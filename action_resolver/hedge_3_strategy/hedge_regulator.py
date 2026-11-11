"""Схема A хеджа: регулятор защиты (чистая логика, без биржи и состояния).

Шаг S = hedge_qty_pct от основной позиции (в монетах: step_qty).
Требуемая защита req (в монетах: required_qty = req * main_qty).

  достраиваем шаг, если hedge + S <= required   (BUILD)
  сворачиваем шаги,  если hedge - S >= required (UNWIND, целых шагов n)
  иначе зона нечувствительности                 (HOLD)

Гистерезис получается сам: после операции цене надо пройти ещё шаг S,
чтобы произошло следующее действие.
"""
from dataclasses import dataclass
from enum import Enum
from math import floor

EPS = 1e-9


class RegAction(Enum):
    BUILD = "build"
    UNWIND = "unwind"
    HOLD = "hold"


@dataclass(frozen=True)
class RegDecision:
    action: RegAction
    steps: int          # UNWIND: сколько целых шагов лишние (>= 1), иначе 0
    step_qty: float     # объём одного шага, монет
    zone_low: float     # граница достройки по cur: req - S (доли позиции)
    zone_high: float    # граница сворачивания по cur: req + S (доли позиции)


def decide(
    main_qty: float,
    hedge_qty: float,
    required_ratio: float,
    step_qty: float,
) -> RegDecision:
    """main_qty > 0. step_qty = 0 означает, что шаг меньше min_qty биржи:
    действовать нечем, остаёмся в HOLD."""
    required_qty = required_ratio * main_qty
    zone_low = (required_qty - step_qty) / main_qty
    zone_high = (required_qty + step_qty) / main_qty

    def result(action: RegAction, steps: int = 0) -> RegDecision:
        return RegDecision(action, steps, step_qty, zone_low, zone_high)

    if step_qty <= 0:
        return result(RegAction.HOLD)

    if hedge_qty + step_qty <= required_qty + EPS:
        return result(RegAction.BUILD)

    steps = floor((hedge_qty - required_qty) / step_qty + EPS)
    if steps >= 1:
        return result(RegAction.UNWIND, steps)

    return result(RegAction.HOLD)
