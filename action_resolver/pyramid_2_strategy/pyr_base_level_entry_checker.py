from dataclasses import dataclass

from services.bb_service import BBService
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_signal import (
    HAReversalSignal,
)


@dataclass
class PyrBaseLevelEntryResult:
    allowed: bool
    ha_breakout: bool
    bb_allowed: bool
    position_allowed: bool


class PyrBaseLevelEntryChecker:

    def __init__(
        self,
        side: str,
        ha_signal: HAReversalSignal,
        bb_service: BBService,
    ):
        self.side = side
        self.ha_signal = ha_signal
        self.bb_service = bb_service

    def _check_position(self, cur_price: float, entries) -> bool:
        if self.side == "Buy":
            return all(entry.price >= cur_price for entry in entries)

        return all(entry.price <= cur_price for entry in entries)

    def _check_ha_breakout(self, entry_tf: str, cur_price: float) -> bool:
        result = self.ha_signal.is_entry(entry_tf, self.side, cur_price)
        return result.ok

    def _check_bb(self, cur_price: float, entry_tf: str) -> bool:
        bb = self.bb_service.get_live(entry_tf)

        if self.side == "Buy":
            return cur_price < bb["mid"]

        return cur_price > bb["mid"]

    def check(self, cur_price: float, entries, entry_tf: str) -> PyrBaseLevelEntryResult:
        ha_breakout = self._check_ha_breakout(entry_tf, cur_price)

        position_allowed = self._check_position(cur_price, entries)
        if not position_allowed:
            return PyrBaseLevelEntryResult(
                allowed=False,
                ha_breakout=ha_breakout,
                bb_allowed=False,
                position_allowed=False,
            )

        if not ha_breakout:
            return PyrBaseLevelEntryResult(
                allowed=False,
                ha_breakout=False,
                bb_allowed=False,
                position_allowed=True,
            )

        # Временно отключена проверка Bollinger Bands.
        # bb_allowed = self._check_bb(cur_price, entry_tf)

        return PyrBaseLevelEntryResult(
            allowed=True,
            ha_breakout=True,
            # bb_allowed=bb_allowed,
            bb_allowed=True,
            position_allowed=True,
        )