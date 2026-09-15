from action_processor.state.stack_schema import StackElem
from dataclasses import dataclass

@dataclass
class Band:
    low: float
    high: float    


class CloseBandCalculator:
    def __init__(
        self,
        side: str,
        fee_taker: float,
        profit_tolerance: float,
    ):
        self.side = side
        self.fee_taker = fee_taker
        self.profit_tolerance = profit_tolerance

    def calculate(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
    ):
        breakeven_price = self._calculate_fee_adjusted_breakeven_price(
            losing_level,
            profitable_level,
        )

        min_profit_buffer = 0.001
        close_price = self._adjust_breakeven_for_profit_buffer(
            breakeven_price,
            min_profit_buffer,
        )

        if self.side == "Sell":
            return Band(
                low=close_price,
                high=close_price * (1 + self.profit_tolerance),
            )

        if self.side == "Buy":
            return Band(
                low=close_price * (1 - self.profit_tolerance),
                high=close_price,
            )

        raise ValueError(f"Unsupported side: {self.side}")

    def _calculate_fee_adjusted_breakeven_price(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
    ) -> float:
        total_qty = losing_level.qty + profitable_level.qty

        if total_qty <= 0:
            raise ValueError(
                f"Invalid pair qty: "
                f"losing={losing_level.qty}, "
                f"profitable={profitable_level.qty}"
            )

        total_value = (
            losing_level.price * losing_level.qty
            + profitable_level.price * profitable_level.qty
        )

        if self.side == "Sell":
            return (
                total_value * (1 + self.fee_taker)
                / (total_qty * (1 - self.fee_taker))
            )

        if self.side == "Buy":
            return (
                total_value * (1 - self.fee_taker)
                / (total_qty * (1 + self.fee_taker))
            )

        raise ValueError(f"Unsupported side: {self.side}")

    def _adjust_breakeven_for_profit_buffer(
        self,
        breakeven_price: float,
        min_profit_buffer: float,
    ) -> float:
        if self.side == "Sell":
            return breakeven_price * (1 + min_profit_buffer)

        if self.side == "Buy":
            return breakeven_price * (1 - min_profit_buffer)

        raise ValueError(f"Unsupported side: {self.side}")