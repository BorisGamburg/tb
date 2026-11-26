from pydantic import BaseModel, ConfigDict, model_validator
from typing import Literal

from action_processor.state.pct import Pct
from action_processor.state.stack_schema import StackData
from common.timeframe.timeframe_set import TimeframeSet


class PyrSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Основное ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    # Наборы таймфреймов (с коэффициентом Боллинджера на каждой ступени):
    # profit_tf - вход в EMPTY и Extension, recovery_tf - новый Base.
    profit_tf: TimeframeSet
    recovery_tf: TimeframeSet

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
    def _check_be_buffers(self):
        # Иначе бот открывал бы уровень и сразу закрывал стек по BE.
        if not 0 <= self.be_close_buffer_pct < self.min_be_buffer_pct:
            raise ValueError(
                f"be_close_buffer_pct={self.be_close_buffer_pct} must be "
                f">= 0 and < min_be_buffer_pct={self.min_be_buffer_pct}"
            )
        return self

    def advance_tf(self) -> bool:
        """После открытия уровня: обе лесенки на следующую ступень."""
        profit = self.profit_tf.advance()
        recovery = self.recovery_tf.advance()
        return profit or recovery

    def reset_tf(self) -> bool:
        """После полного закрытия стека: обе лесенки на первую ступень."""
        profit = self.profit_tf.reset()
        recovery = self.recovery_tf.reset()
        return profit or recovery
