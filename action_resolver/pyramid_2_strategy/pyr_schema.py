from pydantic import BaseModel, ConfigDict, model_validator
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

    # Список таймфреймов и номер текущего в нём (с нуля).
    # Текущий таймфрейм входа: timeframes[tf_index].
    timeframes: list[AllowedTimeframes] = [
        "1", "5", "15", "60", "240", "720"
    ]
    tf_index: int = 0

    open_step_pct: Pct
    open_qty_pct: Pct
    min_be_buffer_pct: Pct
    # Полоса закрытия стека над BE (Profit): закрываем, если буфер до BE
    # не больше этого значения. Должна быть меньше min_be_buffer_pct.
    be_close_buffer_pct: Pct
    min_close_steps: int

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

    @model_validator(mode="after")
    def _check_be_buffers(self):
        # Иначе бот открывал бы уровень и сразу закрывал стек по BE.
        if not 0 <= self.be_close_buffer_pct < self.min_be_buffer_pct:
            raise ValueError(
                f"be_close_buffer_pct={self.be_close_buffer_pct} must be "
                f">= 0 and < min_be_buffer_pct={self.min_be_buffer_pct}"
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