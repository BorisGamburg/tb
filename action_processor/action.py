from dataclasses import dataclass
from enum import Enum
from action_processor.state.stack_schema import StackElem


class Action(Enum):
    NO_ACTION = "no_action"
    OPEN = "open"
    CLOSE = "close"
    CLOSE_POSITION = "close_position"
    CLOSE_PARTIAL = "close_partial"

@dataclass
class ActionCommand:
    action: Action
    symbol: str
    side: str | None = None
    qty: float | None = None
    levels: list[StackElem] | None = None
    reason: str | None = None
