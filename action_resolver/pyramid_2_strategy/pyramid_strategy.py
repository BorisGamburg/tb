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
from action_resolver.pyramid_2_strategy.pyr_recovery_mode import (
    PyrRecoveryMode,
)


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
        )   

        self.recovery_mode = PyrRecoveryMode(
            state_store=state_store,
            app_ctx=app_ctx,
            trading_info=trading_info,
            action_service=self.action_service,
            open_checker=self.open_checker,
            unwinder=self.unwinder,
        )

        self._log_parameters()

    def resolve(self) -> ResolveResult:
        data = self.state_store.data

        current_price = self.app_ctx.price_service.get_market_close_price(
            symbol=data.symbol,
            side=data.side,
        )

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
            result = self.recovery_mode.resolve()
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
        status += f"HA({data.entry_tf}) | "
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