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


# Схема B: хвосты по L/P, как в пирамиде 2. Значения стартовые, их
# подбираем по результатам; в конфиг выносим, если понадобится.
SCHEME_B_TRIGGER_PCT = 10.0     # порог L/P, %
SCHEME_B_TARGET_PCT = 5.0       # целевое L/P после сворачивания, %
SCHEME_B_MIN_PNL = 0.0          # итог ордера не ниже, USDT
SCHEME_B_MIN_STACK_PCT = 0.0    # минимальный стек, % от баланса
SCHEME_B_PROFIT_ORDER = "most_first"   # как в пирамиде (по умолчанию)


@dataclass
class UnwindResult:
    found: bool       # есть объём для закрытия
    qty: float        # объём к закрытию, монет
    price: float      # плановая цена (граница лимитного ордера)
    steps: int        # схема A: сколько шагов закрываем (схема B: 0)
    wait: bool        # условие сворачивания выполнено, но безубытка нет
    min_pnl: float = UNWIND_MIN_PNL
    profit_order: str = UNWIND_PROFIT_ORDER


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
