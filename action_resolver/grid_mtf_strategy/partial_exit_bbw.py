from action_processor.action import (
    Action,
    ActionCommand,
)
from services.bb_service import BBService
from utils.utils import get_inverse_side


class PartialExitBBW:
    def __init__(
        self,
        runtime,
        state_store,
        proxy_driver,
        price_service,
        map_mng,
        side,
        symbol,
    ):
        self.state_store = state_store
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.map_mng = map_mng
        self.side = side
        self.symbol = symbol
        self.runtime = runtime

        self.bb_service = BBService(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

    def get_distance(self, price, entry):
        if self.side == "Sell":
            distance = entry.price - price
        else:
            distance = price - entry.price
            
        return distance
    
    def get_take_profit(self):
        entries = self.state_store.stack_mng.data.entries
        level_number = len(entries) - 1
        tf = self.map_mng.get_tf_for_level(level_number)

        bb = self.bb_service.get_last_closed(tf)

        if self.side == "Sell":
            take_profit = (
                bb["mid"]
                - (bb["mid"] - bb["lower"]) * 0.85
            )
        else:
            take_profit = (
                bb["mid"]
                + (bb["upper"] - bb["mid"]) * 0.85
            )

        return take_profit, tf    

    def get_min_max_distances(self, entry):
        min_distance = (
            entry.price *
            self.state_store.data.min_profit_pct / 100
        )
        max_distance = (
            entry.price *
            self.state_store.data.max_profit_pct / 100
        )
        return min_distance,max_distance

    def get_most_profitable_level(self, entries):
        if self.side == "Sell":
            entry = max(entries, key=lambda e: e.price)
        else:
            entry = min(entries, key=lambda e: e.price)
        return entry   

    def check(self):
        entries = self.state_store.stack_mng.data.entries

        if not entries:
            self.runtime.bbw_exit_status = "NO_POS"
            return None

        cur_price = self.price_service.get_market_close_price(
            symbol=self.symbol,
            side=self.side,
        )

        entry = self.get_most_profitable_level(entries)

        distance = self.get_distance(cur_price, entry)
        min_distance, max_distance = self.get_min_max_distances(entry)

        if distance < min_distance:
            return None

        if distance >= max_distance:
            return self._close(entry)

        if not self._is_take_profit_reached(cur_price):
            return None

        return self._close(entry)    

    def _close(self, entry):
        self.runtime.pending_rearm = True

        return ActionCommand(
            action=Action.CLOSE,
            symbol=self.symbol,
            levels=[entry],
            side=get_inverse_side(self.side),
            qty=entry.qty,
            reason="bbw",
        )    

    def _update_exit_status(self, take_profit):
        self.runtime.bbw_exit_status = f"[tp={take_profit:.6f}]"    

    def _is_take_profit_reached(self, cur_price):
        take_profit, _ = self.get_take_profit()
        self._update_exit_status(take_profit)

        if self.side == "Sell":
            return cur_price <= take_profit

        return cur_price >= take_profit        