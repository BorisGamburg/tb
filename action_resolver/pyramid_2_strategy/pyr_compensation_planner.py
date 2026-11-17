from dataclasses import dataclass

from common.unwind.unwind_planner import EPS, _floor_step, _per_coin


@dataclass
class CompensationPlan:
    base_level: object   # нижний уровень (источник прибыли), закрывается целиком
    base_qty: float
    loss_level: object   # убыточный уровень, с которого закрывается кусок
    loss_qty: float
    expected_pnl: float  # ожидаемый итог связки с учётом комиссий

    @property
    def total_qty(self) -> float:
        return self.base_qty + self.loss_qty


class PyrCompensationPlanner:
    """Расчёт компенсации режима recovery. Только расчёт, без ордеров."""

    def __init__(self, trading_info, step_ratio: float):
        self.trading_info = trading_info
        self.step_ratio = step_ratio

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
        min_pnl - минимальный итог связки.

        Возвращает план или None, если компенсации нет.
        """
        if len(levels) < 2:
            # Меньше 2 уровней. Компенсировать нечего.
            return None

        # Получаем базовый уровень
        base = self._get_base_level(levels, side)

        # Цена должна уйти от Base не меньше, чем на шаг
        if not self._is_step_reached(base, side, price):
            return None

        # Прибыль Base (с комиссиями), которой можно покрыть убыток
        fee_taker = self.trading_info.fee_taker
        base_per_coin = _per_coin(base, price, side, fee_taker)
        if base_per_coin <= 0:
            return None

        base_profit = base_per_coin * base.qty
        pool = base_profit - min_pnl
        if pool <= EPS:
            return None

        # Убыточные уровни: от самого убыточного к менее убыточным
        losers = []
        for level in levels:
            if level is base:
                continue
            per_coin = _per_coin(level, price, side, fee_taker)
            if per_coin < 0:
                losers.append((level, per_coin))
        losers.sort(key=lambda item: item[1])

        # Первый уровень, на котором можно закрыть хотя бы min_qty
        for level, per_coin in losers:
            loss_qty = self._calc_loss_qty(level, -per_coin, pool)
            if loss_qty is None:
                continue

            return CompensationPlan(
                base_level=base,
                base_qty=base.qty,
                loss_level=level,
                loss_qty=loss_qty,
                expected_pnl=base_profit + per_coin * loss_qty,
            )

        return None

    def _get_base_level(self, levels, side: str):
        if side == "Buy":
            return min(levels, key=lambda level: level.price)
        return max(levels, key=lambda level: level.price)

    def _is_step_reached(self, base, side: str, price: float) -> bool:
        if side == "Buy":
            return price >= base.price * (1 + self.step_ratio)
        return price <= base.price * (1 - self.step_ratio)

    def _calc_loss_qty(self, level, loss_per_coin: float, pool: float):
        """Сколько можно закрыть на убыточном уровне. None, если меньше min_qty."""
        qty_step = self.trading_info.qty_step
        min_qty = self.trading_info.min_qty

        qty_max = min(level.qty, pool / loss_per_coin)

        if qty_max >= level.qty - EPS:
            # Прибыли хватает на весь уровень
            qty = level.qty
        else:
            qty = _floor_step(qty_max, qty_step)
            # Остаток уровня не должен стать меньше min_qty
            if level.qty - qty < min_qty - EPS:
                qty = _floor_step(level.qty - min_qty, qty_step)

        if qty < min_qty - EPS:
            return None

        return qty
