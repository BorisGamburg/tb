from dataclasses import dataclass
from action_processor.action import ActionCommand


@dataclass
class ProcessResult:
    external_command: dict | None = None
    action_command: ActionCommand | None = None
    status: str | None = None
    executed: bool | None = None
    signal: bool | None = None
    price: float | None = None
    qty: float | None = None
    fee: float | None = None