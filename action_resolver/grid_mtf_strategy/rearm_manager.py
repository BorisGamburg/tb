from dataclasses import dataclass

from services.distance_service import (
    is_distance_ok,
)
from common.trading_info import TradingInfo
from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver
from action_processor.action_service import ActionService
from action_processor.action import Action, ActionCommand
from action_processor.execution.execution_result import ExecutionResult


@dataclass
class RearmCheckResult:
    distance_ok: bool
    rsi_ok: bool
    rsi: float
    rsi_threshold: float
    rsi_tf: int

@dataclass
class RearmRSIStatus:
    rsi: float
    rsi_threshold: float
    rsi_tf: int
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
        status = self.get_rsi_status(entries)

        return status.rsi_ok, status.rsi, status.rsi_threshold, status.rsi_tf

    def get_rsi_status(self, entries=None):
        if entries is None:
            entries = self.state_store.stack_mng.data.entries

        level = len(entries)
        tpl = self.map_mng.get_template_by_level(level)
        rsi_tf = tpl.entry_bb_rearm_rsi_htf
        rsi = self._get_rsi_last_closed(rsi_tf)
        threshold = tpl.rearm_rsi_htf_threshold
        rsi_ok = self._is_rsi_ok(rsi, threshold)

        return RearmRSIStatus(
            rsi=rsi,
            rsi_threshold=threshold,
            rsi_tf=rsi_tf,
            rsi_ok=rsi_ok,
        )

    def check(self):

        entries = self.state_store.stack_mng.data.entries

        market_price = self.price_service.get_active_price(
            self.symbol,
            self.side,
        )

        distance_ok = self._is_rearm_distance_ok(
            market_price,
            entries,
        )

        rsi_ok, rsi, rsi_threshold, rsi_tf = self.is_rearm_rsi_ok(entries)

        return RearmCheckResult(
            distance_ok=distance_ok,
            rsi_ok=rsi_ok,
            rsi=rsi,
            rsi_threshold=rsi_threshold,
            rsi_tf=rsi_tf,
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
        )

    def _execute_rearm(
        self,
        initial_qty: float
    ) -> ExecutionResult:
        action = self._build_rearm_action(initial_qty=initial_qty)

        return self.action_service.process_action(
            action,
        )

    def _resolve_rearm(
        self,
        initial_qty: float
    ) -> tuple[ExecutionResult | None, RearmCheckResult]:
        while True:
            # Проверяем, нужно ли выполнять REARM
            check_result = self.check()

            if not check_result.distance_ok or not check_result.rsi_ok:
                # REARM не нужен -> выходим из цикла
                return None, check_result
            else:
                # REARM нужен -> выполняем его
                exec_result = self._execute_rearm(
                    initial_qty=initial_qty
                )

                # Проверяем, выполнен ли REARM
                if exec_result.executed:
                    # REARM выполнен -> выходим из цикла
                    return exec_result, check_result
                else:
                    # REARM не выполнен -> повторно проверяем условия
                    self.logger.warning(
                        "REARM не выполнен, повторная попытка..."
                    )    