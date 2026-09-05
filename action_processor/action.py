from dataclasses import dataclass
from enum import Enum
from action_processor.state.stack_schema import StackElem
from action_processor.action_source import ActionSource


class Action(Enum):
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
    source: ActionSource | None = None