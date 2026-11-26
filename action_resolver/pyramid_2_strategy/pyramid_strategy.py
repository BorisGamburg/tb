from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.pyramid_2_strategy.pyramid_mode_resolver import PyramidModeResolver
from common.trading_info import TradingInfo
from common.unwind.unwinder import Unwinder
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
from action_resolver.pyramid_2_strategy.pyr_empty_mode import (
    PyrEmptyMode,
)
from action_resolver.pyramid_2_strategy.pyr_profit_mode import (
    PyrProfitMode,
)
from common.recovery.recovery_mode import RecoveryMode
from common.recovery.ha_breakout_opener import PyrHaBreakoutOpener


class StackLimitExceededError(Exception):
    """Стоимость стека превысила max_stack_pct от баланса (авария)."""


class PyramidStrategy(BaseStrategy):
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

        self.unwinder = Unwinder(
            action_service=self.action_service,
            trading_info=trading_info,
            logger=app_ctx.logger,
        )

        self.empty_mode = PyrEmptyMode(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=self.action_service,
            open_checker=self.open_checker,
        )

        self.profit_mode = PyrProfitMode(
            state_store=state_store,
            app_ctx=app_ctx,
            trading_info=trading_info,
            action_service=self.action_service,
            open_checker=self.open_checker,
            close_processor=self.close_processor,
            unwinder=self.unwinder,
        )

        # HA Breakout для Recovery: используем тот же HA-сигнал,
        # что создан в EntryChecker.
        recovery_ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=self.action_service,
            ha_signal=self.open_checker.ha_signal,
            tf_set=state_store.data.recovery_tf,
        )

        self.recovery_mode = RecoveryMode(
            state_store=state_store,
            app_ctx=app_ctx,
            trading_info=trading_info,
            action_service=self.action_service,
            unwinder=self.unwinder,
            ha_opener=recovery_ha_opener,
            get_qty=self.open_checker.get_qty,
            step_ratio=self.open_checker.step_ratio,
        )

        self._log_parameters()

    def resolve(self) -> ResolveResult:
        data = self.state_store.data

        current_price = self.app_ctx.price_service.get_market_close_price(
            symbol=data.symbol,
            side=data.side,
        )

        # Аварийная защита от ликвидации: до любой другой логики.
        self._check_stack_limit(current_price)

        mode = PyramidModeResolver.resolve(
            side=data.side,
            current_price=current_price,
            stack_mng=self.state_store.stack_mng,
            fee_taker=self.trading_info.fee_taker,
        )

        if mode == PyramidModeResolver.EMPTY_MODE:
            result = self.empty_mode.resolve()
        elif mode == PyramidModeResolver.PROFIT_MODE:
            result = self.profit_mode.resolve()
        elif mode == PyramidModeResolver.RECOVERY_MODE:
            # Политика запуска Recovery живёт в стратегии, не в модуле
            wait = self._recovery_wait(current_price)
            result = wait if wait is not None else self.recovery_mode.resolve()
        else:
            raise ValueError(f"Unsupported Pyramid mode: {mode}")

        return ResolveResult(
            executed=result.executed,
            status=self._build_status_line(
                mode=mode,
                current_price=current_price,
                mode_status=result.status,
            ),
        )

    def _check_stack_limit(self, current_price: float) -> None:
        """Стек (qty * текущая цена) больше max_stack_pct от баланса ->
        исключение. ActionProcessor.run() пишет его в лог и Telegram и
        останавливает бота. Баланс <= 0 тоже считается аварией.
        """
        data = self.state_store.data
        entries = data.stack.entries
        if not entries:
            return

        stack_qty = sum(lv.qty for lv in entries)
        stack_value = stack_qty * current_price
        balance = self.app_ctx.proxy_driver.get_balance()
        stack_pct = stack_value / balance * 100 if balance > 0 else float("inf")

        if stack_pct > data.max_stack_pct:
            raise StackLimitExceededError(
                f"АВАРИЯ: стек превысил лимит. "
                f"{data.symbol} {data.side} | "
                f"стек {stack_pct:.1f}% > лимит {data.max_stack_pct}% "
                f"от баланса | уровней: {len(entries)}, qty: {stack_qty}, "
                f"стоимость: {stack_value:.2f} USDT, баланс: {balance:.2f} USDT, "
                f"цена: {current_price}. Бот остановлен. Лимитные ордера "
                f"на бирже не отменены - проверьте вручную."
            )

    def _recovery_wait(self, current_price: float) -> ResolveResult | None:
        """None - Recovery можно запускать, иначе результат ожидания.

        Цена выше Base и ровно два уровня, расположенные слишком близко
        (min_close_steps) -> Recovery не запускаем. Цена не выше Base ->
        проверка не нужна: компенсировать нечем, возможен только новый Base.
        """
        data = self.state_store.data
        entries = data.stack.entries

        if data.side == "Buy":
            base_price = min(level.price for level in entries)
            above_base = current_price > base_price
        else:
            base_price = max(level.price for level in entries)
            above_base = current_price < base_price

        if not above_base:
            return None

        return self.profit_mode.extension_close.check_distance_for_two_levels()

    def _build_status_line(
        self,
        mode: str,
        current_price: float,
        mode_status: str,
    ) -> str:
        """Статусная строка: общая шапка + статус текущего режима."""
        data = self.state_store.data
        ticker = self.app_ctx.proxy_driver.get_ticker(data.symbol)

        status = f"BID/ASK: {ticker['bid']:.6f} — {ticker['ask']:.6f} | "

        # Режим
        if mode == PyramidModeResolver.EMPTY_MODE:
            status += "MODE: ⚪ EMPTY | "
        elif mode == PyramidModeResolver.PROFIT_MODE:
            status += "MODE: 🟢 PROFIT | "
        else:
            status += "MODE: 🔴 RECOVERY | "

        # Безубыток стека и буфер между ценой и BE
        stack_be = self.state_store.stack_mng.calculate_break_even_price(
            data.side,
            self.trading_info.fee_taker,
        )
        if stack_be is None:
            status += "BE: — | "
        else:
            if data.side == "Buy":
                buffer_pct = (current_price - stack_be) / current_price * 100
            else:
                buffer_pct = (stack_be - current_price) / current_price * 100
            status += f"BE: {stack_be:.6f} (BUFFER {buffer_pct:+.2f}%) | "

        status += f"LEVELS: {len(data.stack.entries)} | "
        status += self._close_target_status(mode)
        tf_set = (
            data.recovery_tf
            if mode == PyramidModeResolver.RECOVERY_MODE
            else data.profit_tf
        )
        status += f"HA({tf_set.tf}) | "
        status += mode_status

        return status.rstrip(" |")

    def _close_target_status(self, mode: str) -> str:
        """Цена закрытия Extension (только в PROFIT и если есть что закрывать)."""
        if mode != PyramidModeResolver.PROFIT_MODE:
            return ""

        target = self.profit_mode.get_close_target()
        if target is None:
            return ""

        return f"CLOSE AT: {target:.6f} | "

    def _log_parameters(self) -> None:
        data = self.state_store.data
        params = (
            f"ЗАГРУЖЕННЫЕ ПАРАМЕТРЫ\n"
            f"Symbol: {data.symbol}\n"
            f"Side: {data.side}\n"
            f"Strategy: {data.strategy}\n"
            f"Profit TF: {data.profit_tf.tf}\n"
            f"Recovery TF: {data.recovery_tf.tf}\n"
            f"Open step: {data.open_step_pct}%\n"
            f"Open qty: {data.open_qty_pct}%\n"
            f"Min BE buffer: {data.min_be_buffer_pct}%\n"
            f"BE close buffer: {data.be_close_buffer_pct}%\n"
            f"Fold trigger L/P: {data.trigger_pct}%\n"
            f"Fold target L/P: {data.target_pct}%\n"
            f"Fold min pnl: {data.min_pnl}\n"
            f"Min stack: {data.min_stack_pct}% of balance\n"
            f"Max stack: {data.max_stack_pct}% of balance\n"
            f"Sleep interval: {data.sleep_interval}\n"
        )
        self.app_ctx.logger.info(params)