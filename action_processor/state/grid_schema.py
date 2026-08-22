from pydantic import BaseModel, ConfigDict
from typing import Dict, Literal

from prog.action_processor.state.stack_schema import StackData
from prog.action_processor.state.map_elem import MapElem
from prog.action_processor.state.pct import Pct


class GridSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- GENERAL ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    # --- EXCHANGE PARAMS ---
    min_qty: float = 0.0
    step_size: float = 0.0

    # --- POSITION LIMIT ---
    max_position_pct: Pct

    # --- REBALANCE ---
    rebalance_activation_pct: Pct
    rebalance_ratio: float
    rebalance_enabled: bool

    # --- STACK ---
    stack: StackData

    # --- MAP ---
    templates: Dict[str, MapElem]