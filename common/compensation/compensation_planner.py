from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


EPS = Decimal("1e-12")


@dataclass
class LevelReduction:
    level: object
    qty: float
    expected_pnl: float


@dataclass
class CompensationPlan:
    base_level: object
    base_qty: float
    reductions: list[LevelReduction]
    total_qty: float
    expected_pnl: float
    budget: float
    budget_used: float


class CompensationPlanner:
    """Самостоятельное планирование компенсационного закрытия."""

    def __init__(
        self,
        qty_step: float,
        min_qty: float,
        fee_taker: float,
    ):
        self.qty_step = self._decimal(qty_step)
        self.min_qty = self._decimal(min_qty)
        self.fee_taker = self._decimal(fee_taker)

        if self.qty_step <= 0:
            raise ValueError("qty_step must be positive")

        if self.min_qty <= 0:
            raise ValueError("min_qty must be positive")

        if not 0 <= self.fee_taker < 1:
            raise ValueError("Invalid taker fee rate")

        self.min_units = self._to_units_ceil(self.min_qty)

    def plan(
        self,
        levels,
        side: str,
        price: float,
        min_pnl: float,
    ) -> CompensationPlan | None:
        if side not in ("Buy", "Sell"):
            raise ValueError(f"Unsupported side: {side}")

        if len(levels) < 2:
            return None

        price = self._decimal(price)
        min_pnl = self._decimal(min_pnl)

        if price <= 0:
            raise ValueError("Closing price must be positive")

        self._validate_levels(levels)

        base = self._get_base_level(levels, side)
        base_pnl_per_coin = self._pnl_per_coin(base, side, price)

        if base_pnl_per_coin <= 0:
            return None

        base_units = self._to_units(base.qty)
        base_qty = self._from_units(base_units)

        base_pnl = base_pnl_per_coin * base_qty
        budget = base_pnl - min_pnl

        if budget <= EPS:
            return None

        losers = []

        for level in levels:
            if level is base:
                continue

            pnl_per_coin = self._pnl_per_coin(level, side, price)

            if pnl_per_coin < 0:
                losers.append((level, pnl_per_coin))

        if not losers:
            return None

        losers.sort(key=lambda item: item[1])

        budget_left = budget
        reductions = []

        for level, pnl_per_coin in losers:
            loss_per_coin = -pnl_per_coin
            level_units = self._to_units(level.qty)

            if level_units < self.min_units:
                continue

            level_qty = self._from_units(level_units)
            full_loss = loss_per_coin * level_qty

            if full_loss <= budget_left + EPS:
                close_units = level_units
            else:
                max_qty = budget_left / loss_per_coin
                close_units = self._to_units_floor(max_qty)

                if close_units < self.min_units:
                    continue

                remaining_units = level_units - close_units

                if 0 < remaining_units < self.min_units:
                    close_units = level_units - self.min_units

                    if close_units < self.min_units:
                        continue

                close_qty = self._from_units(close_units)
                close_loss = loss_per_coin * close_qty

                if close_loss > budget_left + EPS:
                    continue

            close_qty = self._from_units(close_units)
            close_loss = loss_per_coin * close_qty

            reductions.append(
                LevelReduction(
                    level=level,
                    qty=float(close_qty),
                    expected_pnl=float(-close_loss),
                )
            )

            budget_left -= close_loss

            if close_units < level_units:
                break

        if not reductions:
            return None

        loss_qty = sum(
            self._decimal(item.qty)
            for item in reductions
        )

        total_qty = base_qty + loss_qty
        expected_pnl = base_pnl - sum(
            -self._decimal(item.expected_pnl)
            for item in reductions
        )

        if total_qty < self.min_qty:
            return None

        return CompensationPlan(
            base_level=base,
            base_qty=float(base_qty),
            reductions=reductions,
            total_qty=float(total_qty),
            expected_pnl=float(expected_pnl),
            budget=float(budget),
            budget_used=float(budget - budget_left),
        )

    def _get_base_level(self, levels, side: str):
        if side == "Buy":
            return min(levels, key=lambda level: level.price)

        return max(levels, key=lambda level: level.price)

    def _pnl_per_coin(self, level, side: str, price: Decimal) -> Decimal:
        sign = Decimal("1") if side == "Buy" else Decimal("-1")

        entry_price = self._decimal(level.price)
        fee = self._decimal(level.fee)
        initial_qty = self._decimal(level.initial_qty)
        qty = self._decimal(level.qty)

        fee_base_qty = initial_qty if initial_qty > 0 else qty

        if fee_base_qty <= 0:
            raise ValueError("Invalid initial quantity")

        open_fee_per_coin = fee / fee_base_qty
        close_fee_per_coin = price * self.fee_taker

        return (
            sign * (price - entry_price)
            - open_fee_per_coin
            - close_fee_per_coin
        )

    def _validate_levels(self, levels):
        for level in levels:
            price = self._decimal(level.price)
            qty = self._decimal(level.qty)
            fee = self._decimal(level.fee)
            initial_qty = self._decimal(level.initial_qty)

            if price <= 0:
                raise ValueError(f"Invalid level price: {price}")

            if qty <= 0:
                raise ValueError(f"Invalid level qty: {qty}")

            if fee < 0:
                raise ValueError(f"Invalid level fee: {fee}")

            if initial_qty < 0:
                raise ValueError(
                    f"Invalid initial quantity: {initial_qty}"
                )

            units = self._to_units(qty)
            normalized_qty = self._from_units(units)

            if abs(qty - normalized_qty) > EPS:
                raise ValueError(
                    f"Level qty is not a multiple of qty_step: {qty}"
                )

    def _to_units(self, qty) -> int:
        value = self._decimal(qty) / self.qty_step
        rounded = value.to_integral_value(rounding=ROUND_FLOOR)

        if abs(value - rounded) > EPS:
            raise ValueError(
                f"Quantity is not a multiple of qty_step: {qty}"
            )

        return int(rounded)

    def _to_units_floor(self, qty) -> int:
        value = self._decimal(qty) / self.qty_step
        return int(value.to_integral_value(rounding=ROUND_FLOOR))

    def _to_units_ceil(self, qty) -> int:
        value = self._decimal(qty) / self.qty_step
        return int(value.to_integral_value(rounding=ROUND_CEILING))

    def _from_units(self, units: int) -> Decimal:
        return units * self.qty_step

    @staticmethod
    def _decimal(value) -> Decimal:
        return Decimal(str(value))
