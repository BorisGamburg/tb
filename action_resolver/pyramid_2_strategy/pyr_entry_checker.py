from dataclasses import dataclass

from action_resolver.pyramid_2_strategy.pyr_base_level_entry_checker import (
    PyrBaseLevelEntryChecker,
)
from action_resolver.pyramid_2_strategy.pyr_extension_level_entry_checker import (
    PyrExtensionLevelEntryChecker,
)
from common.trading_info import TradingInfo
from services.bb_service import BBService
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_signal import (
    HAReversalSignal,
)

from common.ha_trend_checker import HATrendChecker
from common.level_distance_checker import is_level_distance_allowed
from action_resolver.pyramid_2_strategy.pyr_qty_calculator import PyrQtyCalculator
from action_resolver.pyramid_2_strategy.pyr_position_limit_checker import (
    is_position_limit_allowed,
)


@dataclass
class PyrdEntryResult:
    allowed: bool
    qty: float
    trend_active: bool
    distance_allowed: bool
    level_type: str | None
    qty_checked: bool = False
    raw_qty: float = 0.0
    position_limit_blocked: bool = False
    ha_breakout: bool = False

class PyrEntryChecker:

    def __init__(
        self,
        proxy_driver,
        symbol: str,
        side: str,
        step_pct: float,
        qty_pct: float,
        trading_info: TradingInfo,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side
        self.step_ratio = step_pct / 100

        self.qty_calculator = PyrQtyCalculator(
            proxy_driver=proxy_driver,
            symbol=symbol,
            qty_pct=qty_pct,
            trading_info=trading_info,
        )

        self.ha_trend = HATrendChecker(
            proxy_driver=proxy_driver,
            symbol=symbol,
            side=side,
        )

        self.ha_signal = HAReversalSignal(
            proxy_driver=proxy_driver,
            symbol=symbol,
        )

        self.bb_service = BBService(
            proxy_driver=proxy_driver,
            symbol=symbol,
        )

        self.base_level_checker = PyrBaseLevelEntryChecker(
            side=side,
            ha_signal=self.ha_signal,
            bb_service=self.bb_service,
        )

        self.extension_level_checker = PyrExtensionLevelEntryChecker(
            side=side,
        )

    def _get_pyramid_qty(self) -> float:
        _, qty = self.qty_calculator.calculate()
        return qty

    def check(self, entries, entry_tf: str) -> PyrdEntryResult:
        cur_price = float(self.proxy_driver.get_last_price(self.symbol))
        raw_qty, qty = self.qty_calculator.calculate()

        # Проверяем сигнал на базовый уровень
        base_result = self.base_level_checker.check(cur_price, entries, entry_tf)

        # Активен ли тренд?
        trend_active = self.ha_trend.is_active(entry_tf)
        if not trend_active:
            return PyrdEntryResult(
                allowed=False,
                trend_active=False,
                distance_allowed=False,
                level_type=None,
                qty=qty,
                qty_checked=True,
                raw_qty=raw_qty,
                ha_breakout=base_result.ha_breakout,
            )

        # Проверяем дистанцию 
        distance_allowed = is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=self.step_ratio,
        )
        if not distance_allowed:
            return PyrdEntryResult(
                allowed=False,
                trend_active=True,
                distance_allowed=False,
                level_type=None,
                qty=qty,
                qty_checked=True,
                raw_qty=raw_qty,
                ha_breakout=base_result.ha_breakout,
            )

        if base_result.allowed:
            level_type = "base"
        else:
            # Проверяем есть ли хотя бы один уровень который ниже текущей цены (для Buy) или выше текущей цены (для Sell)
            extension_result = self.extension_level_checker.check(
                cur_price,
                entries,
            )
            if not extension_result.allowed:
                return PyrdEntryResult(
                    allowed=False,
                    trend_active=True,
                    distance_allowed=True,
                    level_type=None,
                    qty=qty,
                    qty_checked=True,
                    raw_qty=raw_qty,
                    ha_breakout=base_result.ha_breakout,
                )

            level_type = "extension"

        # Если мы пришли сюда, значит базовый или extension уровень разрешен, тренд активен и дистанция разрешена
        # Проверяем не превышает ли позиция лимит
        position_limit_blocked = (
            qty > 0
            and not is_position_limit_allowed(
                self.proxy_driver,
                self.symbol,
                self.side,
            )
        )

        allowed = qty > 0 and not position_limit_blocked

        return PyrdEntryResult(
            allowed=allowed,
            qty=qty,
            trend_active=True,
            distance_allowed=True,
            level_type=level_type if allowed else None,
            qty_checked=True,
            raw_qty=raw_qty,
            position_limit_blocked=position_limit_blocked,
            ha_breakout=base_result.ha_breakout,
        )

    def get_rearm_qty(self) -> float:
        return self._get_pyramid_qty()

