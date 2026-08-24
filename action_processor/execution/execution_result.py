from dataclasses import dataclass
from action_processor.action import ActionCommand


@dataclass
class ExecutionResult:
    action_command: ActionCommand
    price: float | None = None
    qty: float | None = None
    fee: float | None = None
