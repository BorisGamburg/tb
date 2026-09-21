from pydantic import BaseModel, Field, ConfigDict
from typing import List


class StackElem(BaseModel):
    price: float
    qty: float
    stop_price: float = Field(default=0.0)
    stop_active: bool = Field(default=False)
    fee: float = Field(default=0.0)
    initial_qty: float = Field(default=0.0)  # добавлено
    
class StackData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    entries: List[StackElem] = Field(default_factory=list)