from action_processor.state.stack_schema import StackElem


class LevelSelector:
    def __init__(self, hedge_side: str):
        self.hedge_side = hedge_side

    def get_sorted_levels(self, entries: list[StackElem]) -> list[StackElem]:
        return sorted(
            entries,
            key=lambda entry: entry.price,
            reverse=self.hedge_side == "Buy",
        )

    def get_losing_levels(
        self,
        levels: list[StackElem],
        current_price: float,
    ) -> list[StackElem]:
        if self.hedge_side == "Sell":
            return [
                level for level in levels
                if level.price < current_price
            ]

        if self.hedge_side == "Buy":
            return [
                level for level in levels
                if level.price > current_price
            ]

        raise ValueError(f"Unsupported side: {self.hedge_side}")

    def get_next_less_losing_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
    ) -> StackElem | None:
        index = sorted_levels.index(losing_level)

        if index + 1 >= len(sorted_levels):
            return None

        return sorted_levels[index + 1]