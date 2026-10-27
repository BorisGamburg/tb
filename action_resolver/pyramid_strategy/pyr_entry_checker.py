from dataclasses import dataclass

from action_resolver.pyramid_strategy.pyr_base_level_entry_checker import (
    PyrBaseLevelEntryChecker,
)
from action_resolver.pyramid_strategy.pyr_extension_level_entry_checker import (
    PyrExtensionLevelEntryChecker,
)
from common.trading_info import TradingInfo
from services.bb_service import BBService
from signals.ha_reversal_signal import HAReversalSignal

from common.ha_trend_checker import HATrendChecker
from common.level_distance_checker import is_level_distance_allowed


@dataclass
class PyrdEntryResult:
    allowed: bool
    qty: float
    trend_active: bool
    distance_allowed: bool
    level_type: str | None
    ha_prev_color: str | None = None
    ha_curr_color: str | None = None


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
        self.qty_ratio = qty_pct / 100
        self.trading_info = trading_info

        self.main_side = "Sell" if side == "Buy" else "Buy"

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
        main_position = self.proxy_driver.get_position(
            self.symbol,
            self.main_side,
        )
        main_qty = float(main_position["size"])
        return self.trading_info.get_valid_order_qty(
            main_qty * self.qty_ratio
        )

    def check(self, entries, entry_tf: str) -> PyrdEntryResult:
        cur_price = float(self.proxy_driver.get_last_price(self.symbol))

        base_result = self.base_level_checker.check(cur_price, entries, entry_tf)

        trend_active = self.ha_trend.is_active(entry_tf)
        if not trend_active:
            return PyrdEntryResult(
                allowed=False,
                qty=0.0,
                trend_active=False,
                distance_allowed=False,
                level_type=None,
                ha_prev_color=base_result.ha_prev_color,
                ha_curr_color=base_result.ha_curr_color,                
            )

        distance_allowed = is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=self.step_ratio,
        )
        if not distance_allowed:
            return PyrdEntryResult(
                allowed=False,
                qty=0.0,
                trend_active=True,
                distance_allowed=False,
                level_type=None,
                ha_prev_color=base_result.ha_prev_color,
                ha_curr_color=base_result.ha_curr_color,                
            )

        if base_result.allowed:
            level_type = "base"
        else:
            extension_result = self.extension_level_checker.check(
                cur_price,
                entries,
            )
            if not extension_result.allowed:
                return PyrdEntryResult(
                    allowed=False,
                    qty=0.0,
                    trend_active=True,
                    distance_allowed=True,
                    level_type=None,
                    ha_prev_color=base_result.ha_prev_color,
                    ha_curr_color=base_result.ha_curr_color,
                )

            level_type = "extension"

        qty = self._get_pyramid_qty()

        return PyrdEntryResult(
            allowed=qty > 0,
            qty=qty,
            trend_active=True,
            distance_allowed=True,
            level_type=level_type if qty > 0 else None,
            ha_prev_color=base_result.ha_prev_color,
            ha_curr_color=base_result.ha_curr_color,
        )