from action_processor.state.state import State
from action_processor.action_service import ActionService
from action_processor.action import Action, ActionCommand
from action_processor.action_source import ActionSource
from action_processor.process_result import ProcessResult
from common.trading_info import TradingInfo
from action_resolver.grid_mtf_strategy.entry_checker import EntryChecker, EntryCheckResult
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from action_processor.bootstrap import AppContext


class EntryMng:

    def __init__(
        self,
        runtime,
        state_store: State,
        map_mng: GridMTFMapMng,
        app_ctx: AppContext,
        trading_info: TradingInfo,
        action_service: ActionService,
    ):
        self.state_store = state_store
        self.map_mng = map_mng
        self.app_ctx = app_ctx
        self.runtime = runtime
        self.trading_info = trading_info
        self.action_service = action_service

        self.entry_checker = EntryChecker(
            runtime=self.runtime,
            state_store=self.state_store,
            map_mng=self.map_mng,
            proxy_driver=self.app_ctx.proxy_driver,
            price_service=self.app_ctx.price_service,
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
        )

    def _get_entry_qty(self) -> float:
        level = len(self.state_store.stack_mng.data.entries)

        cur_map_elem = self.map_mng.get_template_by_level(level)
        qty_factor = cur_map_elem.qty_pct / 100

        balance = self.app_ctx.proxy_driver.get_balance()
        qty_in_usd = qty_factor * balance

        price = self.app_ctx.proxy_driver.get_last_price(self.state_store.data.symbol)

        qty = qty_in_usd / price

        qty = self.trading_info.get_valid_order_qty(qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid OPEN qty: {qty} "
                f"(qty_factor={qty_factor})"
            )

        return qty

    def _execute_open(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        action = ActionCommand(
            action=Action.OPEN,
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
            qty=self._get_entry_qty(),
            reason="ha_reversal",
            source=ActionSource.ENTRY_CHECKER
        )

        process_result = self.action_service.process_action(
            action,
            process_result,
        )

        return process_result

    def resolve(
        self,
        process_result: ProcessResult,
    ) -> tuple[ProcessResult, EntryCheckResult]:
        check_result = self.entry_checker.check()

        entry_allowed = check_result.entry_allowed
        ha_ok = check_result.ha.signal
        rsi_ok = check_result.rsi.ok
        bb_ok = check_result.bb_ok
        distance_ok = check_result.distance_ok

        if self.app_ctx.notifier is None:
            raise RuntimeError("Notifier is not initialized")

        self.app_ctx.notifier.log_distance_blocked(
            ha_ok,
            rsi_ok,
            distance_ok,
        )

        if entry_allowed:
            process_result = self._execute_open(
                process_result,
            )
        else:
            process_result.executed = False

        return process_result, check_result