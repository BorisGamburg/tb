from action_resolver.resolve_result import ResolveResult
from action_resolver.pyramid_2_strategy.pyr_close_processor import (
    PyrCloseProcessor,
)
from common.rearm import Rearm
from action_resolver.pyramid_2_strategy.pyr_extension_close import (
    PyrExtensionClose,
)
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_opener import (
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
        close_result = self.extension_close.process()

        if close_result is not None:
            return close_result

        return self.ha_breakout.process()