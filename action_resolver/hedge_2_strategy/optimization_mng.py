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

class PriceLocation(Enum):
    PROFIT = "PROFIT"
    IN_BAND = "IN_BAND"
    LOSS = "LOSS"    

class OptimizationMng:
    def __init__(
        self,
        state,
        price_service,
        fee_taker: float,
        logger
    ):
        self.state = state
        self.price_service = price_service
        self.hedge_side = state.data.side
        self.fee_taker = fee_taker
        self.logger = logger

        self.close_band_calculator = CloseBandCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
            profit_tolerance=state.data.profit_tolerance_pct / 100,
        )   

        self.close_result_calculator = CloseResultCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
        )         

    def _get_losing_levels(
        self,
        levels,
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

    def _get_sorted_levels(self) -> list[StackElem]:
        return sorted(
            self.state.stack_mng.data.entries,
            key=lambda entry: entry.price,
            reverse=self.hedge_side == "Buy",
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

    def _get_price_location(
        self,
        cur_price: float,
        close_band: Band,
    ) -> PriceLocation:
        if self.hedge_side == "Sell":
            if cur_price < close_band.low:
                return PriceLocation.PROFIT

            if cur_price > close_band.high:
                return PriceLocation.LOSS

        elif self.hedge_side == "Buy":
            if cur_price > close_band.high:
                return PriceLocation.PROFIT

            if cur_price < close_band.low:
                return PriceLocation.LOSS

        else:
            raise ValueError(f"Unsupported side: {self.hedge_side}")

        return PriceLocation.IN_BAND    

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
        if self.hedge_side == "Sell":
            return [
                level for level in levels
                if level.price > current_price
            ]

        if self.hedge_side == "Buy":
            return [
                level for level in levels
                if level.price < current_price
            ]

        raise ValueError(f"Unsupported side: {self.hedge_side}")

    def _is_close_result_acceptable(
        self,
        close_result: float,
    ) -> bool:
        return close_result >= 0

    def check(self) -> OptimizationResult:
        # Получаем тек цену
        current_price = self.price_service.get_active_price(
            self.state.data.symbol,
            self.hedge_side,
        )

        # Получаем отсортированные по возрастанию прибыли (уменьшению убытка) уровни
        sorted_levels = self._get_sorted_levels()

        # Получаем отсортированные по уменьшению убытка убыточные уровни
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

            # Если подходящий прибыльный уровень найден -> выходим
            if result.found:
                return result

            # Подходящий прибыльный уровень не найден, 
            # смотрим надо ли продолжать поиск
            if not result.continue_search:
                return result

        # Ничего не найдено -> выходим
        return OptimizationResult(
            found=False,
            continue_search=False,
            losing_level=None,
            profitable_level=None,
            qty=0,
            band=result.band
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

        # Если альтернативный прибыльный уровень не найден -> выходим и сообщаем 
        # что прибыльный уровень не найден и надо продолжать поиск для следующего убыточного уровня
        if alternative_profitable_level is None:
            return OptimizationResult(
                found=False,
                continue_search=True,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=None, 
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
            band=None,  
        )    

    def _find_alternative_profitable_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
    ) -> StackElem | None:
        # Получаем прибыльные уровни
        profitable_levels = self._get_profitable_levels(
            sorted_levels,
            cur_price,
        )

        # Проходим по прибыльным уровням и ищем тот который закроет losing_level в прибыль
        for profit_level in profitable_levels:
            # Вычисляем netto pnl при закрытии пары
            close_pair_netto_pnl = self.close_result_calculator.calc_netto_pnl(
                losing_level,
                profit_level,
                cur_price
            )

            # Если результат закрытия устраивает -> выходим и возвращаем найденный прибыльный уровень
            if self._is_close_result_acceptable(close_pair_netto_pnl):
                return profit_level

        # Подходящий прибыльный уровень не найден -> выходим
        return None    


    def _process_losing_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
    ) -> OptimizationResult:

        # Получаем следующий по уменьшению убытка уровень
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
                band=None,
            )

        # Вычисляем close_band
        close_band = self.close_band_calculator.calculate(
            losing_level,
            next_less_losing_level,
        )

        # Получаем положение цены относительно close_band
        price_location = self._get_price_location(
            cur_price,
            close_band,
        )

        # Анализируем price_location и предпринимаем соответствующие действия
        result = self._process_price_location(
            price_location,
            losing_level,
            next_less_losing_level,
            sorted_levels,
            cur_price,
            close_band,
        )

        if result.losing_level is not None:
            self.logger.info(
                f"[OPT] PROCESS RESULT | "
                f"losing={result.losing_level.price:.8f}/{result.losing_level.qty}"
            )

        if result.profitable_level is not None:
            self.logger.info(
                f"[OPT] PROCESS RESULT | "
                f"profitable={result.profitable_level.price:.8f}/"
                f"{result.profitable_level.qty}"
            )

        return result    

    def _process_price_location(
        self,
        price_location: PriceLocation,
        losing_level: StackElem,
        next_less_losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
        close_band: Band,
    ) -> OptimizationResult:

        # Если цена в прибыли, то значит прибыльный уровень не найден и
        # можно прекращать поиск
        if price_location == PriceLocation.PROFIT:
            return OptimizationResult(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=close_band,
            )

        # Если цена внутри close_band -> закрываемся и выходим
        if price_location == PriceLocation.IN_BAND:
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
                band=close_band,
            )

        # Если цена в убытке -> ищем альтернативное закрытие
        if price_location == PriceLocation.LOSS:
            res = self._find_alternative_close(
                losing_level,
                sorted_levels,
                cur_price,
            )

            res.band = close_band

            return res

        raise ValueError(
            f"Unsupported price location: {price_location}"
        )    