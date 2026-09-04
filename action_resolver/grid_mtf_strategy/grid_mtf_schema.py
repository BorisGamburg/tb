from pydantic import BaseModel, ConfigDict
from typing import Dict, Literal

from action_processor.state.stack_schema import StackData
from action_processor.state.pct import Pct
from action_processor.state.types import AllowedTimeframes


class GridMTFTemplate(BaseModel):

    model_config = ConfigDict(extra="forbid")

    tf_filter: AllowedTimeframes              
    tf_rsi_entry_threshold: float
    htf_filter: AllowedTimeframes
    htf_rsi_entry_threshold: float
    htf_rsi_rearm_threshold: float

    qty_pct: Pct            # Обычно нужно для расчета объема


class GridMTFSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- GENERAL ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str
    min_rearm_distance_pct: Pct
    min_profit_pct: Pct
    max_profit_pct: Pct
    sleep_interval: int  # Интервал сна в секундах
    exit_guard_enabled: bool

    # Start
    require_start_condition: bool
    start_condition_type: Literal["ha_reversal", "structure_break"] | None
    start_tf: AllowedTimeframes | None
    start_rsi_threshold: float

    # --- TP ---
    tp_price: float = 0.0
    tp_enabled: bool = False

    # --- STACK ---
    stack: StackData

    # --- TEMPLATE STAGES ---
    templates: Dict[int, GridMTFTemplate]