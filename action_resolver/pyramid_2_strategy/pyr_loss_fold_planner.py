"""Планировщик свёртывания по порогу L/P.

L - суммарный убыток убыточных уровней, P - суммарная прибыль прибыльных
(оба по цене закрытия, с комиссиями). Чистая функция plan(), без зависимостей от бота.
"""
from dataclasses import dataclass, field
from math import floor, ceil

EPS = 1e-9


@dataclass
class Level:
    price: float          # цена входа
    qty: float            # текущий объём уровня
    fee: float = 0.0      # входная комиссия всего уровня (на текущий qty)


@dataclass
class Params:
    trigger: float = 0.10   # запуск, если L/P выше
    target: float = 0.05    # цель возврата L/P
    l_min: float = 0.0      # минимальный L в USDT для запуска (защита от шума)
    min_pnl: float = 0.0    # итог ордера не ниже
    fee_taker: float = 0.00055
    qty_step: float = 0.001
    min_qty: float = 0.001


@dataclass
class Piece:
    level_idx: int
    role: str             # 'loss' или 'donor'
    qty: float
    pnl: float            # чистый pnl этого куска при закрытии


@dataclass
class Plan:
    triggered: bool
    reason: str
    L: float = 0.0
    P: float = 0.0
    ratio: float = 0.0
    budget: float = 0.0
    pieces: list = field(default_factory=list)
    total_qty: float = 0.0
    pnl: float = 0.0
    ratio_after: float = 0.0


def _floor_step(q, step):
    return round(floor(q / step + EPS) * step, 12)


def _ceil_step(q, step):
    return round(ceil(q / step - EPS) * step, 12)


def _per_coin(lv, price, side, fee_taker):
    sign = 1.0 if side == "Buy" else -1.0
    return sign * (price - lv.price) - lv.fee / lv.qty - price * fee_taker


def _stats(levels, price, side, fee_taker):
    L = P = 0.0
    for lv in levels:
        u = _per_coin(lv, price, side, fee_taker)
        if u < 0:
            L += -u * lv.qty
        elif u > 0:
            P += u * lv.qty
    ratio = (L / P) if P > 0 else (float("inf") if L > 0 else 0.0)
    return L, P, ratio


def plan(levels, price, side, p: Params) -> Plan:
    """price - цена с исполняемой стороны стакана (лонг: bid, шорт: ask)."""
    L, P, ratio = _stats(levels, price, side, p.fee_taker)
    res = Plan(False, "", L, P, ratio, ratio_after=ratio)

    if L < p.l_min:
        res.reason = f"L={L:.4f} меньше L_min={p.l_min}"
        return res
    if ratio <= p.trigger:
        res.reason = f"L/P={ratio:.3f} не выше порога {p.trigger}"
        return res
    res.triggered = True

    pool = P - p.min_pnl                      # сколько убытка можно закрыть
    budget = min(L, (L - p.target * P) / (1 - p.target))
    res.budget = budget
    if pool <= EPS:
        res.reason = "нет прибыли для покрытия"
        return res

    per = [(i, _per_coin(lv, price, side, p.fee_taker)) for i, lv in enumerate(levels)]
    losers = sorted([(i, u) for i, u in per if u < 0], key=lambda x: x[1])   # самый убыточный первым
    donors = sorted([(i, u) for i, u in per if u > 0], key=lambda x: x[1])   # наименее прибыльный первым

    pieces, loss_closed, budget_left = [], 0.0, budget
    for i, u in losers:
        if budget_left <= EPS:
            break
        lv, c = levels[i], -u
        qmax = min(lv.qty, budget_left / c, (pool - loss_closed) / c)
        if qmax >= lv.qty - EPS:
            q = lv.qty
        else:
            q = _floor_step(qmax, p.qty_step)
            if lv.qty - q < p.min_qty - EPS:          # остаток не меньше min_qty
                q = _floor_step(lv.qty - p.min_qty, p.qty_step)
        if q < p.min_qty - EPS:
            continue                                  # на этот уровень не хватает, идём к следующему
        pieces.append(Piece(i, "loss", q, u * q))
        loss_closed += c * q
        budget_left -= c * q

    if not pieces:
        res.reason = "прибыли не хватает даже на минимальный кусок"
        return res

    need = loss_closed + p.min_pnl
    for i, u in donors:
        if need <= EPS:
            break
        lv = levels[i]
        q = _ceil_step(need / u, p.qty_step)
        q = max(q, p.min_qty)
        if q >= lv.qty - EPS or lv.qty - q < p.min_qty - EPS:
            q = lv.qty
        pieces.append(Piece(i, "donor", q, u * q))
        need -= u * q
    if need > 1e-7:
        res.pieces, res.reason = [], "доноры не покрывают закрываемый убыток"
        return res

    # состояние после плана
    left = {}
    for pc in pieces:
        left[pc.level_idx] = left.get(pc.level_idx, 0.0) + pc.qty
    after = []
    for i, lv in enumerate(levels):
        q_left = lv.qty - left.get(i, 0.0)
        if q_left > EPS:
            after.append(Level(lv.price, q_left, lv.fee * q_left / lv.qty))
    _, _, res.ratio_after = _stats(after, price, side, p.fee_taker)

    res.pieces = pieces
    res.total_qty = sum(pc.qty for pc in pieces)
    res.pnl = sum(pc.pnl for pc in pieces)
    res.reason = "ok"
    return res