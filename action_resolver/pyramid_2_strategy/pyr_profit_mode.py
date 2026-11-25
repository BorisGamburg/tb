from action_resolver.resolve_result import ResolveResult
from action_resolver.pyramid_2_strategy.pyr_be_close import PyrBeClose
from action_resolver.pyramid_2_strategy.pyr_close_processor import (
    PyrCloseProcessor,
)
from common.rearm import Rearm
from action_resolver.pyramid_2_strategy.pyr_extension_close import (
    PyrExtensionClose,
)
from common.recovery.ha_breakout_opener import (
    PyrHaBreakoutOpener,
)
from action_resolver.pyramid_2_strategy.pyr_extension_open import (
    PyrExtensionOpen,
)


class PyrProfitMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        open_checker,
        close_processor: PyrCloseProcessor,
        unwinder,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
        self.close_processor = close_processor

        self.rearm = Rearm(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            get_qty=open_checker.get_qty,
            step_ratio=open_checker.step_ratio,
        )

        self.extension_close = PyrExtensionClose(
            state_store=state_store,
            app_ctx=app_ctx,
            close_processor=close_processor,
            rearm=self.rearm,
            step_ratio=open_checker.step_ratio,
            min_close_steps=state_store.data.min_close_steps,
        )

        # Условие минимальной дистанции для 2 уровней общее с Extension.
        self.be_close = PyrBeClose(
            state_store=state_store,
            app_ctx=app_ctx,
            trading_info=trading_info,
            unwinder=unwinder,
            be_close_buffer_pct=state_store.data.be_close_buffer_pct,
            check_distance=self.extension_close.check_distance_for_two_levels,
        )

        # Используем тот же HA Breakout, который уже создан в EntryChecker.
        self.ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            ha_signal=open_checker.ha_signal,
        )

        self.ha_breakout = PyrExtensionOpen(
            state_store=state_store,
            app_ctx=app_ctx,
            trading_info=trading_info,
            open_checker=open_checker,
            ha_opener=self.ha_opener,
        )

    def resolve(self) -> ResolveResult:
        # Закрытие всего стека по BE приоритетнее остальных действий
        be_close_result = self.be_close.process()

        if be_close_result is not None:
            return be_close_result

        close_result = self.extension_close.process()

        if close_result is not None:
            return close_result

        return self.ha_breakout.process()

    def get_close_target(self) -> float | None:
        """Цена, при которой закроется ближайший Extension (для статуса)."""
        return self.extension_close.get_target_price()