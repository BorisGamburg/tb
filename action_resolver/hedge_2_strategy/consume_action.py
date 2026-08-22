from dataclasses import dataclass


@dataclass
class ConsumeAction:

    level: object

    qty_before: float
    qty_removed: float
    qty_after: float

    fully_removed: bool