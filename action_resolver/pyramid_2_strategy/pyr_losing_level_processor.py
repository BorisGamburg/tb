from enum import Enum

from action_processor.state.stack_schema import StackElem
from action_resolver.pyramid_2_strategy.pyr_close_band_calculator import (
    Band,
    PyrCloseBandCalculator,
)
from action_resolver.pyramid_2_strategy.pyr_level_selector import PyrLevelSelector
from action_resolver.pyramid_2_strategy.pyr_pair_close_calculator import (
    PyrPairCloseCalculator,
)


class PriceLocation(Enum):
    PROFIT = "PROFIT"
    IN_BAND = "IN_BAND"
    LOSS = "LOSS"


class PyrLosingLevelProcessor:
    def __init__(
        self,
        hedge_side: str,
        close_band_calculator: PyrCloseBandCalculator,
        band_cross_calculator: PyrPairCloseCalculator,
        level_selector: PyrLevelSelector,
        logger,
    ):
        self.hedge_side = hedge_side
        self.close_band_calculator = close_band_calculator
        self.band_cross_calculator = band_cross_calculator
        self.level_selector = level_selector
        self.logger = logger

    def process(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
        optimization_result_cls,
    ) -> "PyrOptimizationResult":
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
        cur_price: float,
        close_band: Band,
        optimization_result_cls,
    ) -> "PyrOptimizationResult":

        if price_location == PriceLocation.PROFIT:
            return optimization_result_cls(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=close_band,
            )

        if price_location == PriceLocation.IN_BAND:
            plan = self.band_cross_calculator.calculate(
                profitable_level=next_less_losing_level,
                losing_level=losing_level,
                close_price=cur_price,
            )

            self.logger.info(
                f"[OPT] IN BAND | "
                f"price={cur_price:.8f} | "
                f"band=[{close_band.low:.8f}, {close_band.high:.8f}] | "
                f"plan_found={plan.found}"
            )

            if not plan.found:
                return optimization_result_cls(
                    found=False,
                    continue_search=True,
                    losing_level=None,
                    profitable_level=None,
                    qty=0,
                    band=close_band,
                )

            return optimization_result_cls(
                found=True,
                continue_search=False,
                losing_level=losing_level,
                profitable_level=next_less_losing_level,
                qty=plan.total_qty,
                band=close_band,
                band_cross_plan=plan,
            )

        if price_location == PriceLocation.LOSS:
            return optimization_result_cls(
                found=False,
                continue_search=True,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=close_band,
            )

        raise ValueError(f"Unsupported price location: {price_location}")
