from action_processor.action_service import ActionService
from action_processor.bootstrap import AppContext
from action_processor.execution.limit_order_result import LimitOrderStatus
from action_processor.state.state import State
from action_resolver.base_strategy import BaseStrategy
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_signal import (
    HAReversalSignal,
)
from action_resolver.pyramid_2_strategy.pyr_qty_calculator import (
    PyrQtyCalculator,
)
from action_resolver.resolve_result import ResolveResult
from common.recovery.ha_breakout_opener import PyrHaBreakoutOpener
from common.recovery.recovery_mode import RecoveryMode
from common.trading_info import TradingInfo
from common.unwind.unwinder import Unwinder


# Запас над безубытком стека (доля от цены): покрывает проскальзывание.
# BE уже учитывает комиссии.
EXIT_BE_MARGIN = 0.0005  # 0.05%


class RecoveryStrategy(BaseStrategy):
    """Сборщик мусора: только компенсация и закрытие стека в безубыток.

    Цикл (для Buy, для Sell зеркально; close_price - bid/ask):
      1. стек пуст                      -> работа завершена, бот стоп;
      2. close_price >= BE * (1 + k)    -> закрываем весь стек;
      3. close_price > BE               -> ждём;
      4. close_price <= BE              -> RecoveryMode.resolve().
    """

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

        data = state_store.data

        self.action_service = ActionService(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

        self.unwinder = Unwinder(
            action_service=self.action_service,
            trading_info=trading_info,
            logger=app_ctx.logger,
        )

        qty_calculator = PyrQtyCalculator(
            proxy_driver=app_ctx.proxy_driver,
            symbol=data.symbol,
            qty_pct=float(data.open_qty_pct),
            trading_info=trading_info,
        )

        ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=self.action_service,
            ha_signal=HAReversalSignal(
                proxy_driver=app_ctx.proxy_driver,
                symbol=data.symbol,
            ),
        )

        self.recovery_mode = RecoveryMode(
            state_store=state_store,
            app_ctx=app_ctx,
            trading_info=trading_info,
            action_service=self.action_service,
            unwinder=self.unwinder,
            ha_opener=ha_opener,
            get_qty=lambda: qty_calculator.calculate()[1],
            step_ratio=float(data.open_step_pct) / 100,
            # Стек опустел после компенсации -> работа закончена,
            # новый уровень не открываем.
            rearm_if_empty=False,
        )

        self._log_parameters()

    def resolve(self) -> ResolveResult:
        data = self.state_store.data

        if not data.stack.entries:
            self.finished = True
            return ResolveResult(
                executed=False,
                status=self._build_status_line(None, None, "DONE: STACK EMPTY"),
            )

        close_price = float(
            self.app_ctx.price_service.get_market_close_price(
                symbol=data.symbol,
                side=data.side,
            )
        )
        stack_be = self.state_store.stack_mng.calculate_break_even_price(
            data.side,
            self.trading_info.fee_taker,
        )
        exit_price = self._get_exit_price(stack_be)

        if self._is_above(close_price, exit_price):
            result = self._close_stack(close_price, stack_be)
        elif self._is_above(close_price, stack_be):
            result = ResolveResult(
                executed=False,
                status="WAIT: PRICE BETWEEN BE AND EXIT",
            )
        else:
            result = self.recovery_mode.resolve()

        return ResolveResult(
            executed=result.executed,
            status=self._build_status_line(
                close_price, exit_price, result.status
            ),
        )

    def _get_exit_price(self, stack_be: float) -> float:
        """Порог закрытия: BE плюс запас (для Sell - минус)."""
        if self.state_store.data.side == "Buy":
            return stack_be * (1 + EXIT_BE_MARGIN)
        return stack_be * (1 - EXIT_BE_MARGIN)

    def _is_above(self, close_price: float, level: float) -> bool:
        """Цена по выгодную сторону от уровня (Buy: выше, Sell: ниже)."""
        if self.state_store.data.side == "Buy":
            return close_price >= level
        return close_price <= level

    def _close_stack(self, close_price: float, stack_be: float) -> ResolveResult:
        data = self.state_store.data
        entries = data.stack.entries
        total_qty = sum(level.qty for level in entries)

        self.app_ctx.logger.info(
            f"[RECOVERY EXIT] price={close_price} | be={stack_be} "
            f"| levels={len(entries)} | qty={total_qty}"
        )

        exec_result = self.unwinder.run(
            levels=entries,
            side=data.side,
            symbol=data.symbol,
            qty=total_qty,
            price=close_price,
            min_pnl=0.0,
        )

        if exec_result is None:
            return ResolveResult(
                executed=False,
                status="EXIT: SKIPPED (QTY < MIN)",
            )

        if not exec_result.executed:
            return ResolveResult(executed=False, status="EXIT: NOT FILLED")

        status = (
            "FILLED"
            if exec_result.status == LimitOrderStatus.FILLED
            else "PARTIALLY FILLED"
        )
        return ResolveResult(
            executed=True,
            status=(
                f"EXIT: {status} "
                f"| price={exec_result.price} | qty={exec_result.qty}"
            ),
        )

    def _build_status_line(
        self,
        close_price: float | None,
        exit_price: float | None,
        mode_status: str,
    ) -> str:
        data = self.state_store.data
        ticker = self.app_ctx.proxy_driver.get_ticker(data.symbol)

        status = f"BID/ASK: {ticker['bid']:.6f} — {ticker['ask']:.6f} | "
        status += "MODE: 🧹 RECOVERY | "

        if exit_price is not None:
            status += f"EXIT AT: {exit_price:.6f} | "

        status += f"LEVELS: {len(data.stack.entries)} | "
        status += f"HA({data.entry_tf}) | "
        status += mode_status

        return status.rstrip(" |")

    def _log_parameters(self) -> None:
        data = self.state_store.data
        self.app_ctx.logger.info(
            f"ЗАГРУЖЕННЫЕ ПАРАМЕТРЫ\n"
            f"Symbol: {data.symbol}\n"
            f"Side: {data.side}\n"
            f"Strategy: {data.strategy}\n"
            f"Entry TF: {data.entry_tf}\n"
            f"Open step: {data.open_step_pct}%\n"
            f"Open qty: {data.open_qty_pct}%\n"
            f"Min pnl: {data.min_pnl}\n"
            f"Exit margin over BE: {EXIT_BE_MARGIN * 100:.3f}%\n"
            f"Sleep interval: {data.sleep_interval}\n"
        )
