from enum import Enum

from action_processor.state.stack_schema import StackElem
from action_resolver.hedge_2_strategy.close_band_calculator import (
    Band,
    CloseBandCalculator,
)
from action_resolver.hedge_2_strategy.alternative_search import AlternativeSearchService
from action_resolver.hedge_2_strategy.level_selector import LevelSelector


class PriceLocation(Enum):
    PROFIT = "PROFIT"
    IN_BAND = "IN_BAND"
    LOSS = "LOSS"


class LosingLevelProcessor:
    def __init__(
        self,
        hedge_side: str,
        close_band_calculator: CloseBandCalculator,
        level_selector: LevelSelector,
        alternative_search_service: AlternativeSearchService,
        logger,
    ):
        self.hedge_side = hedge_side
        self.close_band_calculator = close_band_calculator
        self.level_selector = level_selector
        self.alternative_search_service = alternative_search_service
        self.logger = logger

    def process(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
        optimization_result_cls,
    ) -> "OptimizationResult":
        # Получаем следующий по уменьшению убытка уровень
        next_less_losing_level = self.level_selector.get_next_less_losing_level(
            losing_level,
            sorted_levels,
        )

        if next_less_losing_level is None:
            return optimization_result_cls(
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

        # self.logger.info(
        #     f"[OPT] CLOSE ANALYSIS | "
        #     f"side={self.hedge_side} | "
        #     f"price={cur_price:.8f} | "
        #     f"band=[{close_band.low:.8f}, {close_band.high:.8f}] | "
        #     f"location={price_location.value} | "
        #     f"losing={losing_level.price:.8f}/{losing_level.qty} | "
        #     f"next_less_losing={next_less_losing_level.price:.8f}/"
        #     f"{next_less_losing_level.qty}"
        # )

        # Анализируем price_location и предпринимаем соответствующие действия
        result = self._process_price_location(
            price_location,
            losing_level,
            next_less_losing_level,
            sorted_levels,
            cur_price,
            close_band,
            optimization_result_cls,
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

    def _process_price_location(
        self,
        price_location: PriceLocation,
        losing_level: StackElem,
        next_less_losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
        close_band: Band,
        optimization_result_cls,
    ) -> "OptimizationResult":

        # Если цена в прибыли -> прекращаем поиск
        if price_location == PriceLocation.PROFIT:
            return optimization_result_cls(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=close_band,
            )

        # Если цена внутри close_band -> закрываемся и выходим
        if price_location == PriceLocation.IN_BAND:
            qty = losing_level.qty + next_less_losing_level.qty

            self._log_normal_close(losing_level, next_less_losing_level, cur_price, close_band, qty)

            return optimization_result_cls(
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
                optimization_result_cls,
            )

            res.band = close_band

            self._log_alternative_close(cur_price, close_band, res)

            return res

        raise ValueError(f"Unsupported price location: {price_location}")

    def _find_alternative_close(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        current_price: float,
        optimization_result_cls,
    ) -> "OptimizationResult":
        alternative_profitable_level = (
            self.alternative_search_service.find_alternative_profitable_level(
                losing_level,
                sorted_levels,
                current_price,
            )
        )

        if alternative_profitable_level is None:
            return optimization_result_cls(
                found=False,
                continue_search=True,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=None,
            )

        qty = losing_level.qty + alternative_profitable_level.qty

        return optimization_result_cls(
            found=True,
            continue_search=False,
            losing_level=losing_level,
            profitable_level=alternative_profitable_level,
            qty=qty,
            band=None,
        )

    def _log_alternative_close(self, cur_price, close_band, res):
        if res.found:
            self.logger.info(
                f"[OPT] CLOSE DECISION | "
                f"branch=ALTERNATIVE | "
                f"price={cur_price:.8f} | "
                f"band=[{close_band.low:.8f}, {close_band.high:.8f}] | "
                f"losing={res.losing_level.price:.8f}/"
                f"{res.losing_level.qty} | "
                f"profitable={res.profitable_level.price:.8f}/"
                f"{res.profitable_level.qty} | "
                f"qty={res.qty}"
            )

    def _log_normal_close(self, losing_level, next_less_losing_level, cur_price, close_band, qty):
        self.logger.info(
            f"[OPT] CLOSE DECISION | "
            f"branch=IN_BAND | "
            f"price={cur_price:.8f} | "
            f"band=[{close_band.low:.8f}, {close_band.high:.8f}] | "
            f"losing={losing_level.price:.8f}/{losing_level.qty} | "
            f"profitable={next_less_losing_level.price:.8f}/"
            f"{next_less_losing_level.qty} | "
            f"qty={qty}"
        )