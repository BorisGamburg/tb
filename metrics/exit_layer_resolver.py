from typing import List
from prog.action_processor.state.stack_schema import StackElem


class ExitLayerResolver:

    def __init__(self, side: str):
        self.side = side


    def resolve_close_levels(
        self,
        entries: List[StackElem],
        price: float
    ) -> List[StackElem]:

        sorted_entries = self._sort_stack(entries)

        return self._filter_profitable(sorted_entries, price)


    def _sort_stack(self, entries):

        if self.side == "Sell":
            return sorted(entries, key=lambda x: -x.price)

        return sorted(entries, key=lambda x: x.price)


    def _filter_profitable(self, entries, price):

        fee_total = 4 * 0.00055

        result = []

        for e in entries:

            if self.side == "Sell":

                if price < e.price * (1 - fee_total):
                    result.append(e)

            else:

                if price > e.price * (1 + fee_total):
                    result.append(e)

        return result