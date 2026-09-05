from action_processor.action import (
    Action,
    ActionCommand,
)
from services.distance_service import (
    is_distance_ok,
)
from common.trading_info import TradingInfo
from action_processor.action_source import ActionSource
from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver


class RearmChecker:

    def __init__(
        self,
        runtime,
        state_store,
        map_mng,
        proxy_driver: ProxyDriver,
        price_service: MarketService,
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

   
    def check(self, execution_result=None) -> ActionCommand | None:
        # Проверяем, есть ли запрос на rearm. 
        if not self.runtime.pending_rearm:
            return None

        # Проверяем результат rearm-ордера из предыдущего цикла.
        if (
            execution_result is not None
            and execution_result.action_command.source
            == ActionSource.REARM_CHECKER
        ):
            if execution_result.executed:
                # Предыдущий rearm успешно выполнен.
                self.runtime.pending_rearm = False
                return None

            # Предыдущий rearm НЕ выполнен.
            # pending_rearm оставляем True — будем пробовать снова.

        rearm_ready = self._is_rearm_ready()
        if not rearm_ready:
            self.logger.info(
                f"[REARM] {self.runtime.rearm_status}"
            )
            return None

        qty = self._get_qty()

        return ActionCommand(
            action=Action.OPEN,
            symbol=self.symbol,
            side=self.side,
            qty=qty,
            reason="rearm",
            source=ActionSource.REARM_CHECKER,
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

        threshold = tpl.htf_rsi_rearm_threshold

        rsi_ok = self._is_rsi_ok(
            rsi,
            threshold,
        )

        self.runtime.rsi_exit_status = (
            "OK" if rsi_ok else "BLOCK"
        )        

        return rsi_ok    
    
    def _is_rearm_ready(self):

        entries = self.state_store.stack_mng.data.entries

        market_price = self.price_service.get_market_price(
            self.symbol,
            self.side,
        )

        distance_ok = self._is_rearm_distance_ok(
            market_price,
            entries,
        )

        rsi_ok = self.is_rearm_rsi_ok(entries)

        if distance_ok and rsi_ok:
            self.runtime.rearm_status = "READY"
        elif not distance_ok and not rsi_ok:
            self.runtime.rearm_status = "BLOCK: DISTANCE + RSI"
        elif not distance_ok:
            self.runtime.rearm_status = "BLOCK: DISTANCE"
        else:
            self.runtime.rearm_status = "BLOCK: RSI"        

        return distance_ok and rsi_ok

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