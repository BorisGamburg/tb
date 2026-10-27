from dataclasses import dataclass

from services.bb_service import BBService
from signals.ha_reversal_signal import HAReversalSignal


@dataclass
class PyrBaseLevelEntryResult:
    allowed: bool
    ha_reversal: bool
    bb_allowed: bool
    position_allowed: bool
    ha_prev_color: str | None = None
    ha_curr_color: str | None = None


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

    def _check_ha_reversal(self, entry_tf: str) -> tuple[bool, dict]:
        return self.ha_signal.is_entry(entry_tf, self.side)

    def _check_bb(self, cur_price: float, entry_tf: str) -> bool:
        bb = self.bb_service.get_live(entry_tf)

        if self.side == "Buy":
            return cur_price < bb["mid"]

        return cur_price > bb["mid"]

    def check(self, cur_price: float, entries, entry_tf: str) -> PyrBaseLevelEntryResult:
        ha_reversal, ha_payload = self._check_ha_reversal(entry_tf)

        ha_prev_color = ha_payload["prev_color"]
        ha_curr_color = ha_payload["curr_color"]

        position_allowed = self._check_position(cur_price, entries)
        if not position_allowed:
            return PyrBaseLevelEntryResult(
                allowed=False,
                ha_reversal=ha_reversal,
                bb_allowed=False,
                position_allowed=False,
                ha_prev_color=ha_prev_color,
                ha_curr_color=ha_curr_color,
            )

        if not ha_reversal:
            return PyrBaseLevelEntryResult(
                allowed=False,
                ha_reversal=False,
                bb_allowed=False,
                position_allowed=True,
                ha_prev_color=ha_prev_color,
                ha_curr_color=ha_curr_color,
            )

        bb_allowed = self._check_bb(cur_price, entry_tf)

        return PyrBaseLevelEntryResult(
            allowed=bb_allowed,
            ha_reversal=True,
            bb_allowed=bb_allowed,
            position_allowed=True,
            ha_prev_color=ha_prev_color,
            ha_curr_color=ha_curr_color,
        )