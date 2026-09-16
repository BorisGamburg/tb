from enum import Enum
from dataclasses import dataclass

from action_processor.state.stack_schema import StackElem
from action_resolver.hedge_2_strategy.close_band_calculator import (
    Band,
    CloseBandCalculator,
)
from action_resolver.hedge_2_strategy.close_result_calculator import (
    CloseResultCalculator,
)


@dataclass
class OptimizationResult:
    found: bool
    continue_search: bool
    losing_level: StackElem | None
    profitable_level: StackElem | None
    qty: float
    band: Band | None = None  # <--- Добавили поле

class PricePosition(Enum):
    PROFIT = "PROFIT"
    IN_BAND = "IN_BAND"
    LOSS = "LOSS"    

class OptimizationMng:
    def __init__(
        self,
        state,
        price_service,
        fee_taker: float,
    ):
        self.state = state
        self.price_service = price_service
        self.side = state.data.side
        self.fee_taker = fee_taker

        self.close_band_calculator = CloseBandCalculator(
            side=self.side,
            fee_taker=self.fee_taker,
            profit_tolerance=state.data.profit_tolerance_pct / 100,
        )   

        self.close_result_calculator = CloseResultCalculator(
            side=self.side,
            fee_taker=self.fee_taker,
        )         

    def _get_losing_levels(
        self,
        levels,
        current_price: float,
    ) -> list[StackElem]:
        if self.side == "Buy":
            return [
                level for level in levels
                if level.price < current_price
            ]

        if self.side == "Sell":
            return [
                level for level in levels
                if level.price > current_price
            ]

        raise ValueError(f"Unsupported side: {self.side}")

    def _get_sorted_levels(self) -> list[StackElem]:
        return sorted(
            self.state.stack_mng.data.entries,
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

    def _get_profitable_levels(
        self,
        levels: list[StackElem],
        current_price: float,
    ) -> list[StackElem]:
        if self.side == "Buy":
            return [
                level for level in levels
                if level.price > current_price
            ]

        if self.side == "Sell":
            return [
                level for level in levels
                if level.price < current_price
            ]

        raise ValueError(f"Unsupported side: {self.side}")

    def _calculate_close_result(
        self,
        losing_level: StackElem,
        profitable_level: StackElem,
        cur_price: float
    ):
        return self.close_result_calculator.calculate(
            losing_level,
            profitable_level,
            cur_price
        )

    def _is_close_result_acceptable(
        self,
        close_result: float,
    ) -> bool:
        return close_result >= 0

    def check(self) -> OptimizationResult:
        # Получаем тек цену
        current_price = self.price_service.get_active_price(
            self.state.data.symbol,
            self.side,
        )

        # Получаем отсортированные по возрастанию прибыли (уменьшению убытка) уровни
        sorted_levels = self._get_sorted_levels()

        # Получаен отсортированные по уменьшению убытка убыточные уровни
        losing_levels = self._get_losing_levels(
            sorted_levels,
            current_price,
        )

        # Проходим по убыточным уровням и проверяем можно ли их закрыть
        for losing_level in losing_levels:
            # Проверяем можно ли закрыть этот конкретный убыточный уровень
            result = self._process_losing_level(
                losing_level,
                sorted_levels,
                current_price,
            )

            # Если подходящий прибыльный уровеня найден -> выходим
            if result.found:
                return result

            # Подходящий прибыльный уровень не найден, 
            # смотрим надо ли продолжаль поиск
            if not result.continue_search:
                return result

        # Ничего не найдено -> выходим
        return OptimizationResult(
            found=False,
            continue_search=False,
            losing_level=None,
            profitable_level=None,
            qty=0,
        )

    def _find_alternative_close(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        current_price: float,
    ) -> OptimizationResult:
        # Ищем альтернативный прибыльный уровень
        alternative_profitable_level = (
            self._find_alternative_profitable_level(
                losing_level,
                sorted_levels,
                current_price,
            )
        )

        # Если альтернативный прибыльный уровень не найден -> выходим
        if alternative_profitable_level is None:
            return OptimizationResult(
                found=False,
                continue_search=True,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=None,  # <--- Указали дефолтный band
            )

        # Альтернативный прибыльный уровень найден
        # Вычисляем размер ордера для закрытия
        qty = self._calculate_close_qty(
            losing_level,
            alternative_profitable_level,
        )

        # Возвращаем результат
        return OptimizationResult(
            found=True,
            continue_search=False,
            losing_level=losing_level,
            profitable_level=alternative_profitable_level,
            qty=qty,
            band=None,  # <--- Указали дефолтный band
        )    

    def _process_losing_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        current_price: float,
    ) -> OptimizationResult:

        next_less_losing_level = self._get_next_less_losing_level(
            losing_level,
            sorted_levels,
        )


        if next_less_losing_level is None:
            return OptimizationResult(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=None,  # <--- ДОБАВЛЕНО
            )

        close_band = self.close_band_calculator.calculate(
            losing_level,
            next_less_losing_level,
        )

        price_position = self._get_price_position(
            current_price,
            close_band,
        )


        if price_position == PricePosition.PROFIT:
            return OptimizationResult(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=close_band,
            )

        if price_position == PricePosition.IN_BAND:
            qty = self._calculate_close_qty(
                losing_level,
                next_less_losing_level,
            )
            return OptimizationResult(
                found=True,
                continue_search=False,
                losing_level=losing_level,
                profitable_level=next_less_losing_level,
                qty=qty,
                band=close_band,  # <--- ДОБАВЛЕНО
            )

        if price_position == PricePosition.LOSS:
            res = self._find_alternative_close(
                losing_level,
                sorted_levels,
                current_price,
            )
            res.band = close_band  # <--- ДОБАВЛЕНО
            return res

        raise ValueError(f"Unsupported price position: {price_position}")    

    def _find_alternative_profitable_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
    ) -> StackElem | None:
        profitable_levels = self._get_profitable_levels(
            sorted_levels,
            cur_price,
        )

        for profitable_level in profitable_levels:
            close_result = self._calculate_close_result(
                losing_level,
                profitable_level,
                cur_price
            )

            if self._is_close_result_acceptable(close_result):
                return profitable_level

        return None    