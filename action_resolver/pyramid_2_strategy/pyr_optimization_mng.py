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
from action_resolver.pyramid_2_strategy.pyr_pair_close_calculator import (
    PyrPairCloseCalculator,
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

        self.pair_close_calculator = PyrPairCloseCalculator(
            hedge_side=self.hedge_side,
            trading_info=trading_info,
        )

        self.previous_price: float | None = None

        self.close_result_calculator = PyrCloseResultCalculator(
            hedge_side=self.hedge_side,
            fee_taker=self.fee_taker,
        )

        self.alternative_search_service = PyrAlternativeSearchService(
            close_result_calculator=self.close_result_calculator,
            hedge_side=self.hedge_side,
            logger=logger
        )

    def check(self) -> PyrOptimizationResult:
        current_price, sorted_levels = self._prepare_data()

        previous_price = self.previous_price
        self.previous_price = current_price

        # Проверяем, находится ли текущая цена внутри Close Band.
        inside_band_result = self._check_price_inside_close_band(
            current_price,
            sorted_levels,
        )
        if inside_band_result is not None:
            return inside_band_result

        # Проверяем пересечение Close Band между предыдущей и текущей ценой.
        close_band_within_result = self._check_close_band_within(
            previous_price,
            current_price,
            sorted_levels,
        )
        if close_band_within_result is not None:
            return close_band_within_result

        return PyrOptimizationResult(
            found=False,
            continue_search=False,
            losing_level=None,
            profitable_level=None,
            qty=0,
        )

    def _prepare_data(self) -> tuple[float, list[StackElem]]:
        current_price = self.price_service.get_active_price(
            self.state.data.symbol,
            self.hedge_side,
        )

        sorted_levels = self.level_selector.get_sorted_levels(
            self.state.stack_mng.data.entries
        )

        return current_price, sorted_levels

    def _check_close_band_within(
        self,
        previous_price: float | None,
        current_price: float,
        sorted_levels: list[StackElem],
    ) -> PyrOptimizationResult | None:
        if previous_price is None:
            return None

        # Ищем Close Band, который находится между предыдущей и текущей ценой.
        close_band_within = self._get_close_band_within(
            previous_price,
            current_price,
            sorted_levels,
        )
        if close_band_within is None:
            # Close Band не найден -> выходим
            return None

        # Рассчитываем безопасный план закрытия выбранной пары.
        (losing_level, profitable_level, band), crossed_bands_count = (
            close_band_within
        )
        plan = self.pair_close_calculator.calculate(
            profitable_level=profitable_level,
            losing_level=losing_level,
            close_price=current_price,
        )

        # Если безопасный план не найден, пробуем альтернативное закрытие.
        if not plan.found:
            return self._try_alternative_close(
                losing_level=losing_level,
                sorted_levels=sorted_levels,
                current_price=current_price,
                band=band,
            )

        # Лог
        self.logger.info(
            f"[OPT] BAND CROSS | "
            f"side={self.hedge_side} | "
            f"previous={previous_price:.8f} | "
            f"current={current_price:.8f} | "
            f"band=[{band.low:.8f}, {band.high:.8f}] | "
            f"losing={losing_level.price:.8f} | "
            f"profitable={profitable_level.price:.8f} | "
            f"crossed_bands={crossed_bands_count} | "
            f"plan_found={plan.found}"
        )

        # Безопасный план найден -> возвращаем результат.
        return PyrOptimizationResult(
            found=True,
            continue_search=False,
            losing_level=losing_level,
            profitable_level=profitable_level,
            qty=plan.total_qty,
            band=band,
            band_cross_plan=plan,
        )

    def _try_alternative_close(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        current_price: float,
        band: Band,
    ) -> PyrOptimizationResult:
        alternative_level = (
            self.alternative_search_service.find_alternative_profitable_level(
                losing_level,
                sorted_levels,
                current_price,
            )
        )

        if alternative_level is None:
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
            profitable_level=alternative_level,
            qty=losing_level.qty + alternative_level.qty,
            band=band,
        )

    def _get_close_band_within(
        self,
        previous_price: float,
        current_price: float,
        sorted_levels: list[StackElem],
    ) -> tuple[tuple[StackElem, StackElem, Band], int] | None:
        close_bands_within = self._find_close_bands_within(
            previous_price,
            current_price,
            sorted_levels,
        )

        if not close_bands_within:
            return None

        return (
            self._select_outermost_close_band(close_bands_within),
            len(close_bands_within),
        )

    def _select_outermost_close_band(
        self,
        crossed_close_bands: list[tuple[StackElem, StackElem, Band]],
    ) -> tuple[StackElem, StackElem, Band]:
        if self.hedge_side == "Buy":
            return min(
                crossed_close_bands,
                key=lambda pair: pair[2].low,
            )

        return max(
            crossed_close_bands,
            key=lambda pair: pair[2].high,
        )

    def _find_close_bands_within(
        self,
        previous_price: float,
        current_price: float,
        sorted_levels: list[StackElem],
    ) -> list[tuple[StackElem, StackElem, Band]]:
        crossed_close_bands = []

        # Проверяем Close Band всех соседних пар уровней.
        for losing_level, profitable_level in zip(
            sorted_levels,
            sorted_levels[1:],
        ):
            # Рассчитываем Close Band для текущей пары уровней.
            band = self.close_band_calculator.calculate(
                losing_level,
                profitable_level,
            )

            # Проверяем, находится ли  close_band между предыдущей и текущей ценой.
            if self.hedge_side == "Buy":
                within = (
                    previous_price > band.high
                    and current_price < band.low
                )
            elif self.hedge_side == "Sell":
                within = (
                    previous_price < band.low
                    and current_price > band.high
                )
            else:
                raise ValueError(
                    f"Unsupported side: {self.hedge_side}"
                )

            # Если close_band  внутри, то добавляем его в список
            if within:
                crossed_close_bands.append(
                    (losing_level, profitable_level, band)
                )

        return crossed_close_bands

    def _check_price_inside_close_band(
        self,
        current_price: float,
        sorted_levels: list[StackElem],
    ) -> PyrOptimizationResult | None:
        # Проверяем Close Bands всех соседних пар уровней.
        for losing_level, profitable_level in zip(
            sorted_levels,
            sorted_levels[1:],
        ):
            # Рассчитываем Close Band для текущей пары.
            band = self.close_band_calculator.calculate(
                losing_level,
                profitable_level,
            )

            # Если цена вне Close Band, переходим к следующей паре.
            if not band.low <= current_price <= band.high:
                continue

            plan = self.pair_close_calculator.calculate(
                profitable_level=profitable_level,
                losing_level=losing_level,
                close_price=current_price,
            )

            if not plan.found:
                return PyrOptimizationResult(
                    found=False,
                    continue_search=False,
                    losing_level=None,
                    profitable_level=None,
                    qty=0,
                    band=band,
                    band_cross_plan=plan,
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

        return None