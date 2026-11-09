from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from common.trading_info import TradingInfo
from action_resolver.pyramid_2_strategy.unwinder import (
    FoldConfig,
    Unwinder,
)
from action_processor.action import Action
from action_processor.action import ActionCommand
from action_processor.action_service import ActionService
from action_resolver.resolve_result import ResolveResult
from action_resolver.pyramid_2_strategy.pyr_entry_checker import (
    PyrEntryChecker,
)
from action_resolver.pyramid_2_strategy.pyr_partial_close_calculator import (
    PyrPartialCloseCalculator,
)
from action_resolver.pyramid_2_strategy.pyr_close_processor import (
    PyrCloseProcessor,
)
from action_resolver.pyramid_2_strategy.pyr_tp_checker import PyrTPChecker
from utils.utils import get_inverse_side
from action_resolver.pyramid_2_strategy.pyr_dust_cleaner import (
    PyrDustCleaner,
)
from action_resolver.pyramid_2_strategy.pyr_loss_fold_planner import (
    _per_coin,
)
from action_resolver.pyramid_2_strategy.pyr_position_limit_checker import (
    is_position_limit_allowed,
)
from common.level_distance_checker import is_level_distance_allowed

class PyramidStrategy(BaseStrategy):
    BASE_TIMEFRAMES = ["1", "5", "15", "60", "240", "720"]
    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ):
        super().__init__()

        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info

        self.action_service = ActionService(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

        self.partial_close_calculator = PyrPartialCloseCalculator()

        self.close_processor = PyrCloseProcessor(
            action_service=self.action_service,
            partial_close_calculator=self.partial_close_calculator,
            trading_info=trading_info,
        )
        self.open_checker = PyrEntryChecker(
            proxy_driver=app_ctx.proxy_driver,
            symbol=state_store.data.symbol,
            side=state_store.data.side,
            step_pct=float(state_store.data.open_step_pct),
            qty_pct=float(state_store.data.open_qty_pct),
            trading_info=trading_info,
        )

        self.profit_close_checker = PyrTPChecker(
            proxy_driver=app_ctx.proxy_driver,
            symbol=state_store.data.symbol,
            side=state_store.data.side,
            price_service=app_ctx.price_service,
            fee_taker=trading_info.fee_taker,
        )

        self.dust_cleaner = PyrDustCleaner(
            symbol=state_store.data.symbol,
            side=state_store.data.side,
            price_service=app_ctx.price_service,
            trading_info=trading_info,
            logger=app_ctx.logger,
        )

        self.unwinder = Unwinder(
            proxy_driver=app_ctx.proxy_driver,
            action_service=self.action_service,
            trading_info=trading_info,
            logger=app_ctx.logger,
        )

        self._log_parameters()

    def resolve(self) -> ResolveResult:
        # Проверяем закрытие dust-уровня
        dust_result, dust_found = self._process_dust_close()
        if dust_found:
            return dust_result

        # Проверяем закрытие всей пирамиды по прибыли
        profit_close_result, profit_close_found = self._process_profit_close()
        if profit_close_found:
            return profit_close_result

        # Проверяем Unwind
        close_result, close_found, fold_report = self._process_close()
        if close_found:
            return close_result

        # Проверяем открытие
        entry_result, executed = self._process_open()

        # Строка статуса строится здесь, один раз, в конце
        status = self._build_status_line(entry_result, fold_report)

        return ResolveResult(executed=executed, status=status)

    def _process_open(self) -> tuple:
        """Возвращает (entry_result, executed)."""
        # Проверяем сигнал на открытие
        entry_result = self.open_checker.check(
            self.state_store.data.stack.entries,
            self.state_store.data.entry_tf,
        )

        if not entry_result.allowed:
            return entry_result, False

        # Формируем команду
        action_command = ActionCommand(
            action=Action.OPEN,
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
            qty=entry_result.qty,
        )

        # Передаем команду на исполнение и учет
        exec_result = self.action_service.process_action(action_command)
        if exec_result.executed and entry_result.level_type == "base":
            self._advance_entry_tf()

        return entry_result, exec_result.executed

    def _process_close(self) -> tuple[ResolveResult, bool, object]:
        """Возвращает (ResolveResult, найдено, fold_report)."""
        # Свёртывание стека по порогу L/P
        exec_result, fold_report = self.unwinder.run(
            self._fold_config(),
            self.state_store.data.stack.entries,
        )
        if exec_result is None:
            # Запускать нечего -> выходим
            return ResolveResult(executed=False, status=""), False, fold_report

        # Свёртывание исполнилось -> пробуем открыть донорский уровень
        if exec_result.executed:
            self._try_rearm()

        return ResolveResult(
            executed=exec_result.executed,
            status="",
        ), True, fold_report

    def _fold_config(self) -> FoldConfig:
        """Настройки свёртывания из состояния стратегии (читаются на каждом тике)."""
        data = self.state_store.data
        return FoldConfig(
            symbol=data.symbol,
            side=data.side,
            trigger_pct=data.trigger_pct,
            target_pct=data.target_pct,
            min_pnl=data.min_pnl,
            min_stack_pct=data.min_stack_pct,
        )

    def _try_rearm(self) -> None:
        """Rearm после успешного свёртывания (разовая проверка).

        Открываем новый уровень, только если:
        1) в стеке не осталось прибыльных уровней (пустой стек - частный
           случай), т.е. нет донора для следующего свёртывания;
        2) расстояние от цены до каждого уровня стека не меньше шага
           пирамиды (open_step_pct);
        3) размер позиции в норме (is_position_limit_allowed);
        4) объём rearm больше нуля.
        Не прошла проверка - rearm пропускаем, дальше работает обычный вход.
        """
        data = self.state_store.data
        entries = data.stack.entries
        proxy_driver = self.app_ctx.proxy_driver

        # 1. Прибыльные уровни остались -> донор есть, rearm не нужен
        if entries:
            ticker = proxy_driver.get_ticker(data.symbol)
            price = ticker["bid"] if data.side == "Buy" else ticker["ask"]
            fee_taker = self.trading_info.fee_taker
            has_profitable = any(
                _per_coin(lv, price, data.side, fee_taker) > 0
                for lv in entries
            )
            if has_profitable:
                return

        # 2. Дистанция до ближайшего уровня не меньше шага пирамиды
        cur_price = float(proxy_driver.get_last_price(data.symbol))
        if not is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=self.open_checker.step_ratio,
        ):
            self.app_ctx.logger.info(
                "[REARM] skipped: distance to nearest level < step"
            )
            return

        # 3. Лимит размера позиции
        if not is_position_limit_allowed(
            proxy_driver, data.symbol, data.side
        ):
            self.app_ctx.logger.info("[REARM] skipped: position limit")
            return

        # 4. Объём
        qty = self.open_checker.get_rearm_qty()
        if qty <= 0:
            self.app_ctx.logger.info("[REARM] skipped: qty = 0")
            return

        rearm_command = ActionCommand(
            action=Action.OPEN,
            symbol=data.symbol,
            side=data.side,
            qty=qty,
            reason="PYRAMID_REARM",
        )

        while True:
            rearm_result = self.action_service.process_action(rearm_command)
            if rearm_result.executed:
                break

    def _process_profit_close(self) -> tuple[ResolveResult, bool]:
        # Если стек пуст, то закрытие по прибыли не проверяем
        entries = self.state_store.data.stack.entries
        if len(entries) == 0:
            return ResolveResult(executed=False, status=""), False

        # Определяем таймфрейм предыдущего уровня
        current_tf = self.state_store.data.entry_tf
        current_index = self.BASE_TIMEFRAMES.index(current_tf)

        if current_index == 0:
            raise ValueError(
                f"Cannot determine close timeframe: "
                f"entry_tf is already at minimum ({current_tf})"
            )

        close_tf = self.BASE_TIMEFRAMES[current_index - 1]

        # Получаем уровни, достигшие безубыточности с учётом комиссий
        # и дополнительного порога прибыли 0.1%.
        profitable_levels = self.profit_close_checker.check(
            entries,
            close_tf,
        )

        if not profitable_levels:
            return ResolveResult(executed=False, status=""), False

        # Закрываем только уровни пирамиды (Action.CLOSE на их суммарный qty),
        # а не всю биржевую позицию: в ней могут быть позиции других стратегий.
        # levels — копия: Accounting удаляет уровни из того же списка entries.
        levels = profitable_levels
        action_command = ActionCommand(
            action=Action.CLOSE,
            symbol=self.state_store.data.symbol,
            side=get_inverse_side(self.state_store.data.side),
            qty=round(sum(level.qty for level in levels), 8),
            levels=levels,
            reason="PYRAMID_PROFIT_CLOSE",
        )

        self.action_service.notify_action(action_command)
        exec_result = self.close_processor.execute_profit_close(action_command)

        return ResolveResult(
            executed=exec_result.executed,
            status="",
        ), True

    def _build_status_line(self, entry_result, fold_report) -> str:
        ticker = self.app_ctx.proxy_driver.get_ticker(
            self.state_store.data.symbol
        )

        status = (
            f"BID/ASK: {ticker['bid']:.6f} — {ticker['ask']:.6f} | "
        )

        ha_marker = "🟢" if entry_result.ha_breakout else "🔴"

        status += (
            f"HA BREAKOUT({self.state_store.data.entry_tf}): "
            f"{ha_marker} | "
        )

        trend_marker = "🟢" if entry_result.trend_active else "🔴"
        status += f"TREND: {trend_marker} | "

        if entry_result.qty_checked:
            status += (
                f"QTY: {entry_result.raw_qty:g} → "
                f"{entry_result.qty:g}"
            )
            if entry_result.qty == 0:
                status += f" (MIN: {self.trading_info.min_qty})"
            status += " | "
        if entry_result.position_limit_blocked:
            status += "POSITION LIMIT: 🔴 | "

        if entry_result.allowed and entry_result.level_type == "base":
            status += "ENTRY: BASE | "
        elif entry_result.allowed and entry_result.level_type == "extension":
            status += "ENTRY: EXTENSION | "

        if self.state_store.data.stack.entries:
            dist_marker = "🟢" if entry_result.distance_allowed else "🔴"
            status += f"DIST: {dist_marker} | "

        fold_status = self._format_fold_status(fold_report)
        if fold_status:
            status += fold_status + " | "

        return status.rstrip(" |")

    def _format_fold_status(self, report) -> str:
        """Fold-часть строки статуса из сырых данных FoldReport."""
        if report is None:
            return ""
        data = self.state_store.data
        plan = report.plan
        ratio = "∞" if plan.ratio == float("inf") else f"{plan.ratio * 100:.1f}%"
        if report.stack_pct < data.min_stack_pct:
            return (
                f"FOLD: 🔴 STACK {report.stack_pct:.1f}% < "
                f"{data.min_stack_pct:g}% | L/P {ratio}"
            )
        if not plan.triggered:
            return (
                f"FOLD: ⚪ L/P {ratio} ≤ {data.trigger_pct:g}% | "
                f"L {plan.L:.4f} P {plan.P:.4f}"
            )
        if not plan.pieces:
            return (
                f"FOLD: 🟠 L/P {ratio} > {data.trigger_pct:g}% | "
                + self._fold_no_cover_reason(report)
            )
        return (
            f"FOLD: 🟢 L/P {ratio} > {data.trigger_pct:g}% | "
            f"CLOSE {plan.total_qty:g}"
        )

    def _fold_no_cover_reason(self, report) -> str:
        """Почему план не построен: сколько прибыли есть и сколько нужно
        минимум (min_qty монет самого дешёвого по убытку уровня)."""
        plan, params = report.plan, report.params
        costs = []
        for lv in report.entries:
            u = _per_coin(
                lv, report.price, self.state_store.data.side, params.fee_taker
            )
            if u < 0:
                costs.append(-u * params.min_qty)
        if not costs:
            return "NO LOSING LEVELS"
        need = min(costs)
        have = max(0.0, min(plan.P - params.min_pnl, plan.budget))
        if have < need:
            return f"NO PROFIT: have {have:.6f} need {need:.6f} USDT"
        return "CAN'T COVER (qty step / min qty)"

    def _log_parameters(self) -> None:
        data = self.state_store.data
        params = (
            f"ЗАГРУЖЕННЫЕ ПАРАМЕТРЫ\n"
            f"Symbol: {data.symbol}\n"
            f"Side: {data.side}\n"
            f"Strategy: {data.strategy}\n"
            f"Entry TF: {data.entry_tf}\n"
            f"Open step: {data.open_step_pct}%\n"
            f"Open qty: {data.open_qty_pct}%\n"
            f"Fold trigger L/P: {data.trigger_pct}%\n"
            f"Fold target L/P: {data.target_pct}%\n"
            f"Fold min pnl: {data.min_pnl}\n"
            f"Min stack: {data.min_stack_pct}% of balance\n"
            f"Sleep interval: {data.sleep_interval}\n"
        )
        self.app_ctx.logger.info(params)

    def _advance_entry_tf(self) -> None:
        # Получаем текущий тф
        current_tf = self.state_store.data.entry_tf

        # Проверяем текущий тф
        if current_tf not in self.BASE_TIMEFRAMES:
            raise ValueError(
                f"Cannot advance entry_tf: {current_tf} "
                f"is not in {self.BASE_TIMEFRAMES}"
            )

        # Получаем следующий тф
        current_index = self.BASE_TIMEFRAMES.index(current_tf)
        if current_index == len(self.BASE_TIMEFRAMES) - 1:
            return
        next_tf = self.BASE_TIMEFRAMES[current_index + 1]

        # Сохраняем следующий тф
        self.state_store.data.entry_tf = next_tf
        self.state_store.save()

        self.app_ctx.logger.info(
            f"Base level opened: entry_tf changed "
            f"from {current_tf} to {next_tf}"
        )

    def _process_dust_close(self) -> tuple[ResolveResult, bool]:

        entries = self.state_store.data.stack.entries

        level, close_qty = self.dust_cleaner.find_closeable_level(
            entries
        )

        if level is None:
            return ResolveResult(executed=False, status=""), False

        action_command = ActionCommand(
            action=Action.CLOSE,
            symbol=self.state_store.data.symbol,
            side=get_inverse_side(self.state_store.data.side),
            qty=close_qty,
            levels=[level],
            reason="PYRAMID_DUST_CLOSE",
        )

        self.action_service.notify_action(action_command)

        exec_result = self.close_processor.execute_profit_close(
            action_command
        )

        return ResolveResult(
            executed=exec_result.executed,
            status="",
        ), True