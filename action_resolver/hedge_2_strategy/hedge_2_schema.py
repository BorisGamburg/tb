from pydantic import BaseModel, ConfigDict
from typing import Literal
from action_processor.state.pct import Pct
from action_processor.state.stack_schema import StackData
from action_processor.state.types import AllowedTimeframes


class Hedge2Schema(BaseModel):
    """Минимальная конфигурация для DD-хеджа."""
    
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Основное ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    hedge_step_pct: Pct
    hedge_qty_pct: Pct

    profit_tolerance_pct: Pct
    loss_tolerance_pct: Pct
        
    # Start
    start_tf: AllowedTimeframes | None

    sleep_interval: float

    # --- Stack / текущие уровни ---
    stack: StackData

