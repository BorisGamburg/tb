from dataclasses import dataclass
from enum import Enum


class LimitOrderStatus(Enum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    NOT_FILLED = "NOT_FILLED"


@dataclass
class LimitOrderResult:
    order_id: str
    avg_price: float | None
    filled_qty: float
    fee: float
    status: LimitOrderStatus
    filled: bool