from dataclasses import dataclass
from action_processor.action import ActionCommand
from action_processor.execution.limit_order_result import LimitOrderStatus


@dataclass
class ExecutionResult:
    action_command: ActionCommand
    price: float | None = None
    qty: float | None = None
    fee: float | None = None
    executed: bool = False
    status: LimitOrderStatus | None = None