from enum import Enum
from dataclasses import dataclass

from action_processor.state.stack_mng import StackMng
from action_processor.state.stack_schema import StackElem
from action_processor.close_opportunity.close_band_calculator import (
    Band,
    CloseBandCalculator,
)
from action_processor.close_opportunity.close_result_calculator import (
    CloseResultCalculator,
)


@dataclass
class CloseOpportunityResult:
    found: bool
    continue_search: bool
    losing_level: StackElem | None
    profitable_level: StackElem | None
    qty: float

class PricePosition(Enum):
    PROFIT = "PROFIT"
    IN_BAND = "IN_BAND"
    LOSS = "LOSS"    

class CloseOpportunity:
    def __init__(
        self,
        stack: StackMng,
        current_price: float,
        side: str,
        fee_taker: float,
        profit_tolerance: float,
    ):
        self.stack = stack
        self.current_price = current_price
        self.side = side

        self.close_band_calculator = CloseBandCalculator(
            side=side,
            fee_taker=fee_taker,
            profit_tolerance=profit_tolerance,
        )       

        self.close_result_calculator = CloseResultCalculator(
            current_price=current_price,
            side=side,
            fee_taker=fee_taker,
        )         

    def _get_losing_levels(self, levels) -> list[StackElem]:
        if self.side == "Buy":
            return [
                level for level in levels
                if level.price < self.current_price
            ]

        if self.side == "Sell":
            return [
                level for level in levels
                if level.price > self.current_price
            ]

        raise ValueError(f"Unsupported side: {self.side}")

    def _get_sorted_levels(self) -> list[StackElem]:
        return sorted(
            self.stack.data.entries,
            key=lambda entry: entry.price,
            reverse=self.side == "Sell",
        )    

    def _get_next_less_losing_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
    ) -> StackElem | None:
        index = sorted_levels.index(losing_level)

        if index + 1 >= len(sorted_levels):
            return None

        return sorted_levels[index + 1]

    def _get_price_position(
        self,
        current_price: float,
        close_band: Band,
    ) -> PricePosition:
        if self.side == "Buy":
            if current_price < close_band.low:
                return PricePosition.PROFIT

            if current_price > close_band.high:
                return PricePosition.LOSS

        elif self.side == "Sell":
            if current_price > close_band.high:
                return PricePosition.PROFIT

            if current_price < close_band.low:
                return PricePosition.LOSS

        else:
            raise ValueError(f"Unsupported side: {self.side}")

        return PricePosition.IN_BAND    

    def _calculate_close_qty(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
    ) -> float:
        return losing_level.qty + profitable_level.qty    

    def _find_alternative_profitable_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
    ) -> StackElem | None:
        profitable_levels = self._get_profitable_levels(
            sorted_levels,
        )

        for profitable_level in profitable_levels:
            close_result = self._calculate_close_result(
                losing_level,
                profitable_level,
            )

            if self._is_close_result_acceptable(close_result):
                return profitable_level

        return None

    def _get_profitable_levels(
        self,
        levels: list[StackElem],
    ) -> list[StackElem]:
        if self.side == "Buy":
            return [
                level for level in levels
                if level.price > self.current_price
            ]

        if self.side == "Sell":
            return [
                level for level in levels
                if level.price < self.current_price
            ]

        raise ValueError(f"Unsupported side: {self.side}")

    def _calculate_close_result(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
    ):
        return self.close_result_calculator.calculate(
            losing_level,
            profitable_level,
        )

    def _is_close_result_acceptable(
        self,
        close_result: float,
    ) -> bool:
        return close_result >= 0

    def find(self) -> CloseOpportunityResult:
        sorted_levels = self._get_sorted_levels()
        losing_levels = self._get_losing_levels(sorted_levels)

        for losing_level in losing_levels:
            result = self._process_losing_level(
                losing_level,
                sorted_levels,
            )

            if result.found:
                return result

            if not result.continue_search:
                return result

        return CloseOpportunityResult(
            found=False,
            continue_search=False,
            losing_level=None,
            profitable_level=None,
            qty=0,
        )

    def _process_losing_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
    ) -> CloseOpportunityResult:
        next_less_losing_level = self._get_next_less_losing_level(
            losing_level,
            sorted_levels,
        )

        if next_less_losing_level is None:
            return CloseOpportunityResult(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
            )

        close_band = self.close_band_calculator.calculate(
            losing_level,
            next_less_losing_level,
        )

        price_position = self._get_price_position(
            self.current_price,
            close_band,
        )

        if price_position == PricePosition.PROFIT:
            return CloseOpportunityResult(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
            )

        if price_position == PricePosition.IN_BAND:
            qty = self._calculate_close_qty(
                losing_level,
                next_less_losing_level,
            )
            return CloseOpportunityResult(
                found=True,
                continue_search=False,
                losing_level=losing_level,
                profitable_level=next_less_losing_level,
                qty=qty,
            )

        if price_position == PricePosition.LOSS:
            return self._find_alternative_close(
                losing_level,
                sorted_levels,
            )

        raise ValueError(f"Unsupported price position: {price_position}")    

    def _find_alternative_close(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
    ) -> CloseOpportunityResult:
        alternative_profitable_level = (
            self._find_alternative_profitable_level(
                losing_level,
                sorted_levels,
            )
        )

        if alternative_profitable_level is None:
            return CloseOpportunityResult(
                found=False,
                continue_search=True,
                losing_level=None,
                profitable_level=None,
                qty=0,
            )

        qty = self._calculate_close_qty(
            losing_level,
            alternative_profitable_level,
        )

        return CloseOpportunityResult(
            found=True,
            continue_search=False,
            losing_level=losing_level,
            profitable_level=alternative_profitable_level,
            qty=qty,
        )    