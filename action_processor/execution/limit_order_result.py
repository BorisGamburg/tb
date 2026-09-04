from dataclasses import dataclass


@dataclass
class LimitOrderResult:
    order_id: str
    avg_price: float | None
    filled_qty: float
    fee: float
    pnl: float
    filled: bool