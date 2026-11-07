from dataclasses import dataclass


@dataclass
class PyrExtensionLevelEntryResult:
    allowed: bool


class PyrExtensionLevelEntryChecker:

    def __init__(self, side: str):
        self.side = side

    def check(self, cur_price: float, entries) -> PyrExtensionLevelEntryResult:
        if self.side == "Buy":
            allowed = any(
                entry.price < cur_price
                for entry in entries
            )
        else:
            allowed = any(
                entry.price > cur_price
                for entry in entries
            )

        return PyrExtensionLevelEntryResult(
            allowed=allowed,
        )