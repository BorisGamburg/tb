from action_processor.execution.limit_order_result import LimitOrderStatus
from action_processor.execution.execution_result import ExecutionResult
from action_processor.action import ActionCommand, Action
from action_processor.action_service import ActionService
from action_resolver.pyramid_strategy.pyramid_partial_close_calculator import (
    PyramidPartialCloseCalculator,
)


class PyramidCloseProcessor:

    def __init__(
        self,
        action_service: ActionService,
        partial_close_calculator: PyramidPartialCloseCalculator,
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
    ) -> ExecutionResult:
        """
        Закрытие всех уровней пирамиды лимитным ордером на их суммарный qty
        (позиции других стратегий на бирже не затрагиваются).

        Учёт строится по фактически исполненному объёму: если исполнено
        меньше запрошенного, закрываются уровни от наименее прибыльных
        к наиболее прибыльным, остаток остаётся в стеке.
        """
        # Исполнение команды и контроль результата
        exec_result = self._execute_and_check(action_command)

        # Ордер не исполнился -> стек не меняем
        if not exec_result.executed:
            return exec_result

        # Учёт: обновляем уровни стека по фактически исполненному объёму
        self._apply_profit_close(action_command.levels, exec_result)

        return exec_result

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

    def _apply_profit_close(self, levels, exec_result: ExecutionResult):
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
            return

        # Исполнено частично -> закрываем уровни, начиная с наименее прибыльных
        reductions = self.partial_close_calculator.calc_sequential_reductions(
            levels=levels,
            executed_qty=filled_qty,
            side=exec_result.action_command.side,
        )
        accounting.reduce_levels(levels, reductions)