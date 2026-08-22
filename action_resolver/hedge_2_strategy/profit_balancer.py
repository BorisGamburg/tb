from prog.action_resolver.hedge_2_strategy.multi_level_balancer import (
    MultiLevelBalancer,
)

from prog.action_resolver.hedge_2_strategy.consume_planner import (
    ConsumePlanner,
)


class ProfitBalancer:

    OK = 0

    ERR_BALANCER_FAILED = 1

    @staticmethod
    def balance(
        profitable_close_qty,
        compensated_loss,
        profit_buffer,
        exec_price,
        levels,
        qty_step,
    ):
        """
        High-level profit balancing coordinator.

        Strategy:

            1. Try MultiLevelBalancer
            2. If farthest level overflows:
               switch to consume fallback
        """

        code, payload = MultiLevelBalancer.solve(
            profitable_close_qty=profitable_close_qty,
            compensated_loss=compensated_loss,
            profit_buffer=profit_buffer,

            exec_price=exec_price,

            levels=levels,

            qty_step=qty_step,
        )

        #
        # Balanced solution found
        #

        if code == MultiLevelBalancer.OK:

            return (
                ProfitBalancer.OK,
                {
                    "balance_type": "balanced",
                    **payload,
                }
            )

        #
        # Fallback:
        # consume from far levels
        #

        if (
            code
            == MultiLevelBalancer.ERR_LAST_FAR_LEVEL_OVERFLOW
        ):

            planner = ConsumePlanner()

            consume_levels = list(
                reversed(levels)
            )

            consume_actions = planner.plan(
                levels=consume_levels,
                qty=profitable_close_qty,
            )

            return (
                ProfitBalancer.OK,
                {
                    "balance_type": "consume",
                    "consume_actions": consume_actions,
                    "multi_level_payload": payload,
                }
            )

        #
        # Balancing failed
        #

        return (
            ProfitBalancer.ERR_BALANCER_FAILED,
            {
                "multi_level_code": code,
                "multi_level_payload": payload,
            }
        )