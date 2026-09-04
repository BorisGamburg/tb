from dataclasses import dataclass
from rich.text import Text

from action_processor.action import Action, ActionCommand
from utils.utils import get_inverse_side


@dataclass(frozen=True, slots=True)
class GuardResult:
    allowed: bool
    reason: str | None = None


class ActionGuard:
    def __init__(
        self,
        proxy_driver,
        symbol,
        side,
        logger,
        telegram,
        runtime,
        state_store,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side
        self.logger = logger
        self.telegram = telegram
        self.runtime = runtime
        self.state_store = state_store

        self._last_state: tuple | None = None

    def is_allowed(self) -> bool:
        result = self._check()

        self._update_status(result)
        self._handle_state_change(result)

        return result.allowed

    def _check(self) -> GuardResult:

        candidate = self._get_most_profitable_level(
            self.state_store.stack_mng.data.entries,
        )
        if candidate is None:
            return GuardResult(
                allowed=True,
            )

        if not self.can_close_levels([candidate]):
            return GuardResult(
                allowed=False,
                reason="hedge_ratio",
            )

        return GuardResult(
            allowed=True,
        )

    def _get_most_profitable_level(self, levels):
        if not levels:
            return None

        if self.side == "Sell":
            return max(
                levels,
                key=lambda level: float(level.price),
            )

        return min(
            levels,
            key=lambda level: float(level.price),
        )

    def can_close_levels(
        self,
        levels,
    ) -> bool:

        if not levels:
            return True

        close_qty = sum(
            float(level.qty)
            for level in levels
        )

        entries = self.state_store.stack_mng.data.entries
        main_qty = sum(
            float(entry.qty)
            for entry in entries
        )

        hedge_pos = self.proxy_driver.get_position(
            self.symbol,
            get_inverse_side(self.side),
        )
        hedge_qty = float(
            hedge_pos["size"]
        )

        new_main_qty = main_qty - close_qty

        return new_main_qty >= hedge_qty * 2

    def _update_status(
        self,
        result: GuardResult | None = None,
    ) -> None:
        if self.runtime is None:
            return

        if result is None:
            self.runtime.guard_status = None
            return

        if result.allowed:
            status = Text()
            status.append(
                "CLOSE",
                style="white on green",
            )
            status.append(" ALLOWED")
            self.runtime.guard_status = status
            return

        status = Text()
        status.append(
            "CLOSE",
            style="white on red",
        )
        status.append(
            f" BLOCK({result.reason})"
        )

        self.runtime.guard_status = status

    def _handle_state_change(
        self,
        result: GuardResult,
    ) -> None:
        state = (
            "CLOSE",
            result.allowed,
            result.reason,
        )

        if state == self._last_state:
            return

        self._last_state = state

        if result.allowed:
            return

        message = (
            f"{self.symbol} | "
            f"ACTION GUARD | "
            f"CLOSE BLOCKED | "
            f"reason={result.reason}"
        )

        self.logger.warning(message)
        self.telegram.send_telegram_message(message)        