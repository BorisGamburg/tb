from dataclasses import dataclass
from enum import Enum
from action_processor.state.stack_schema import StackElem


class Action(Enum):
    OPEN = "open"
    CLOSE = "close"
    
@dataclass
class ActionCommand:
    action: Action
    symbol: str
    side: str | None = None
    qty: float | None = None
    levels: list[StackElem] | None = None
    reason: str | None = None