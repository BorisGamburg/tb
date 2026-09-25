from dataclasses import dataclass
from action_processor.action import ActionCommand
from rich.text import Text


@dataclass
class ProcessResult:

    external_command: dict | None
    action_command: ActionCommand | None
    status: Text
    executed: bool
    signal: bool
    price: float
    qty: float
    fee: float