from dataclasses import dataclass
from action_processor.action import ActionCommand


@dataclass
class ProcessResult:

    external_command: dict | None
    action_command: ActionCommand | None
    status: str
    executed: bool
    signal: bool
    price: float
    qty: float
    fee: float