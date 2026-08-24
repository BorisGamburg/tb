from action_processor.action import (
    Action,
    ActionCommand,
)
from services.distance_service import (
    is_distance_ok,
)
from common.trading_info import TradingInfo


class RearmChecker:

    def __init__(
        self,
        runtime,
        state_store,
        map_mng,
        proxy_driver,
        price_service,
        logger,
        symbol,
        side,
        trading_info: TradingInfo,
    ):
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger
        self.symbol = symbol
        self.side = side
        self.runtime = runtime
        self.trading_info = trading_info
        

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

    def _is_rsi_ok(
        self,
        rsi,
        threshold,
    ):

        if rsi is None:
            return False

        if self.side == "Sell":
            return rsi >= threshold

        return rsi <= threshold
    
    def check(self):
        if not self.runtime.pending_rearm:
            return None

        self.runtime.pending_rearm = False

        rearm_ready = self._is_rearm_ready()

        if not rearm_ready:
            self.logger.info(
                "[REARM][BLOCKED] Перезарядка пропущена: дистанция от входа не набрана"
            )
            return None

        qty = self._get_qty()

        return ActionCommand(
            action=Action.OPEN,
            symbol=self.symbol,
            side=self.side,
            qty=qty,
            reason="rearm",
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

        if not self.runtime.pending_rearm:
            self.runtime.distance_status = "OFF"
        else:
            self.runtime.distance_status = "OK" if distance_ok else "BLOCK"

        return distance_ok    

        
    
    def is_rearm_rsi_ok(self, entries):

        level = len(entries) - 1

        tpl = self.map_mng.get_template_by_level(
            level
        )

        rsi = self._get_rsi_last_closed(
            tpl.htf_filter
        )

        threshold = tpl.htf_rsi_entry_threshold

        rsi_ok = self._is_rsi_ok(
            rsi,
            threshold,
        )

        return rsi_ok    
    
    def _is_rearm_ready(self):

        entries = self.state_store.stack_mng.data.entries

        chase_price = self.price_service.get_chase_price(
            self.symbol,
            self.side,
        )

        distance_ok = self._is_rearm_distance_ok(
            chase_price,
            entries,
        )

        # rsi_ok = self.is_rearm_rsi_ok(entries)

        return distance_ok

        # return distance_ok and rsi_ok

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