from pydantic import BaseModel, ConfigDict
from typing import Literal

from action_processor.state.pct import Pct
from action_processor.state.stack_schema import StackData
from action_processor.state.types import AllowedTimeframes


class PyramidSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Основное ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    entry_tf: AllowedTimeframes
    hedge_step_pct: Pct
    hedge_qty_pct: Pct
    profit_tolerance_pct: Pct

    sleep_interval: float

    # Уведомления в Telegram об открытии/закрытии ордеров
    order_notifications_enabled: bool = False

    # --- Stack / текущие уровни ---
    stack: StackData