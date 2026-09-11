from action_processor.action import Action, ActionCommand
from action_processor.action_service import ActionService
from action_processor.process_result import ProcessResult
from action_processor.action_source import ActionSource


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
                source=ActionSource.EXTERNAL_COMMAND
            )

            process_result.action_command = action_command            

            return self.action_service.process_action(
                action_command=action_command,
                process_result=process_result
            )

        self.logger.error(
            f"Неизвестная внешняя команда: {command}"
        )

        return process_result