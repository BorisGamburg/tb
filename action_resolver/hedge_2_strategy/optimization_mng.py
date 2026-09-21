from dataclasses import dataclass

from action_processor.state.stack_schema import StackElem
from action_resolver.hedge_2_strategy.close_band_calculator import (
    Band,
    CloseBandCalculator,
)
from action_resolver.hedge_2_strategy.close_result_calculator import (
    CloseResultCalculator,
)
from action_resolver.hedge_2_strategy.alternative_search import AlternativeSearchService
from action_resolver.hedge_2_strategy.level_selector import LevelSelector
from action_resolver.hedge_2_strategy.losing_level_processor import LosingLevelProcessor


@dataclass
class OptimizationResult:
    found: bool
    continue_search: bool
    losing_level: StackElem | None
    profitable_level: StackElem | None
    qty: float
    band: Band | None = None


class OptimizationMng:
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

        self.level_selector = LevelSelector(hedge_side=self.hedge_side)

        self.close_band_calculator = CloseBandCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
            profit_tolerance=state.data.profit_tolerance_pct / 100,
        )

        self.close_result_calculator = CloseResultCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
        )

        self.alternative_search_service = AlternativeSearchService(
            close_result_calculator=self.close_result_calculator,
            hedge_side=self.hedge_side,
            logger=logger
        )

        self.losing_level_processor = LosingLevelProcessor(
            hedge_side=self.hedge_side,
            close_band_calculator=self.close_band_calculator,
            level_selector=self.level_selector,
            alternative_search_service=self.alternative_search_service,
            logger=self.logger,
        )

    def check(self) -> OptimizationResult:
        current_price, sorted_levels, losing_levels = self._prepare_data()

        last_band = None
        for losing_level in losing_levels:
            result = self.losing_level_processor.process(
                losing_level=losing_level,
                sorted_levels=sorted_levels,
                cur_price=current_price,
                optimization_result_cls=OptimizationResult,
            )

            if result.band:
                last_band = result.band

            if result.found or not result.continue_search:
                return result

        return OptimizationResult(
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