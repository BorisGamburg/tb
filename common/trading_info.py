from dataclasses import dataclass
import math


@dataclass(slots=True)
class TradingInfo:

    symbol: str
    qty_step: float
    min_qty: float
    fee_taker: float

    def get_valid_order_qty(self, qty: float) -> float:
        qty = math.floor(qty / self.qty_step) * self.qty_step

        if qty < self.min_qty:
            return 0.0

        return round(qty, 8)