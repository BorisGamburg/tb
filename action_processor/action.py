from dataclasses import dataclass
from enum import Enum
from action_processor.state.stack_schema import StackElem
from action_resolver.grid_mtf_strategy.entry_checker import EntryCheckDetails
from action_resolver.grid_mtf_strategy.partial_exit_bbw import BBWCheckDetails


class Action(Enum):
    NO_ACTION = "no_action"
    OPEN = "open"
    CLOSE = "close"
    CLOSE_POSITION = "close_position"
    CLOSE_PARTIAL = "close_partial"

@dataclass
class ActionDetails:
    entry_check: EntryCheckDetails | None = None
    bbw_exit: BBWCheckDetails | None = None  

@dataclass
class ActionCommand:
    action: Action
    symbol: str
    side: str | None = None
    qty: float | None = None
    levels: list[StackElem] | None = None
    reason: str | None = None
    details: ActionDetails | None = None
