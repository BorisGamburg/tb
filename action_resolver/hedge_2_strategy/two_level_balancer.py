from math import ceil


def ceil_to_step(value, step):
    return ceil(value / step) * step


class TwoLevelBalancer:

    OK = 0

    ERR_EQUAL_PROFIT_PER_UNIT = 1

    ERR_NEGATIVE_FAR_QTY = 2
    ERR_NEGATIVE_NEAR_QTY = 3

    ERR_FAR_QTY_EXCEEDED = 4

    ERR_REALIZED_PROFIT_BELOW_REQUIRED = 5

    @staticmethod
    def _compute_initial_split(
        exec_price,
        near_level_price,
        far_level_price,
        compensated_loss,
        profit_buffer,
        profitable_close_qty,
        qty_step,
    ):
        # Получаем дистанции уровней от цены закрытия
        p_near = abs(exec_price - near_level_price)
        p_far = abs(exec_price - far_level_price)

        # Если дистанции равны, то не наш случай
        if p_far == p_near:
            return (
                TwoLevelBalancer.ERR_EQUAL_PROFIT_PER_UNIT,
                {
                    "p_near": p_near,
                    "p_far": p_far,
                },
            )

        # Получаем размер прибыли, который надо покрыть
        required_profit = compensated_loss + profit_buffer

        # Рассчитываем кол-во для дальнего уровня
        far_consumed_qty = (
            (required_profit - p_near * profitable_close_qty)
            / (p_far - p_near)
        )

        # Округляем до шага вверх
        far_consumed_qty = ceil_to_step(
            far_consumed_qty,
            qty_step,
        )

        # Рассчитываем кол-во для ближнего уровня как остаток
        near_consumed_qty = profitable_close_qty - far_consumed_qty

        return None, {
            "p_near": p_near,
            "p_far": p_far,
            "required_profit": required_profit,
            "near_consumed_qty": near_consumed_qty,
            "far_consumed_qty": far_consumed_qty,
        }

    @staticmethod
    def solve(
        profitable_close_qty,
        compensated_loss,
        profit_buffer,

        exec_price,

        near_level_price,
        near_level_available_qty,

        far_level_price,
        far_level_available_qty,

        qty_step,
    ):
        err, split = TwoLevelBalancer._compute_initial_split(
            exec_price,
            near_level_price,
            far_level_price,
            compensated_loss,
            profit_buffer,
            profitable_close_qty,
            qty_step,
        )
        if err is not None:
            return (err, split)

        p_near = split["p_near"]
        p_far = split["p_far"]
        required_profit = split["required_profit"]
        near_consumed_qty = split["near_consumed_qty"]
        far_consumed_qty = split["far_consumed_qty"]

        # Это обозначает, что даже если весь объем
        # закрытия отправить на дальний уровень,
        # прибыли все равно недостаточно.
        if near_consumed_qty < 0:
            return (
                TwoLevelBalancer.ERR_NEGATIVE_NEAR_QTY,
                {"near_consumed_qty": near_consumed_qty}
            )

        # Если расчетный размер для дальнего уровня получился отрицательный или
        # расчетный размер для ближнего уровня превосходит наличное кол-во, то
        # отъедаем ликвидность сверху
        if (
            far_consumed_qty < 0
            or
            near_consumed_qty > near_level_available_qty
        ):
            near_consumed_qty = min(profitable_close_qty, near_level_available_qty)
            far_consumed_qty = profitable_close_qty - near_consumed_qty

        # Локвидности на дальнем уровне недостаточно для погашения убытка
        if far_consumed_qty > far_level_available_qty:
            return (
                TwoLevelBalancer.ERR_FAR_QTY_EXCEEDED,
                {
                    "required_far_qty": far_consumed_qty,
                    "available_far_qty": (
                        far_level_available_qty
                    ),
                }
            )

        # Рассчитываем прибыль с обоих уровней 
        realized_profit = (
            p_near * near_consumed_qty
            + p_far * far_consumed_qty
        )

        # Хватает ли прибыли для покрытия убытка?
        if realized_profit < required_profit:
            return (
                TwoLevelBalancer.ERR_REALIZED_PROFIT_BELOW_REQUIRED,
                {
                    "required_profit": required_profit,
                    "realized_profit": realized_profit,
                }
            )

        return (
            TwoLevelBalancer.OK,
            {
                "near_consumed_qty": (
                    near_consumed_qty
                ),

                "far_consumed_qty": (
                    far_consumed_qty
                ),

                "required_profit": (
                    required_profit
                ),

                "realized_profit": (
                    realized_profit
                ),

                "profit_excess": (
                    realized_profit
                    - required_profit
                ),
            }
        )