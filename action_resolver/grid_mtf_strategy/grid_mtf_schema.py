from pydantic import BaseModel, ConfigDict
from typing import Dict, Literal

from action_processor.state.stack_schema import StackData
from action_processor.state.pct import Pct
from action_processor.state.types import AllowedTimeframes


class GridMTFTemplate(BaseModel):

    model_config = ConfigDict(extra="forbid")

    entry_tf_ha_rsi: AllowedTimeframes
    entry_tf_threshold_rsi: float
    entry_bb_rearm_rsi_htf: AllowedTimeframes
    rearm_rsi_htf_threshold: float
    entry_dist_tf_bbw: AllowedTimeframes
    entry_dist_multiplier_bbw: float
    exit_tf_bbw: AllowedTimeframes
    qty_pct: Pct


class GridMTFSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- GENERAL ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str
    min_rearm_distance_pct: Pct
    min_profit_pct: Pct
    max_profit_bb_pct: Pct
    sleep_interval: int  # Интервал сна в секундах
    exit_guard_enabled: bool
    merge_threshold_pct: Pct

    # --- TP ---
    tp_price: float = 0.0
    tp_enabled: bool = False

    # --- STACK ---
    stack: StackData

    # --- TEMPLATE STAGES ---
    templates: Dict[int, GridMTFTemplate]