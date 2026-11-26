from pydantic import BaseModel, ConfigDict, model_validator
from typing import Literal

from action_processor.state.pct import Pct
from action_processor.state.stack_schema import StackData
from action_processor.state.types import AllowedTimeframes


class RecoverySchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Основное ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    # Список таймфреймов и номер текущего в нём (с нуля).
    # Текущий таймфрейм входа: timeframes[tf_index].
    timeframes: list[AllowedTimeframes] = [
        "1", "5", "15", "60", "240", "720"
    ]
    tf_index: int = 0

    # Шаг и объём нового уровня (новый Base, REARM)
    open_step_pct: Pct
    open_qty_pct: Pct

    # Минимальный итог компенсации, USDT
    min_pnl: float = 0.0

    sleep_interval: float

    # Уведомления в Telegram об открытии/закрытии ордеров
    order_notifications_enabled: bool = False

    # --- Stack / текущие уровни ---
    stack: StackData

    @model_validator(mode="after")
    def _check_timeframes(self):
        if not self.timeframes:
            raise ValueError("timeframes must not be empty")
        if not 0 <= self.tf_index < len(self.timeframes):
            raise ValueError(
                f"tf_index={self.tf_index} is out of range "
                f"for timeframes={self.timeframes}"
            )
        return self

    @property
    def entry_tf(self) -> str:
        """Текущий таймфрейм входа."""
        return self.timeframes[self.tf_index]

    def advance_tf(self) -> bool:
        """Переходит на следующий таймфрейм списка.

        Возвращает True, если индекс был изменён. На последнем таймфрейме
        остаёмся на нём и возвращаем False.
        """
        if self.tf_index >= len(self.timeframes) - 1:
            return False
        self.tf_index += 1
        return True
