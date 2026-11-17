from decimal import Decimal, ROUND_CEILING


class PyrPartialCloseCalculator:

    def calc_proportional_reductions(
        self,
        levels,
        executed_qty: float,
        qty_step: float,
        side: str,
    ):
        if len(levels) != 2:
            raise ValueError(
                f"Expected exactly two levels, got {len(levels)}"
            )

        level_1, level_2 = levels

        profitable_level = self._get_profitable_level(
            level_1,
            level_2,
            side,
        )

        total_qty = level_1.qty + level_2.qty

        profitable_reduction = self._calc_profitable_reduction(
            executed_qty=executed_qty,
            profitable_qty=profitable_level.qty,
            total_qty=total_qty,
            qty_step=qty_step,
        )

        loss_reduction = self._calc_loss_reduction(
            executed_qty=executed_qty,
            profitable_reduction=profitable_reduction,
        )

        if profitable_level is level_1:
            return profitable_reduction, loss_reduction

        return loss_reduction, profitable_reduction

    def _get_profitable_level(
        self,
        level_1,
        level_2,
        side: str,
    ):
        if side == "Sell":
            return (
                level_1
                if level_1.price < level_2.price
                else level_2
            )

        if side == "Buy":
            return (
                level_1
                if level_1.price > level_2.price
                else level_2
            )

        raise ValueError(f"Unsupported side: {side}")

    def _calc_profitable_reduction(
        self,
        executed_qty: float,
        profitable_qty: float,
        total_qty: float,
        qty_step: float,
    ):
        profitable_reduction_raw = (
            executed_qty * profitable_qty / total_qty
        )

        return self.ceil_to_step(
            profitable_reduction_raw,
            qty_step,
        )

    def _calc_loss_reduction(
        self,
        executed_qty: float,
        profitable_reduction: float,
    ):
        loss_reduction = executed_qty - profitable_reduction

        if loss_reduction < 0:
            raise ValueError(
                "Calculated loss reduction is negative: "
                f"{loss_reduction}"
            )

        return loss_reduction

    def ceil_to_step(self, value: float, step: float) -> float:
        value_decimal = Decimal(str(value))
        step_decimal = Decimal(str(step))

        lower = (value_decimal // step_decimal) * step_decimal
        upper = lower + step_decimal

        if value_decimal == lower:
            return float(lower)

        return float(upper)

    def calc_sequential_reductions(
        self,
        levels,
        executed_qty: float,
        side: str,
    ) -> list[float]:
        """
        Распределяет исполненный объём по уровням, начиная с наименее
        прибыльных и двигаясь к наиболее прибыльным: каждый уровень
        закрывается целиком, пока хватает объёма, последний — частично.

        side — сторона ордера закрытия (как в calc_proportional_reductions):
        "Sell" закрывает long, наименее прибыльный уровень — с наибольшей
        ценой входа; "Buy" закрывает short, наименее прибыльный — с
        наименьшей ценой входа. Возвращает редукции в исходном порядке levels.
        """
        if not levels:
            raise ValueError("Expected at least one level")

        if side not in ("Buy", "Sell"):
            raise ValueError(f"Unsupported side: {side}")

        qtys = [Decimal(str(level.qty)) for level in levels]
        total = sum(qtys)
        executed = Decimal(str(executed_qty))

        if executed <= 0:
            raise ValueError(f"Executed qty must be positive: {executed_qty}")
        if executed > total:
            raise ValueError(
                f"Executed qty exceeds total levels qty | "
                f"executed={executed_qty} | total={total}"
            )

        # Сортировка устойчива: при равных ценах порядок уровней сохраняется
        order = sorted(
            range(len(levels)),
            key=lambda i: levels[i].price,
            reverse=(side == "Sell"),
        )

        reductions = [Decimal(0)] * len(levels)
        remaining = executed

        for i in order:
            if remaining <= 0:
                break

            reduction = min(qtys[i], remaining)
            reductions[i] = reduction
            remaining -= reduction

        return [float(value) for value in reductions]
    def calc_bundle_reductions(
        self,
        base_qty: float,
        loss_qty: float,
        executed_qty: float,
        qty_step: float,
    ) -> tuple[float, float]:
        """
        Распределяет исполненный объём связки (Base целиком + кусок убыточного
        уровня) пропорционально объёмам частей. Доля прибыльной части (Base)
        округляется вверх по qty_step, остаток уходит на убыточную часть.

        Возвращает (редукция Base, редукция убыточного уровня).
        """
        base = Decimal(str(base_qty))
        loss = Decimal(str(loss_qty))
        executed = Decimal(str(executed_qty))
        step = Decimal(str(qty_step))
        total = base + loss

        if base <= 0 or loss <= 0:
            raise ValueError(
                f"Bundle parts must be positive | base={base_qty} | loss={loss_qty}"
            )
        if executed <= 0:
            raise ValueError(f"Executed qty must be positive: {executed_qty}")
        if executed > total:
            raise ValueError(
                f"Executed qty exceeds bundle qty | "
                f"executed={executed_qty} | total={total}"
            )

        base_raw = executed * base / total
        base_reduction = (base_raw / step).to_integral_value(
            rounding=ROUND_CEILING
        ) * step
        base_reduction = min(base_reduction, base, executed)

        loss_reduction = executed - base_reduction
        if loss_reduction < 0 or loss_reduction > loss:
            raise ValueError(
                f"Invalid bundle reductions | "
                f"base_reduction={base_reduction} | loss_reduction={loss_reduction}"
            )

        return float(base_reduction), float(loss_reduction)
