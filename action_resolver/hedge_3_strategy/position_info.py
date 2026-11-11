from dataclasses import dataclass


@dataclass
class PositionInfo:
    side: str
    qty: float
    entry_price: float
