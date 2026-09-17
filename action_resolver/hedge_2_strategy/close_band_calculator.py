from action_processor.state.stack_schema import StackElem
from dataclasses import dataclass

@dataclass
class Band:
    low: float
    high: float    


class CloseBandCalculator:
    def __init__(
        self,
        hedge_side: str,
        fee_taker: float,
        profit_tolerance: float,
    ):
        self.hedge_side = hedge_side
        self.fee_taker = fee_taker
        self.profit_tolerance = profit_tolerance

    def calculate(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
    ):
        # Получаем цену безубытка с учетом комиссий
        breakeven_price = self._calculate_fee_adjusted_breakeven_price(
            losing_level,
            profitable_level,
        )

        # Добавляем к цене безубытка запас на прибыль
        min_profit_buffer = 0.001
        fee_min_profit_price = self._adjust_breakeven_for_profit_buffer(
            breakeven_price,
            min_profit_buffer,
        )

        # Вычисляем close band и возвращаем его
        return self._build_close_band(fee_min_profit_price)

    def _build_close_band(self, fee_min_profit_price: float) -> Band:
        if self.hedge_side == "Buy":
            return Band(
                low=fee_min_profit_price,
                high=fee_min_profit_price * (1 + self.profit_tolerance),
            )

        if self.hedge_side == "Sell":
            return Band(
                low=fee_min_profit_price * (1 - self.profit_tolerance),
                high=fee_min_profit_price,
            )

        raise ValueError(f"Unsupported side: {self.hedge_side}")    

    def _calculate_fee_adjusted_breakeven_price(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
    ) -> float:
        # Вычисляем и контроллируем суммарный размер уровней
        total_qty = losing_level.qty + profitable_level.qty
        if total_qty <= 0:
            raise ValueError(
                f"Invalid pair qty: "
                f"losing={losing_level.qty}, "
                f"profitable={profitable_level.qty}"
            )

        # Вычисляем суммарную цену
        total_value = (
            losing_level.price * losing_level.qty
            + profitable_level.price * profitable_level.qty
        )

        if self.hedge_side == "Buy":
            return (
                total_value * (1 + self.fee_taker)
                / (total_qty * (1 - self.fee_taker))
            )

        if self.hedge_side == "Sell":
            return (
                total_value * (1 - self.fee_taker)
                / (total_qty * (1 + self.fee_taker))
            )

        raise ValueError(f"Unsupported side: {self.hedge_side}")

    def _adjust_breakeven_for_profit_buffer(
        self,
        breakeven_price: float,
        min_profit_buffer: float,
    ) -> float:
        if self.hedge_side == "Buy":
            return breakeven_price * (1 + min_profit_buffer)

        if self.hedge_side == "Sell":
            return breakeven_price * (1 - min_profit_buffer)

        raise ValueError(f"Unsupported side: {self.hedge_side}")