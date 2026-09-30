from action_processor.action import Action, ActionCommand
from action_processor.action_service import ActionService
from action_processor.process_result import ProcessResult


class ExternalCommandProcessor:

    def __init__(
        self,
        symbol: str,
        side: str,
        action_service: ActionService,
        logger,
    ):
        self.symbol = symbol
        self.side = side
        self.action_service = action_service
        self.logger = logger

    def process(
        self,
        process_result: ProcessResult,
    ):
        if not process_result.external_command:
            return process_result

        command = process_result.external_command.get("command")

        if command == "CLOSE_POSITION":
            action_command = ActionCommand(
                action=Action.CLOSE_POSITION,
                symbol=self.symbol,
                side=self.side,
            )

            process_result.action_command = action_command            

            exec_result = self.action_service.process_action(
                action_command=action_command,
            )

            process_result.action_command = exec_result.action_command
            process_result.price = exec_result.price
            process_result.qty = exec_result.qty
            process_result.fee = exec_result.fee
            process_result.executed = exec_result.executed

            return process_result
        
        self.logger.error(
            f"Неизвестная внешняя команда: {command}"
        )

        return process_result