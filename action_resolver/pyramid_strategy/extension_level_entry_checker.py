from dataclasses import dataclass


@dataclass
class PyramidExtensionLevelEntryResult:
    allowed: bool


class PyramidExtensionLevelEntryChecker:

    def __init__(self, side: str):
        self.side = side

    def check(self, cur_price: float, entries) -> PyramidExtensionLevelEntryResult:
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

        return PyramidExtensionLevelEntryResult(
            allowed=allowed,
        )