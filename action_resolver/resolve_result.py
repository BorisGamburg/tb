from dataclasses import dataclass

from action_processor.action import ActionCommand



@dataclass(frozen=True)
class ResolveResult:
    executed: bool
    status: str