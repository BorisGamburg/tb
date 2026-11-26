from pydantic import BaseModel, ConfigDict
from typing import Literal

from action_processor.state.pct import Pct
from action_processor.state.stack_schema import StackData
from common.timeframe.timeframe_set import TimeframeSet


class RecoverySchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Основное ---
    symbol: str
    side: Literal["Buy", "Sell"]
    strategy: str

    # Набор таймфреймов нового Base (с коэффициентом Боллинджера)
    recovery_tf: TimeframeSet

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

    def advance_tf(self) -> bool:
        """После открытия уровня: лесенка на следующую ступень."""
        return self.recovery_tf.advance()

    def reset_tf(self) -> bool:
        """После полного закрытия стека: лесенка на первую ступень."""
        return self.recovery_tf.reset()
