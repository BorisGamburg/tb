from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from common.trading_info import TradingInfo
from common.unwind.unwind_advisor import (
    UnwindConfig,
    UnwindAdvisor,
)
from common.unwind.unwinder import Unwinder
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
from common.unwind.unwind_planner import (
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

        self.unwind_advisor = UnwindAdvisor(
            proxy_driver=app_ctx.proxy_driver,
            trading_info=trading_info,
        )

        self.unwinder = Unwinder(
            action_service=self.action_service,
            trading_info=trading_info,
            logger=app_ctx.logger,
        )

        self._log_parameters()

    def resolve(self) -> ResolveResult:
        # Проверяем Unwind
        close_result, close_found, unwind_report = self._process_close()
        if close_found:
            return close_result

        # Проверяем открытие
        entry_result, executed = self._process_open()

        # Строка статуса строится здесь, один раз, в конце
        status = self._build_status_line(entry_result, unwind_report)

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
        """Возвращает (ResolveResult, найдено, unwind_report)."""
        config = self._unwind_config()
        entries = self.state_store.data.stack.entries

        # Условия свёртывания (размер стека, порог L/P) и объём к закрытию
        unwind_report = self.unwind_advisor.check(config, entries)
        if unwind_report is None or unwind_report.qty_to_close <= 0:
            # Свёртывать нечего -> выходим
            return ResolveResult(executed=False, status=""), False, unwind_report

        # Свёртывание: исполнение и списание по факту
        try:
            exec_result = self.unwinder.run(
                levels=entries,
                side=config.side,
                symbol=config.symbol,
                qty=unwind_report.qty_to_close,
                price=unwind_report.price,
                min_pnl=config.min_pnl,
            )
        except Exception as e:
            plan = unwind_report.plan
            raise RuntimeError(
                f"FOLD unwind failed | "
                f"plan: total_qty={plan.total_qty} pnl={plan.pnl} "
                f"L={plan.L} P={plan.P} ratio={plan.ratio} "
                f"pieces={[(p.level_idx, p.role, p.qty) for p in plan.pieces]} | "
                f"error: {e!r}"
            ) from e

        if exec_result is None:
            # Объём после нормализации меньше минимума -> ордер не отправлялся
            return ResolveResult(executed=False, status=""), False, unwind_report

        # Свёртывание исполнилось -> пробуем открыть донорский уровень
        if exec_result.executed:
            self._try_rearm()

        return ResolveResult(
            executed=exec_result.executed,
            status="",
        ), True, unwind_report

    def _unwind_config(self) -> UnwindConfig:
        """Настройки свёртывания из состояния стратегии (читаются на каждом тике)."""
        data = self.state_store.data
        return UnwindConfig(
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

    def _build_status_line(self, entry_result, unwind_report) -> str:
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

        unwind_status = self._format_unwind_status(unwind_report)
        if unwind_status:
            status += unwind_status + " | "

        return status.rstrip(" |")

    def _format_unwind_status(self, report) -> str:
        """Unwind-часть строки статуса из сырых данных UnwindReport."""
        if report is None:
            return ""
        data = self.state_store.data
        plan = report.plan
        ratio = "∞" if plan.ratio == float("inf") else f"{plan.ratio * 100:.1f}%"
        if report.stack_pct < data.min_stack_pct:
            return (
                f"UNWIND: 🔴 STACK {report.stack_pct:.1f}% < "
                f"{data.min_stack_pct:g}% | L/P {ratio}"
            )
        if not plan.triggered:
            return (
                f"UNWIND: ⚪ L/P {ratio} ≤ {data.trigger_pct:g}% | "
                f"L {plan.L:.4f} P {plan.P:.4f}"
            )
        if not plan.pieces:
            return (
                f"UNWIND: 🟠 L/P {ratio} > {data.trigger_pct:g}% | "
                + self._unwind_no_cover_reason(report)
            )
        return (
            f"UNWIND: 🟢 L/P {ratio} > {data.trigger_pct:g}% | "
            f"CLOSE {plan.total_qty:g}"
        )

    def _unwind_no_cover_reason(self, report) -> str:
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

