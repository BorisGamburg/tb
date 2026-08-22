from pydantic import BaseModel, Field, ConfigDict
from prog.action_processor.state.pct import Pct
from prog.action_processor.state.types import AllowedTimeframes


class DynamicOffset(BaseModel):

    tf: AllowedTimeframes
    bbw_coeff: float = Field(gt=0)


class MapElem(BaseModel):

    model_config = ConfigDict(extra="forbid")

    qty_pct: Pct

    tf: AllowedTimeframes
    tf_filter: AllowedTimeframes
    tf_filter_macro: AllowedTimeframes
    tf_cci_fast: AllowedTimeframes
    tf_cci_slow: AllowedTimeframes
    tf_rsi: AllowedTimeframes

    avdo_offset_min_pct: Pct
    avdo_dyn: DynamicOffset

    prta_offset_min_pct: Pct