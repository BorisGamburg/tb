from action_processor.execution.limit_order_result import LimitOrderStatus
from action_processor.execution.execution_result import ExecutionResult
from action_processor.action import ActionCommand, Action
from action_processor.action_service import ActionService
from action_resolver.pyramid_2_strategy.pyr_partial_close_calculator import (
    PyrPartialCloseCalculator,
)
from dataclasses import dataclass


@dataclass
class PyrCloseResult:
    execution_result: ExecutionResult
    fully_closed: bool


class PyrCloseProcessor:

    def __init__(
        self,
        action_service: ActionService,
        partial_close_calculator: PyrPartialCloseCalculator,
        trading_info,
    ):
        self.action_service = action_service
        self.partial_close_calculator = partial_close_calculator
        self.trading_info = trading_info

    def _execute_filled(self, exec_result):
        self.action_service.accounting.apply(
            action=exec_result.action_command.action,
            price=exec_result.price,
            qty=exec_result.qty,
            fee=exec_result.fee,
            levels=exec_result.action_command.levels,
        )

    def _execute_partial(self, exec_result):
        levels = exec_result.action_command.levels
        executed_qty = exec_result.qty

        reductions = self.partial_close_calculator.calc_proportional_reductions(
            levels=levels,
            executed_qty=executed_qty,
            qty_step=self.trading_info.qty_step,
            side=exec_result.action_command.side,
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

    def execute_profit_close(
        self,
        action_command: ActionCommand,
    ) -> PyrCloseResult:

        exec_result = self._execute_and_check(action_command)

        if not exec_result.executed:
            return PyrCloseResult(
                execution_result=exec_result,
                fully_closed=False,
            )

        fully_closed = self._apply_profit_close(
            action_command.levels,
            exec_result,
        )

        return PyrCloseResult(
            execution_result=exec_result,
            fully_closed=fully_closed,
        )

    def _execute_and_check(
        self,
        action_command: ActionCommand,
    ) -> ExecutionResult:
        # Выполняем команду
        exec_result = self.action_service.execution.execute(action_command)

        # Не выполнена -> выходим
        if not exec_result.executed:
            return exec_result

        # Статус ордера неожиданный -> исключение
        if exec_result.status not in (
            LimitOrderStatus.FILLED,
            LimitOrderStatus.PARTIALLY_FILLED,
        ):
            raise ValueError(
                f"Unexpected CLOSE execution status: {exec_result.status}"
            )

        # Исполненный объём некорректен -> исключение
        if exec_result.qty <= 0:
            raise ValueError(
                f"Profit close executed with non-positive qty: "
                f"{exec_result.qty}"
            )

        # Исполнено больше, чем есть на уровнях пирамиды: затронут чужой объём
        total_qty = sum(level.qty for level in action_command.levels or [])
        tolerance = self.trading_info.qty_step / 2
        if exec_result.qty > total_qty + tolerance:
            raise RuntimeError(
                f"Profit close filled more than pyramid qty | "
                f"filled={exec_result.qty} | pyramid_qty={total_qty}"
            )

        return exec_result

    def _apply_profit_close(self, levels, exec_result: ExecutionResult) -> bool:
        levels = list(levels or [])
        total_qty = sum(level.qty for level in levels)
        filled_qty = exec_result.qty
        tolerance = self.trading_info.qty_step / 2
        accounting = self.action_service.accounting

        # Исполнено всё -> закрываем все уровни целиком
        if abs(total_qty - filled_qty) <= tolerance:
            accounting.apply(
                action=Action.CLOSE,
                price=exec_result.price,
                qty=filled_qty,
                fee=exec_result.fee,
                levels=levels,
            )
            return True

        # Исполнено частично -> закрываем уровни, начиная с наименее прибыльных
        reductions = self.partial_close_calculator.calc_sequential_reductions(
            levels=levels,
            executed_qty=filled_qty,
            side=exec_result.action_command.side,
        )
        accounting.reduce_levels(levels, reductions)

        return False


    def execute_compensation_close(
        self,
        action_command: ActionCommand,
        base_qty: float,
        loss_qty: float,
    ) -> PyrCloseResult:
        """
        Закрытие связки одним ордером: Base целиком + кусок убыточного уровня.

        action_command.levels = [base_level, loss_level], qty команды - сумма
        base_qty и loss_qty. Учёт строится по фактически исполненному объёму:
        при полном исполнении Base закрывается целиком, с убыточного уровня
        списывается loss_qty; при частичном - объём распределяется между
        частями пропорционально, остаток остаётся в стеке.
        """
        levels = list(action_command.levels or [])
        if len(levels) != 2:
            raise ValueError(
                f"Compensation close expects exactly two levels, got {len(levels)}"
            )

        qty_step = self.trading_info.qty_step
        tolerance = qty_step / 2
        total_qty = base_qty + loss_qty

        if action_command.qty is None or abs(action_command.qty - total_qty) > tolerance:
            raise ValueError(
                f"Compensation command qty mismatch | "
                f"command_qty={action_command.qty} | "
                f"base_qty={base_qty} | loss_qty={loss_qty}"
            )

        # Исполнение команды и контроль результата
        exec_result = self._execute_and_check(action_command)

        # Ордер не исполнился -> стек не меняем
        if not exec_result.executed:
            return PyrCloseResult(
                execution_result=exec_result,
                fully_closed=False,
            )

        filled_qty = exec_result.qty

        # Исполнено больше, чем в связке: затронут чужой объём
        if filled_qty > total_qty + tolerance:
            raise RuntimeError(
                f"Compensation close filled more than bundle qty | "
                f"filled={filled_qty} | bundle_qty={total_qty}"
            )

        # Исполнено всё -> закрываем Base целиком и loss_qty на убыточном уровне
        if abs(total_qty - filled_qty) <= tolerance:
            reductions = [base_qty, loss_qty]
            fully_closed = True
        else:
            # Исполнено частично -> распределяем пропорционально частям
            reductions = list(
                self.partial_close_calculator.calc_bundle_reductions(
                    base_qty=base_qty,
                    loss_qty=loss_qty,
                    executed_qty=filled_qty,
                    qty_step=qty_step,
                )
            )
            fully_closed = False

        self.action_service.accounting.reduce_levels(levels, reductions)

        return PyrCloseResult(
            execution_result=exec_result,
            fully_closed=fully_closed,
        )
