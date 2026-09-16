# action_resolver/hedge_2_strategy/close_processor.py

from action_processor.execution.limit_order_result import LimitOrderStatus
from action_processor.process_result import ProcessResult
from action_processor.action import ActionCommand
from action_resolver.hedge_2_strategy.partial_close_calculator import (
    PartialCloseCalculator,
)


class CloseProcessor:

    def __init__(
        self,
        action_service,
        partial_close_calculator: PartialCloseCalculator,
        trading_info,
    ):
        self.action_service = action_service
        self.partial_close_calculator = partial_close_calculator
        self.trading_info = trading_info

    def execute(
        self,
        action_command: ActionCommand,
        process_result: ProcessResult,
        status_line: str,
    ) -> ProcessResult:
        exec_result = self.action_service.execution.execute(
            action_command,
        )

        process_result.action_command = exec_result.action_command
        process_result.price = exec_result.price
        process_result.qty = exec_result.qty
        process_result.fee = exec_result.fee
        process_result.executed = exec_result.executed

        if not exec_result.executed:
            process_result.status = status_line
            return process_result

        if exec_result.status == LimitOrderStatus.PARTIALLY_FILLED:
            return self._execute_partial(
                exec_result,
                process_result,
                status_line,
            )

        if exec_result.status == LimitOrderStatus.FILLED:
            return self._execute_filled(
                exec_result,
                process_result,
                status_line,
            )

        raise ValueError(
            f"Unexpected CLOSE execution status: {exec_result.status}"
        )

    def _execute_filled(
        self,
        exec_result,
        process_result: ProcessResult,
        status_line: str,
    ) -> ProcessResult:
        self.action_service.accounting.apply(
            action=exec_result.action_command.action,
            price=exec_result.price,
            qty=exec_result.qty,
            fee=exec_result.fee,
            levels=exec_result.action_command.levels,
        )

        process_result.status = status_line
        return process_result

    def _execute_partial(
        self,
        exec_result,
        process_result: ProcessResult,
        status_line: str,
    ) -> ProcessResult:
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

        process_result.status = status_line
        return process_result

