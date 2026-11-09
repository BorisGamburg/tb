"""Распределение исполненного объёма по уровням стека.

Цель: списать ровно q_units, не превышая остаток каждого уровня, так чтобы
суммарный PnL >= min_pnl, а объём убыточных уровней был максимальным.
Если такого распределения нет, берём распределение с максимальным PnL
(то есть минимальным убытком).

Порядок списания прибыльных уровней (profit_order):
  "least_first" - от наименее прибыльных (самые прибыльные остаются в стеке
                  дольше). Убыточные при этом идут от наименее убыточных.
                  Если безубыточность так недостижима, а с более прибыльными
                  уровнями достижима, берётся вариант "most_first".
  "most_first"  - от самых прибыльных: максимальный PnL при заданном объёме
                  убыточных, то есть максимально возможное списание убыточных.

Порядок убыточных уровней (loss_order):
  "least_first" - от наименее убыточных (по умолчанию, прежнее поведение).
  "most_first"  - от самых убыточных (как в планировщике свёртывания).
                  Если в этом порядке безубыточного распределения нет, но
                  оно есть при убыточных от наименее убыточных, берётся оно
                  (breakeven=True). Если безубыточного нет совсем, убыток
                  минимизируется: убыточные от наименее убыточных.

Все величины целые: units - количество в шагах qty_step,
coef - PnL на один шаг (целое, округление должно быть консервативным).
Сложность: O(n log n + n log q), от числа монет почти не зависит.
"""
from dataclasses import dataclass


@dataclass
class Result:
    reductions: list      # списание по уровням, в порядке входного списка
    pnl: int              # суммарный PnL в целых единицах coef
    loss_units: int       # списано с убыточных уровней
    breakeven: bool       # True, если выполнено pnl >= min_pnl
    profit_order: str = "most_first"  # какой порядок реально применён


def optimize_reductions(levels, q_units, min_pnl=0, profit_order="most_first",
                        loss_order="least_first"):
    """levels: список (coef, units). Возвращает Result или None, если q_units
    больше суммарного остатка."""
    if profit_order not in ("most_first", "least_first"):
        raise ValueError("profit_order: most_first или least_first")
    if loss_order not in ("most_first", "least_first"):
        raise ValueError("loss_order: most_first или least_first")
    n = len(levels)
    if q_units < 0 or q_units > sum(u for _, u in levels):
        return None

    # убыточные: от наименее убыточных (least) и от самых убыточных (most)
    loss_least = sorted((i for i in range(n) if levels[i][0] < 0),
                        key=lambda i: -levels[i][0])
    loss_idx = loss_least if loss_order == "least_first" else loss_least[::-1]
    prof_most = sorted((i for i in range(n) if levels[i][0] >= 0),
                       key=lambda i: -levels[i][0])
    prof_least = prof_most[::-1]
    cap_loss = sum(levels[i][1] for i in loss_least)
    cap_prof = sum(levels[i][1] for i in prof_most)

    def fill(order, amount):
        red, total = {}, 0
        for i in order:
            if amount <= 0:
                break
            take = min(levels[i][1], amount)
            red[i] = take
            total += take * levels[i][0]
            amount -= take
        return red, total

    def f(L, prof_order, l_order=None):
        l_order = loss_idx if l_order is None else l_order
        return fill(l_order, L)[1] + fill(prof_order, q_units - L)[1]

    def max_L(prof_order, lo, hi, l_order=None):
        # f не возрастает по L: ищем наибольшее L с f(L) >= min_pnl
        a, b = lo, hi
        while a < b:
            mid = (a + b + 1) // 2
            if f(mid, prof_order, l_order) >= min_pnl:
                a = mid
            else:
                b = mid - 1
        return a

    def build(L, prof_order, ok, used, l_order=None):
        l_order = loss_idx if l_order is None else l_order
        r1, p1 = fill(l_order, L)
        r2, p2 = fill(prof_order, q_units - L)
        reductions = [0] * n
        for i, v in {**r1, **r2}.items():
            reductions[i] = v
        return Result(reductions, p1 + p2, L, ok, used)

    lo = max(0, q_units - cap_prof)   # меньше нельзя: нечем добрать объём
    hi = min(q_units, cap_loss)

    if profit_order == "least_first" and f(lo, prof_least) >= min_pnl:
        return build(max_L(prof_least, lo, hi), prof_least, True, "least_first")

    # "most_first": максимум PnL при каждом L
    if f(lo, prof_most) < min_pnl:
        # В порядке loss_order безубыточного нет. Пробуем убыточные от
        # наименее убыточных: если так безубыточность достижима, берём
        # максимальный объём убыточных в этом порядке.
        if (loss_idx is not loss_least
                and f(lo, prof_most, loss_least) >= min_pnl):
            L = max_L(prof_most, lo, hi, loss_least)
            return build(L, prof_most, True, "most_first", loss_least)
        # Безубыточного нет совсем: максимум PnL = минимум L, убыточные от
        # наименее убыточных (потеря наименьшая)
        return build(lo, prof_most, False, "most_first", loss_least)
    return build(max_L(prof_most, lo, hi), prof_most, True, "most_first")