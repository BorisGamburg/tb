from action_processor.execution.execution import Execution
from action_processor.accounting import Accounting
from action_processor.bootstrap import AppContext
from action_processor.state.state import State
from action_processor.process_result import ProcessResult
from action_processor.execution.execution_result import ExecutionResult
from action_processor.trade_table_logger import TradeTableLogger
from action_processor.action import Action, ActionCommand
from action_processor.execution.limit_order_result import LimitOrderStatus


class ActionService:

    def __init__(
        self,
        app_ctx: AppContext,
        state_store: State,
    ):
        self.logger = app_ctx.logger
        self.state_store = state_store
        self.telegram = app_ctx.telegram
        
        self.execution = Execution(
            proxy_driver=app_ctx.proxy_driver,
            price_service=app_ctx.price_service,
            logger=app_ctx.logger,
        )

        self.accounting = Accounting(
            state_store=state_store,
        )

        self.trade_table_logger = TradeTableLogger(
            trade_logger=app_ctx.trade_logger,
            state_store=state_store,
        )

    def process_action(
        self,
        action_command: ActionCommand,
        process_result: ProcessResult,
    ) -> ProcessResult:
        # Логируем команду
        self.notify_action(action_command)

        # Запускаем Executor
        exec_result = self.execution.execute(action_command)

        # Заносим результаты в process_result
        process_result.action_command = exec_result.action_command
        process_result.price = exec_result.price
        process_result.qty = exec_result.qty
        process_result.fee = exec_result.fee
        process_result.executed = exec_result.executed        

        if not exec_result.executed:
            return process_result

        # Уведомляем о фактическом исполнении
        self.log_execution(exec_result)
        self.notify_telegram(exec_result)

        # Запускаем Accounter
        accounting_message = self.accounting.apply(process_result)

        # Логируем результаты
        self.logger.info(accounting_message)
        self.trade_table_logger.log_trade_table(exec_result)

        return process_result

    def log_execution(self, exec_result):
        self.logger.info(
            f"[EXECUTION] action={exec_result.action_command.action.value} "
            f"| side={exec_result.action_command.side} "
            f"| qty={exec_result.qty} "
            f"| price={exec_result.price}"
        )
    
    def notify_telegram(self, exec_result: ExecutionResult):
        tg_msg = self._build_message(exec_result)
        if tg_msg and self.telegram:
            self.telegram.send_telegram_message(tg_msg)        

    def _build_message(
        self,
        result: ExecutionResult,
    ) -> str | None:
        """
        Формирует текст уведомления.
        """
        symbol = self.state_store.data.symbol
        side = self.state_store.data.side

        if result.action_command.action == Action.OPEN:
            reason = result.action_command.reason
            source = result.action_command.source.value

            if result.status == LimitOrderStatus.PARTIALLY_FILLED:
                return (
                    "💎 LEVEL PARTIALLY OPENED\n"
                    f"Symbol: {symbol}\n"
                    f"Side: {side}\n"
                    f"Qty: {result.qty}\n"
                    f"Price: {result.price}\n"
                    "Status: PARTIALLY_FILLED\n"
                    f"Reason: {reason}\n"
                    f"Source: {source}"
                )

            return (
                "💎 LEVEL OPENED\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}\n"
                f"Reason: {reason}\n"
                f"Source: {source}"
            )
            
        
        if result.action_command.action == Action.CLOSE:
            reason = result.action_command.reason
            source = result.action_command.source.value

            return (
                "📉 LEVELS CLOSED\n"
                f"Symbol: {symbol}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}\n"
                f"Reason: {reason}\n"
                f"Source: {source}"
            )

        return None

    def notify_action(self, act_cmd: ActionCommand) -> None:
        action = act_cmd.action.value.upper()
        reason = act_cmd.reason or "N/A"

        self.logger.info(
            f"[ACTION] {action} | reason={reason}"
        )    

    