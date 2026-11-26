"""Набор таймфреймов (лесенка) с коэффициентом Боллинджера на каждой ступени.

Модель хранится прямо в конфиге стратегии и сохраняется в YAML вместе с
текущим индексом:

    recovery_tf:
        index: 2
        steps:
            - tf: "1"
              bb: 0.5
            - tf: "15"
              bb: 0.4

bb обязателен у каждой ступени, значения по умолчанию нет.
"""
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from action_processor.state.types import AllowedTimeframes


class TfStep(BaseModel):

    model_config = ConfigDict(extra="forbid")

    tf: AllowedTimeframes
    # Фильтр Боллинджера: 0 < bb <= 1 (1 - фильтр ничего не отсекает)
    bb: float

    @field_validator("bb")
    @classmethod
    def _check_bb(cls, v: float) -> float:
        if not 0 < v <= 1:
            raise ValueError(f"bb={v} must be in (0, 1]")
        return v


class TimeframeSet(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    steps: list[TfStep]
    index: int = 0

    @model_validator(mode="after")
    def _check_index(self):
        if not self.steps:
            raise ValueError("steps must not be empty")
        if not 0 <= self.index < len(self.steps):
            raise ValueError(
                f"index={self.index} is out of range "
                f"for {len(self.steps)} steps"
            )
        return self

    @property
    def step(self) -> TfStep:
        return self.steps[self.index]

    @property
    def tf(self) -> str:
        """Текущий таймфрейм."""
        return self.step.tf

    @property
    def bb(self) -> float:
        """Коэффициент Боллинджера текущей ступени."""
        return self.step.bb

    def advance(self) -> bool:
        """На следующую ступень. False, если уже на последней."""
        if self.index >= len(self.steps) - 1:
            return False
        self.index += 1
        return True

    def reset(self) -> bool:
        """На первую ступень. False, если уже на ней."""
        if self.index == 0:
            return False
        self.index = 0
        return True
