from dataclasses import dataclass

from services.distance_service import (
    is_distance_ok,
)
from common.trading_info import TradingInfo
from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver
from action_processor.action_service import ActionService
from action_processor.action import Action, ActionCommand
from action_processor.action_source import ActionSource
from action_processor.process_result import ProcessResult


@dataclass
class RearmCheckResult:
    distance_ok: bool
    rsi_ok: bool

class RearmMng:

    def __init__(
        self,
        state_store,
        map_mng,
        proxy_driver: ProxyDriver,
        price_service: MarketService,
        logger,
        symbol,
        side,
        trading_info: TradingInfo,
        action_service: ActionService,
    ):
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger
        self.symbol = symbol
        self.side = side
        self.trading_info = trading_info
        self.action_service = action_service
        

    def _get_rsi_last_closed(
        self,
        tf,
    ):

        data = self.proxy_driver.get_rsi(
            symbol=self.symbol,
            tf=tf,
        )

        return data.get(
            "rsi_last_closed"
        )

    def check(self) -> RearmCheckResult:
        return self._is_rearm_ready()
        
    def _is_rearm_distance_ok(
        self,
        chase_price,
        entries,
    ):
        min_distance_ratio = (
            self.state_store.data.min_rearm_distance_pct / 100
        )

        required_distance = (
            chase_price * min_distance_ratio
        )

        distance_ok = is_distance_ok(
            price=chase_price,
            entries=entries,
            required_distance=required_distance,
        )

        return distance_ok    

        
    
    def is_rearm_rsi_ok(self, entries):

        level = len(entries) - 1

        tpl = self.map_mng.get_template_by_level(
            level
        )

        rsi = self._get_rsi_last_closed(
            tpl.htf_filter
        )

        threshold = tpl.htf_rsi_rearm_threshold

        rsi_ok = self._is_rsi_ok(
            rsi,
            threshold,
        )

        return rsi_ok    
    
    def _is_rearm_ready(self):

        entries = self.state_store.stack_mng.data.entries

        market_price = self.price_service.get_active_price(
            self.symbol,
            self.side,
        )

        distance_ok = self._is_rearm_distance_ok(
            market_price,
            entries,
        )

        rsi_ok = self.is_rearm_rsi_ok(entries)

        return RearmCheckResult(
            distance_ok=distance_ok,
            rsi_ok=rsi_ok,
        )

    def _get_qty(self):
        level = len(self.state_store.stack_mng.data.entries)

        cur_map_elem = self.map_mng.get_template_by_level(level)
        qty_factor = cur_map_elem.qty_pct / 100

        balance = self.proxy_driver.get_balance()
        price = self.proxy_driver.get_last_price(self.symbol)

        qty_in_usd = qty_factor * balance
        qty = qty_in_usd / price

        qty = self.trading_info.get_valid_order_qty(qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid OPEN qty: {qty} "
                f"(level={level}, qty_factor={qty_factor})"
            )

        return qty        

    def _is_rsi_ok(
        self,
        rsi,
        threshold,
    ):

        if rsi is None:
            raise RuntimeError(
                f"RSI is unavailable: symbol={self.symbol}"
            )

        if self.side == "Sell":
            return rsi >= threshold

        return rsi <= threshold    

    def _build_rearm_action(self, initial_qty: float) -> ActionCommand:
        qty = self.trading_info.get_valid_order_qty(initial_qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid REARM qty: {qty} (initial_qty={initial_qty})"
            )

        return ActionCommand(
            action=Action.OPEN,
            symbol=self.symbol,
            side=self.side,
            qty=qty,
            reason="REARM",
            source=ActionSource.REARM_CHECKER
        )

    def _execute_rearm(
        self,
        process_result: ProcessResult,
        initial_qty: float
    ) -> ProcessResult:
        action = self._build_rearm_action(initial_qty=initial_qty)

        process_result = self.action_service.process_action(
            action,
            process_result,
        )

        return process_result

    def _resolve_rearm(
        self,
        process_result: ProcessResult,
        initial_qty: float
    ) -> tuple[ProcessResult, RearmCheckResult]:
        while True:
            # Проверяем, нужно ли выполнять REARM
            check_result = self.check()

            if not check_result.distance_ok or not check_result.rsi_ok:
                # REARM не нужен -> выходим из цикла
                return process_result, check_result
            else:
                # REARM нужен -> выполняем его
                process_result = self._execute_rearm(
                    process_result=process_result,
                    initial_qty=initial_qty
                )

                # Проверяем, выполнен ли REARM
                if process_result.executed:
                    # REARM выполнен -> выходим из цикла
                    return process_result, check_result
                else:
                    # REARM не выполнен -> повторно проверяем условия
                    self.logger.warning(
                        "REARM не выполнен, повторная попытка..."
                    )    