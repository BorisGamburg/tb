from action_processor.state.state import State
from action_processor.action_service import ActionService
from action_processor.action import Action, ActionCommand
from action_processor.action_source import ActionSource
from action_processor.process_result import ProcessResult
from common.trading_info import TradingInfo
from action_resolver.grid_mtf_strategy.entry_checker import EntryChecker
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng


class EntryMng:

    def __init__(
        self,
        runtime,
        state_store: State,
        map_mng: GridMTFMapMng,
        proxy_driver,
        price_service,
        symbol,
        side,
        trading_info: TradingInfo,
        action_service: ActionService,
        notifier,
    ):
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side
        self.runtime = runtime
        self.trading_info = trading_info
        self.action_service = action_service
        self.notifier = notifier

        self.entry_checker = EntryChecker(
            runtime=self.runtime,
            state_store=self.state_store,
            map_mng=self.map_mng,
            proxy_driver=self.proxy_driver,
            price_service=price_service,
            symbol=self.symbol,
            side=self.side,
        )

    def _get_entry_qty(self) -> float:
        level = len(self.state_store.stack_mng.data.entries)

        cur_map_elem = self.map_mng.get_template_by_level(level)
        qty_factor = cur_map_elem.qty_pct / 100

        balance = self.proxy_driver.get_balance()
        qty_in_usd = qty_factor * balance

        price = self.proxy_driver.get_last_price(self.symbol)

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
            symbol=self.symbol,
            side=self.side,
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
    ) -> ProcessResult:
        (
            entry_allowed,
            ha_ok,
            rsi_ok,
            bb_ok,
            distance_ok,
        ) = self.entry_checker.check()

        if self.notifier is None:
            raise RuntimeError("Notifier is not initialized")

        self.notifier.log_distance_blocked(
            ha_ok,
            rsi_ok,
            distance_ok,
        )

        if entry_allowed:
            return self._execute_open(
                process_result,
            )

        process_result.executed = False

        return process_result