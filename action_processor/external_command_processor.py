from action_processor.action import Action, ActionCommand
from action_processor.action_service import ActionService


class ExternalCommandProcessor:

    def __init__(
        self,
        symbol: str,
        side: str,
        action_service: ActionService,
    ):
        self.symbol = symbol
        self.side = side
        self.action_service = action_service

    def process(self, external_command):
        if not external_command:
            return None

        command = external_command.get("command")

        if command == "CLOSE_POSITION":
            action_command = ActionCommand(
                action=Action.CLOSE_POSITION,
                symbol=self.symbol,
                side=self.side,
            )

            return self.action_service.process_action(
                action_command
            )

        if command == "TEST":
            print("TEST")
            return None

        return None