from dataclasses import dataclass

from action_resolver.hedge_2_strategy.hedge_mode_selector import HedgeMode


@dataclass
class HedgeStatus:
    price: float
    protection_current: float
    protection_required: float
    pnl: float
    mode: HedgeMode
    pairs: int
