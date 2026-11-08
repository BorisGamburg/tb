from pydantic import BaseModel, ConfigDict
from typing import Literal

from action_processor.state.pct import Pct
from action_processor.state.stack_schema import StackData
from action_processor.state.types import AllowedTimeframes


class PyrSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Основное ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    entry_tf: AllowedTimeframes
    open_step_pct: Pct
    open_qty_pct: Pct
    close_band_width_pct: Pct

    # --- Свёртывание стека по порогу L/P ---
    trigger_pct: Pct = 10.0      # запуск, если L/P выше
    target_pct: Pct = 5.0        # цель возврата L/P
    min_pnl: float = 0.0         # минимальный итог закрытия, USDT
    min_stack_pct: Pct           # минимальный размер стека, % от баланса    

    sleep_interval: float

    # Уведомления в Telegram об открытии/закрытии ордеров
    order_notifications_enabled: bool = False

    # --- Stack / текущие уровни ---
    stack: StackData