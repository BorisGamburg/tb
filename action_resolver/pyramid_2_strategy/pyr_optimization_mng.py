from dataclasses import dataclass

from action_processor.state.stack_schema import StackElem
from action_resolver.pyramid_2_strategy.pyr_close_band_calculator import (
    Band,
    PyrCloseBandCalculator,
)
from action_resolver.pyramid_2_strategy.pyr_close_result_calculator import (
    PyrCloseResultCalculator,
)
from action_resolver.pyramid_2_strategy.pyr_alternative_search import PyrAlternativeSearchService
from action_resolver.pyramid_2_strategy.pyr_level_selector import PyrLevelSelector
from action_resolver.pyramid_2_strategy.pyr_losing_level_processor import PyrLosingLevelProcessor
from action_resolver.pyramid_2_strategy.pyr_band_cross_close_calculator import (
    PyrBandCrossCloseCalculator,
    PyrBandCrossCloseResult,
)


@dataclass
class PyrOptimizationResult:
    found: bool
    continue_search: bool
    losing_level: StackElem | None
    profitable_level: StackElem | None
    qty: float
    band: Band | None = None
    band_cross_plan: PyrBandCrossCloseResult | None = None

class PyrOptimizationMng:
    def __init__(
        self,
        state,
        price_service,
        fee_taker: float,
        trading_info,
        logger,
    ):
        self.state = state
        self.price_service = price_service
        self.hedge_side = state.data.side
        self.fee_taker = fee_taker
        self.logger = logger

        self.level_selector = PyrLevelSelector(hedge_side=self.hedge_side)

        self.close_band_calculator = PyrCloseBandCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
            profit_tolerance=state.data.close_band_width_pct / 100,
        )

        self.band_cross_calculator = PyrBandCrossCloseCalculator(
            hedge_side=self.hedge_side,
            trading_info=trading_info,
        )

        self.previous_price = None
        self.previous_pair_key = None        

        self.close_result_calculator = PyrCloseResultCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
        )

        self.alternative_search_service = PyrAlternativeSearchService(
            close_result_calculator=self.close_result_calculator,
            hedge_side=self.hedge_side,
            logger=logger
        )

        self.losing_level_processor = PyrLosingLevelProcessor(
            hedge_side=self.hedge_side,
            close_band_calculator=self.close_band_calculator,
            level_selector=self.level_selector,
            alternative_search_service=self.alternative_search_service,
            logger=self.logger,
        )

    def check(self) -> PyrOptimizationResult:
        current_price, sorted_levels, losing_levels = self._prepare_data()

        band_cross_result = self._check_band_cross(
            current_price,
            sorted_levels,
        )

        if band_cross_result is not None:
            return band_cross_result

        last_band = None

        for losing_level in losing_levels:
            result = self.losing_level_processor.process(
                losing_level=losing_level,
                sorted_levels=sorted_levels,
                cur_price=current_price,
                optimization_result_cls=PyrOptimizationResult,
            )

            if result.band:
                last_band = result.band

            if result.found or not result.continue_search:
                return result

        return PyrOptimizationResult(
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

    def _check_band_cross(
        self,
        current_price: float,
        sorted_levels: list[StackElem],
    ) -> PyrOptimizationResult | None:
        # Проверяем только пару из двух уровней
        if len(sorted_levels) != 2:
            self.previous_price = None
            self.previous_pair_key = None
            return None

        # Для Buy: первый уровень убыточный, второй прибыльный.
        # Для Sell: первый уровень убыточный, второй прибыльный.
        losing_level, profitable_level = sorted_levels

        # Идентификатор текущей пары.
        # Любое изменение уровней сбрасывает предыдущую цену.
        pair_key = tuple(
            (level.price, level.qty, level.fee, level.initial_qty)
            for level in sorted_levels
        )

        band = self.close_band_calculator.calculate(
            losing_level,
            profitable_level,
        )

        # Новая пара: только устанавливаем начальную цену
        if pair_key != self.previous_pair_key:
            self.previous_pair_key = pair_key
            self.previous_price = current_price
            return None

        previous_price = self.previous_price
        self.previous_price = current_price

        if previous_price is None:
            return None

        # Проверяем полное пересечение Close Band
        if self.hedge_side == "Buy":
            crossed = (
                previous_price > band.high
                and current_price < band.low
            )
        else:
            crossed = (
                previous_price < band.low
                and current_price > band.high
            )

        if not crossed:
            return None

        # Рассчитываем безопасный план закрытия
        plan = self.band_cross_calculator.calculate(
            profitable_level=profitable_level,
            losing_level=losing_level,
            close_price=current_price,
        )

        self.logger.info(
            f"[OPT] BAND CROSS | "
            f"side={self.hedge_side} | "
            f"previous={previous_price:.8f} | "
            f"current={current_price:.8f} | "
            f"band=[{band.low:.8f}, {band.high:.8f}] | "
            f"plan_found={plan.found}"
        )

        # Пересечение обнаружено, но безопасное закрытие невозможно.
        # Возвращаем found=False, чтобы обычное закрытие не выполнялось.
        if not plan.found:
            return PyrOptimizationResult(
                found=False,
                continue_search=False,
                losing_level=None,
                profitable_level=None,
                qty=0,
                band=band,
            )

        return PyrOptimizationResult(
            found=True,
            continue_search=False,
            losing_level=losing_level,
            profitable_level=profitable_level,
            qty=plan.total_qty,
            band=band,
            band_cross_plan=plan,
        )    