from dataclasses import dataclass
from math import ceil, floor

from common.unwind.unwind_planner import EPS, _per_coin
from common.unwind.unwinder import Unwinder


@dataclass
class CompensationPlan:
    base_level: object   # Base: источник прибыли, закрывается целиком
    levels: list         # Base + убыточные уровни (список для Unwinder)
    qty: float           # общий объём ордера = Base + списание с убыточных
    base_qty: float
    loss_qty: float      # сколько списывается с убыточных уровней суммарно


class PyrCompensationPlanner:
    """Расчёт компенсации режима recovery. Только расчёт, без ордеров.

    Прибыль берётся только с Base. Ищется максимальный объём убыточных
    уровней, который Base покрывает в безубыток (min_pnl). Распределение
    по убыточным уровням делает общий оптимизатор Unwinder (самые убыточные
    первыми), поэтому за один ордер может закрыться несколько уровней.
    """

    def __init__(self, trading_info, step_ratio: float, unwinder: Unwinder):
        self.trading_info = trading_info
        self.step_ratio = step_ratio
        self.unwinder = unwinder

    def plan(
        self,
        levels,
        side: str,
        price: float,
        min_pnl: float,
    ) -> CompensationPlan | None:
        """
        levels  - уровни стека (StackElem).
        price   - цена закрытия с исполняемой стороны (Buy: Bid, Sell: Ask).
        min_pnl - минимальный итог ордера.

        Возвращает план или None, если не покрывается даже min_qty
        убыточного уровня.
        """
        if len(levels) < 2:
            # Меньше 2 уровней. Компенсировать нечего.
            return None

        # Получаем базовый уровень
        base = self._get_base_level(levels, side)

        # Цена должна уйти от Base не меньше, чем на шаг
        if not self._is_step_reached(base, side, price):
            return None

        # Base должен быть в прибыли (с комиссиями)
        fee_taker = self.trading_info.fee_taker
        if _per_coin(base, price, side, fee_taker) <= 0:
            return None

        # Убыточные уровни. Остальные прибыльные в расчёте не участвуют.
        losers = [
            level for level in levels
            if level is not base
            and _per_coin(level, price, side, fee_taker) < 0
        ]
        if not losers:
            return None

        # Границы поиска объёма убыточных, в шагах qty_step
        step = self.trading_info.qty_step
        min_units = ceil(self.trading_info.min_qty / step - EPS)
        max_units = floor(sum(level.qty for level in losers) / step + EPS)
        if max_units < min_units:
            return None

        sub_levels = [base] + losers

        def is_breakeven(units: int) -> bool:
            qty = round(base.qty + units * step, 12)
            res = self.unwinder.check_breakeven(
                sub_levels, side, qty, price, min_pnl, "most_first"
            )
            return res is not None and res.breakeven

        # Прибыли Base не хватает даже на min_qty убыточного -> компенсации нет
        if not is_breakeven(min_units):
            return None

        # Бинарный поиск максимального безубыточного объёма
        # (чем больше убыточных, тем меньше PnL, поэтому условие монотонно).
        lo, hi = min_units, max_units
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if is_breakeven(mid):
                lo = mid
            else:
                hi = mid - 1

        loss_qty = round(lo * step, 12)
        return CompensationPlan(
            base_level=base,
            levels=sub_levels,
            qty=round(base.qty + loss_qty, 12),
            base_qty=base.qty,
            loss_qty=loss_qty,
        )

    def _get_base_level(self, levels, side: str):
        if side == "Buy":
            return min(levels, key=lambda level: level.price)
        return max(levels, key=lambda level: level.price)

    def _is_step_reached(self, base, side: str, price: float) -> bool:
        if side == "Buy":
            return price >= base.price * (1 + self.step_ratio)
        return price <= base.price * (1 - self.step_ratio)