from action_processor.execution.limit_order_result import LimitOrderStatus
from action_processor.execution.execution_result import ExecutionResult
from action_processor.action import ActionCommand
from action_resolver.hedge_2_strategy.partial_close_calculator import (
    PartialCloseCalculator,
)
from action_processor.action_service import ActionService


class CloseProcessor:

    def __init__(
        self,
        action_service: ActionService,
        partial_close_calculator: PartialCloseCalculator,
        trading_info,
    ):
        self.action_service = action_service
        self.partial_close_calculator = partial_close_calculator
        self.trading_info = trading_info

    def execute(
        self,
        action_command: ActionCommand,
    ) -> ExecutionResult:
        exec_result = self.action_service.execution.execute(action_command)

        if not exec_result.executed:
            return exec_result

        if exec_result.status == LimitOrderStatus.PARTIALLY_FILLED:
            self._execute_partial(exec_result)
            return exec_result

        if exec_result.status == LimitOrderStatus.FILLED:
            self._execute_filled(exec_result)
            return exec_result

        raise ValueError(
            f"Unexpected CLOSE execution status: {exec_result.status}"
        )

    def _execute_filled(
        self,
        exec_result,
    ):
        self.action_service.accounting.apply(
            action=exec_result.action_command.action,
            price=exec_result.price,
            qty=exec_result.qty,
            fee=exec_result.fee,
            levels=exec_result.action_command.levels,
        )

    def _execute_partial(
        self,
        exec_result,
    ):
        levels = exec_result.action_command.levels
        executed_qty = exec_result.qty

        reductions = (
            self.partial_close_calculator.calc_proportional_reductions(
                levels=levels,
                executed_qty=executed_qty,
                qty_step=self.trading_info.qty_step,
                side=exec_result.action_command.side,
            )
        )

        reduction_1, reduction_2 = reductions
        level_1, level_2 = levels
        new_qty_1 = level_1.qty - reduction_1
        new_qty_2 = level_2.qty - reduction_2

        if new_qty_1 < 0 or new_qty_2 < 0:
            raise ValueError(
                f"Partial close produced negative level qty | "
                f"new_qty_1={new_qty_1} | "
                f"new_qty_2={new_qty_2}"
            )

        if new_qty_1 == 0:
            self.action_service.accounting.remove_level(level_1)
        else:
            self.action_service.accounting.update_level_qty(
                level_1,
                new_qty_1,
            )

        if new_qty_2 == 0:
            self.action_service.accounting.remove_level(level_2)
        else:
            self.action_service.accounting.update_level_qty(
                level_2,
                new_qty_2,
            )


