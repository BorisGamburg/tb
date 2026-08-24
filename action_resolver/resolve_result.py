from dataclasses import dataclass
from action_processor.action import ActionCommand

@dataclass(frozen=True)
class ResolveResult:
    action_command: ActionCommand | None
    status: str
    skip_sleep: bool