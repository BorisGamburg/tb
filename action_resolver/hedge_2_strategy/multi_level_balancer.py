from prog.action_resolver.hedge_2_strategy.two_level_balancer import (
    TwoLevelBalancer,
)


class MultiLevelBalancer:

    OK = 0

    ERR_NOT_ENOUGH_LEVELS = 1
    ERR_ALL_PAIRS_FAILED = 2

    #
    # Last pair failed because:
    #
    # required far qty exceeds
    # far level available qty.
    #
    # Caller should switch to
    # consume fallback logic.
    #

    ERR_LAST_FAR_LEVEL_OVERFLOW = 3

    @staticmethod
    def solve(
        profitable_close_qty,
        compensated_loss,
        profit_buffer,
        exec_price,
        levels,
        qty_step,
    ):
        """
        Attempts to solve balancing problem
        using adjacent level pairs.

        levels:
            sorted from nearest -> farthest

        level format:
            {
                "price": float,
                "available_qty": float,
            }

        Strategy:

            Try:
                (level_0, level_1)
                (level_1, level_2)
                ...
                (level_n-2, level_n-1)

            using TwoLevelBalancer.

            First successful solution wins.
        """

        if len(levels) < 2:

            return (
                MultiLevelBalancer.ERR_NOT_ENOUGH_LEVELS,
                {
                    "levels_count": len(levels),
                }
            )

        pair_errors = []

        last_pair_index = len(levels) - 2

        for i in range(len(levels) - 1):
            near_level = levels[i]
            far_level = levels[i + 1]

            code, payload = TwoLevelBalancer.solve(
                profitable_close_qty=profitable_close_qty,
                compensated_loss=compensated_loss,
                profit_buffer=profit_buffer,
                exec_price=exec_price,
                near_level_price=near_level["price"],
                near_level_available_qty=near_level["available_qty"],
                far_level_price=far_level["price"],
                far_level_available_qty=far_level["available_qty"],
                qty_step=qty_step,
            )

            if code == TwoLevelBalancer.OK:
                return (
                    MultiLevelBalancer.OK,
                    {
                        "pair_index": i,
                        "near_level_index": i,
                        "far_level_index": i + 1,
                        "near_level_price": near_level["price"],
                        "far_level_price": far_level["price"],
                        **payload,
                    }
                )

            # Last pair failed because far level capacity exhausted.
            # Caller should switch to consume fallback.
            if (i == last_pair_index
                and 
                code == TwoLevelBalancer.ERR_FAR_QTY_EXCEEDED
            ):
                return (
                    MultiLevelBalancer.ERR_LAST_FAR_LEVEL_OVERFLOW,
                    {"pair_index": i, "two_level_payload": payload}
                )

            pair_errors.append(
                {
                    "pair_index": i,
                    "two_level_code": code,
                    "two_level_payload": payload,
                }
            )

        return (
            MultiLevelBalancer.ERR_ALL_PAIRS_FAILED,
            {"pair_errors": pair_errors}
        )