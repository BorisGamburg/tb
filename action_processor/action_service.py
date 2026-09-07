from action_processor.execution.execution import Execution
from action_processor.accounting import Accounting
from action_processor.notifier import Notifier
from action_processor.bootstrap import AppContext
from action_processor.state.state import State
from action_processor.process_result import ProcessResult


class ActionService:

    def __init__(
        self,
        app_ctx: AppContext,
        state_store: State,
    ):
        self.execution = Execution(
            proxy_driver=app_ctx.proxy_driver,
            price_service=app_ctx.price_service,
            logger=app_ctx.logger,
        )

        self.accounting = Accounting(
            state_store=state_store,
        )

        self.notifier: Notifier = app_ctx.notifier

    def process_action(
        self,
        action_command,
        process_result: ProcessResult,
    ):
        # Логируем команду
        self.notifier.notify_action(action_command)

        # Запускаем Executor
        exec_result = self.execution.execute(action_command)

        # Заносим результаты в process_result
        process_result.price = exec_result.price
        process_result.qty = exec_result.qty
        process_result.fee = exec_result.fee
        process_result.executed = exec_result.executed        

        # Логируем результат попытки
        self.notifier.log_execution(exec_result)

        if not exec_result.executed:
            return process_result

        # Уведомляем о фактическом исполнении
        self.notifier.notify_telegram(exec_result)

        # Запускаем Accounter
        accounting_message = self.accounting.apply(process_result)

        # Логируем результаты
        self.notifier.log(accounting_message)
        self.notifier.log_trade_table(exec_result)

        return process_result