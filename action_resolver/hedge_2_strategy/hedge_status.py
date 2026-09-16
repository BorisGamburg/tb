from dataclasses import dataclass
from action_resolver.hedge_2_strategy.hedge_mode_selector import HedgeMode
from action_resolver.hedge_2_strategy.optimization_mng import Band


@dataclass
class HedgeStatus:
    bid: float
    ask: float
    protection_current: float
    protection_required: float
    pnl: float
    mode: HedgeMode
    pairs: int
    band: Band | None = None  