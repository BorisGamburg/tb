
from pydantic import BaseModel, ConfigDict


class OrchestratorSchema(BaseModel):

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    symbol: str
    strategy: str
    managed_strategies: list[str]
    sleep_interval: float

    # Уведомления в Telegram об открытии/закрытии ордеров (опционально)
    order_notifications_enabled: bool = False
