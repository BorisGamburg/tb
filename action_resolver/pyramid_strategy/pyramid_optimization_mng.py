from dataclasses import dataclass

from action_processor.state.stack_schema import StackElem
from action_resolver.pyramid_strategy.pyramid_close_band_calculator import (
    Band,
    PyramidCloseBandCalculator,
)
from action_resolver.pyramid_strategy.pyramid_close_result_calculator import (
    PyramidCloseResultCalculator,
)
from action_resolver.pyramid_strategy.pyramid_alternative_search import PyramidAlternativeSearchService
from action_resolver.pyramid_strategy.pyramid_level_selector import PyramidLevelSelector
from action_resolver.pyramid_strategy.pyramid_losing_level_processor import PyramidLosingLevelProcessor


@dataclass
class PyramidOptimizationResult:
    found: bool
    continue_search: bool
    losing_level: StackElem | None
    profitable_level: StackElem | None
    qty: float
    band: Band | None = None


class PyramidOptimizationMng:
    def __init__(
        self,
        state,
        price_service,
        fee_taker: float,
        logger,
    ):
        self.state = state
        self.price_service = price_service
        self.hedge_side = state.data.side
        self.fee_taker = fee_taker
        self.logger = logger

        self.level_selector = PyramidLevelSelector(hedge_side=self.hedge_side)

        self.close_band_calculator = PyramidCloseBandCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
            profit_tolerance=state.data.close_band_width_pct / 100,
        )

        self.close_result_calculator = PyramidCloseResultCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
        )

        self.alternative_search_service = PyramidAlternativeSearchService(
            close_result_calculator=self.close_result_calculator,
            hedge_side=self.hedge_side,
            logger=logger
        )

        self.losing_level_processor = PyramidLosingLevelProcessor(
            hedge_side=self.hedge_side,
            close_band_calculator=self.close_band_calculator,
            level_selector=self.level_selector,
            alternative_search_service=self.alternative_search_service,
            logger=self.logger,
        )

    def check(self) -> PyramidOptimizationResult:
        current_price, sorted_levels, losing_levels = self._prepare_data()

        last_band = None
        for losing_level in losing_levels:
            result = self.losing_level_processor.process(
                losing_level=losing_level,
                sorted_levels=sorted_levels,
                cur_price=current_price,
                optimization_result_cls=PyramidOptimizationResult,
            )

            if result.band:
                last_band = result.band

            if result.found or not result.continue_search:
                return result

        return PyramidOptimizationResult(
            found=False,
            continue_search=False,
            losing_level=None,
            profitable_level=None,
            qty=0,
            band=last_band,
        )

    def _prepare_data(self):
        current_price = self.price_service.get_active_price(
            self.state.data.symbol,
            self.hedge_side,
        )

        sorted_levels = self.level_selector.get_sorted_levels(
            self.state.stack_mng.data.entries
        )

        losing_levels = self.level_selector.get_losing_levels(
            sorted_levels,
            current_price,
        )
        return current_price, sorted_levels, losing_levels