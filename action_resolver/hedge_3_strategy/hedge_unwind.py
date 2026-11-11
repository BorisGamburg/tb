"""Схема A хеджа: подбор объёма сворачивания.

Из n лишних шагов берём максимальное число целых шагов, которое закрывается
не в убыток (min_pnl = 0). Перебор от большего к меньшему: безубыточный
объём по построению безубыточен и для меньшего числа шагов, поэтому первый
найденный вариант и есть максимум. Не уложился даже один шаг - ждём.

Оценка безубытка идёт через Unwinder.check_breakeven, то есть теми же
формулами и тем же оптимизатором, что и фактическое списание.
"""
from dataclasses import dataclass

# Сворачиваем только в безубыток или в плюс.
UNWIND_MIN_PNL = 0.0

# Из убыточных уровней первыми самые убыточные (фиксировано в оптимизаторе),
# из прибыльных первыми наименее прибыльные.
UNWIND_PROFIT_ORDER = "least_first"


@dataclass
class UnwindResult:
    found: bool       # есть безубыточный объём для закрытия
    qty: float        # объём к закрытию, монет
    price: float      # плановая цена (граница лимитного ордера)
    steps: int        # сколько шагов закрываем
    wait: bool        # условие сворачивания выполнено, но безубытка нет


@dataclass
class HoldResult:
    """Ничего не делаем (зона нечувствительности и прочее)."""


def find_unwind_qty(
    unwinder,
    levels,
    side: str,
    steps: int,
    step_qty: float,
    price: float,
) -> UnwindResult:
    for n in range(steps, 0, -1):
        qty = round(n * step_qty, 12)
        res = unwinder.check_breakeven(
            levels,
            side,
            qty,
            price,
            UNWIND_MIN_PNL,
            UNWIND_PROFIT_ORDER,
        )
        if res is not None and res.breakeven:
            return UnwindResult(
                found=True, qty=qty, price=price, steps=n, wait=False
            )
    return UnwindResult(
        found=False, qty=0.0, price=price, steps=0, wait=True
    )
