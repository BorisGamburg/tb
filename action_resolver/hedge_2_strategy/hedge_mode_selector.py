from dataclasses import dataclass
from enum import Enum
from action_resolver.hedge_2_strategy.protect_calc import (
    calc_required_protect_ratio,
)


class HedgeMode(Enum):
    BUILD = "build"
    OPTIMIZATION = "optimization"

@dataclass
class ProtectionCheck:
    needed: bool
    curr_ratio: float
    required_ratio: float


class HedgeModeSelector:
    def __init__(
        self,
        hedge_side: str,
        max_hedge_ratio: float,
    ):
        self.hedge_side = hedge_side
        self.main_side = "Sell" if hedge_side == "Buy" else "Buy"
        self.max_hedge_ratio = max_hedge_ratio
        self.protect_ratio_factor = 1.0

    def _calc_protect_ratios(
        self,
        unrealised_pnl: float,
        main_qty: float,
        hedge_qty: float,
        entry_price: float,
    ):
        # Рассчитываем текущий коэффициент защиты
        curr_protect_ratio = self._calc_curr_protect_ratio(main_qty, hedge_qty)

        # Рассчитываем требуемый коэффициент защиты
        required_protect_ratio = calc_required_protect_ratio(
            unrealised_pnl=unrealised_pnl,
            entry_price=entry_price,
            main_qty=main_qty,
            protect_ratio_factor=self.protect_ratio_factor,
            max_hedge_ratio=self.max_hedge_ratio,
        )

        return curr_protect_ratio, required_protect_ratio

    def _calc_curr_protect_ratio(
        self,
        main_qty: float,
        hedge_qty: float,
    ) -> float:
        return hedge_qty / main_qty
    
    def check_protection(
        self,
        unrealised_pnl: float,
        main_pos_size: float,
        hedge_pos_size: float,
        entry_price: float,
    ) -> ProtectionCheck:
        # Если основной позиции нет — защита не требуется
        if main_pos_size <= 0:
            return ProtectionCheck(
                needed=False,
                curr_ratio=0.0,
                required_ratio=0.0,
            )

        # Рассчитываем текущий и требуемый уровень защиты
        curr_ratio, required_ratio = self._calc_protect_ratios(
            unrealised_pnl=unrealised_pnl,
            main_qty=main_pos_size,
            hedge_qty=hedge_pos_size,
            entry_price=entry_price,
        )

        return ProtectionCheck(
            needed=curr_ratio < required_ratio,
            curr_ratio=curr_ratio,
            required_ratio=required_ratio,
        )
