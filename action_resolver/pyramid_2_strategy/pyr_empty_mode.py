from action_resolver.resolve_result import ResolveResult
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_opener import (
    PyrHaBreakoutOpener,
)
from action_resolver.pyramid_2_strategy.pyr_tf_advance import advance_entry_tf


class PyrEmptyMode:
    """Режим пустого стека: ждём HA-сигнал и открываем Base."""

    def __init__(
        self,
        state_store,
        app_ctx,
        action_service,
        open_checker,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.action_service = action_service
        self.open_checker = open_checker

        # Используем тот же HA Breakout, который уже создан в EntryChecker.
        self.ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            ha_signal=open_checker.ha_signal,
        )

    def resolve(self) -> ResolveResult:
        # Проверяем HA Signal
        if not self.ha_opener.has_signal():
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: NO SIGNAL",
            )

        # Получаем qty
        qty = self.open_checker.get_qty()
        if qty <= 0:
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (QTY = 0)",
            )

        # Стек пустой -> открываем Base по сигналу,
        # без проверки дистанции и буфера BE.
        result = self.ha_opener.open(qty, "BASE (EMPTY STACK)")

        # Открыт Base -> переходим на следующий таймфрейм списка
        if result.executed:
            advance_entry_tf(self.state_store, self.app_ctx)

        return result