from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.resolve_result import ResolveResult
from orchestrator.orchestrator import Orchestrator
from common.trading_info import TradingInfo


class OrchestratorStrategy(BaseStrategy):

    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ):
        super().__init__()

        self.state_store = state_store
        self.symbol = state_store.data.symbol
        self.managed_strategies = state_store.data.managed_strategies
        self.app_ctx = app_ctx
        self.trading_info = trading_info

    def _get_close_position_pnl_and_fee(
        self,
        side: str,
    ) -> tuple[float, float]:
        position = self.app_ctx.proxy_driver.get_position(
            self.symbol,
            side,
        )

        qty = float(position["size"])

        if qty <= 0:
            return 0.0, 0.0

        pnl = self.app_ctx.price_service.calc_position_market_close_pnl(
            symbol=self.symbol,
            position_entry_price=float(position["entry_price"]),
            position_qty=qty,
            position_side=side,
        )

        fee = self.app_ctx.price_service.calc_position_market_close_fee(
            symbol=self.symbol,
            position_qty=qty,
            position_side=side,
            fee_taker=self.trading_info.fee_taker,
        )

        return pnl, fee    

    def _is_close_allowed(self) -> bool:
        buy_pnl, buy_fee = self._get_close_position_pnl_and_fee("Buy")
        sell_pnl, sell_fee = self._get_close_position_pnl_and_fee("Sell")

        total_pnl = buy_pnl + sell_pnl
        total_fee = buy_fee + sell_fee

        return total_pnl >= 7 * total_fee    

    def _close_positions(self):
        for strategy in self.managed_strategies:
            endpoint = f"ipc:///tmp/{self.symbol}_{strategy}.sock"

            orchestrator = Orchestrator(endpoint)

            try:
                result = orchestrator.send_command(
                    {"command": "CLOSE_POSITION"},
                    timeout=5.0,
                )
                self.app_ctx.logger.info(
                    f"{strategy}: {result}"
                )
            finally:
                orchestrator.close()    

    def resolve(
        self,
        ctx,
        execution_result=None,
    ) -> ResolveResult:
        if not self._is_close_allowed():
            return ResolveResult(
                action_command=None,
                status="WAIT CLOSE",
                skip_sleep=False,
            )

        self.app_ctx.logger.info(
            "[ORCHESTRATOR] CLOSE CONDITIONS MET | "
            "positions would be closed"
        )

        # TODO: После завершения тестирования раскомментировать.
        # self._close_positions()

        return ResolveResult(
            action_command=None,
            status="CLOSE CONDITIONS MET",
            skip_sleep=False,
        )                   