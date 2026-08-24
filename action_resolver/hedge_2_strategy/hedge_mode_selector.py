from enum import Enum
from action_resolver.hedge_2_strategy.protect_calc import (
    calc_required_protect_ratio,
)


class HedgeMode(Enum):
    BUILD = "build"
    OPTIMIZATION = "optimization"

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
    
    def select_mode(
        self,
        unrealised_pnl: float,
        main_pos_size: float,
        hedge_pos_size: float,
        entry_price: float,
    ):
        report = ""

        # Если основной позиции нет — защита не требуется
        if main_pos_size <= 0:
            report += (
                "Mode: OPTIMIZATION "
                "(main position absent). "
            )

            return (
                HedgeMode.OPTIMIZATION,
                report,
                0.0,
                0.0,
            )

        # Рассчитываем текущий и требуемый уровень защиты
        curr_ratio, required_ratio = self._calc_protect_ratios(
            unrealised_pnl=unrealised_pnl,
            main_qty=main_pos_size,
            hedge_qty=hedge_pos_size,
            entry_price=entry_price,
        )

        report += (
            "Protection: "
            f"current={curr_ratio:.3f}, "
            f"required={required_ratio:.3f} "
            f"({'достаточно' if curr_ratio >= required_ratio else 'недостаточно'}) "
            f"Unrealised PnL: {unrealised_pnl:.6f} "
        )

        # Защиты недостаточно
        if curr_ratio < required_ratio:
            report += (
                "Mode: BUILD "
            )

            return (
                HedgeMode.BUILD,
                report,
                curr_ratio,
                required_ratio,
            )

        # Защиты достаточно
        report += (
            "Mode: OPTIMIZATION "
        )

        return (
            HedgeMode.OPTIMIZATION,
            report,
            curr_ratio,
            required_ratio,
        )
