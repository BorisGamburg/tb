from dataclasses import dataclass

from services.bb_service import BBService
from signals.ha_reversal_signal import HAReversalSignal


@dataclass
class PyrBaseLevelEntryResult:
    allowed: bool
    ha_reversal: bool
    bb_allowed: bool
    position_allowed: bool


class PyrBaseLevelEntryChecker:

    def __init__(
        self,
        side: str,
        timeframe: str,
        ha_signal: HAReversalSignal,
        bb_service: BBService,
    ):
        self.side = side
        self.timeframe = timeframe
        self.ha_signal = ha_signal
        self.bb_service = bb_service

    def _check_position(self, cur_price: float, entries) -> bool:
        if self.side == "Buy":
            return all(entry.price >= cur_price for entry in entries)

        return all(entry.price <= cur_price for entry in entries)

    def _check_ha_reversal(self) -> bool:
        ha_reversal, _ = self.ha_signal.is_entry(self.timeframe, self.side)
        return ha_reversal

    def _check_bb(self, cur_price: float) -> bool:
        bb = self.bb_service.get_live(self.timeframe)

        if self.side == "Buy":
            return cur_price < bb["mid"]

        return cur_price > bb["mid"]

    def check(self, cur_price: float, entries) -> PyrBaseLevelEntryResult:
        position_allowed = self._check_position(cur_price, entries)
        if not position_allowed:
            return PyrBaseLevelEntryResult(
                allowed=False,
                ha_reversal=False,
                bb_allowed=False,
                position_allowed=False,
            )

        ha_reversal = self._check_ha_reversal()
        if not ha_reversal:
            return PyrBaseLevelEntryResult(
                allowed=False,
                ha_reversal=False,
                bb_allowed=False,
                position_allowed=True,
            )

        bb_allowed = self._check_bb(cur_price)

        return PyrBaseLevelEntryResult(
            allowed=bb_allowed,
            ha_reversal=True,
            bb_allowed=bb_allowed,
            position_allowed=True,
        )
