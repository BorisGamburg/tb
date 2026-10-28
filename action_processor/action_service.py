from action_processor.execution.execution import Execution
from action_processor.accounting import Accounting
from action_processor.bootstrap import AppContext
from action_processor.state.state import State
from action_processor.execution.execution_result import ExecutionResult
from action_processor.action import ActionCommand
from common.trading_info import TradingInfo


class ActionService:

    def __init__(
        self,
        app_ctx: AppContext,
        state_store: State,
        trading_info: TradingInfo,
    ):
        self.logger = app_ctx.logger
        self.state_store = state_store
        
        self.execution = Execution(
            app_ctx=app_ctx,
            trading_info=trading_info,
            order_notifications_enabled=(
                state_store.data.order_notifications_enabled
            ),
        )

        self.accounting = Accounting(
            state_store=state_store,
            logger=app_ctx.logger,
        )

    def process_action(
        self,
        action_command: ActionCommand,
    ) -> ExecutionResult:
        # Логируем команду
        self.notify_action(action_command)

        # Запускаем Executor
        exec_result = self.execution.execute(action_command)

        if not exec_result.executed:
            return exec_result

        # Запускаем Accounter
        self.accounting.apply(
            action=exec_result.action_command.action,
            price=exec_result.price,
            qty=exec_result.qty,
            fee=exec_result.fee,
            levels=exec_result.action_command.levels,
        )

        return exec_result

    def notify_action(self, act_cmd: ActionCommand) -> None:
        action = act_cmd.action.value.upper()
        reason = act_cmd.reason or "N/A"

        self.logger.info(
            f"[ACTION] {action} | reason={reason}"
        )    

    