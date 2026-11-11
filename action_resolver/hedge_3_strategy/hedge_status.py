from dataclasses import dataclass
from action_resolver.hedge_3_strategy.hedge_mode_selector import HedgeMode
from action_resolver.hedge_3_strategy.optimization_mng import Band


@dataclass
class HedgeStatus:
    bid: float
    ask: float
    protection_current: float
    protection_required: float
    pnl: float
    mode: HedgeMode
    band: Band | None = None
    # Схема A: границы зоны нечувствительности по текущей защите
    # (достраиваем при cur <= zone_low, сворачиваем при cur >= zone_high).
    zone_low: float | None = None
    zone_high: float | None = None
    unwind_wait: bool = False   # сворачивать пора, но безубытка нет
    scheme: str = "A"
    scheme_info: str = ""   # схема B: L/P и объём к закрытию 