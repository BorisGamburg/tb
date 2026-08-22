from dataclasses import dataclass
from rich.text import Text

from prog.action_processor.action import Action, ActionCommand
from prog.utils.utils import get_inverse_side


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
        runtime=None,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side
        self.logger = logger
        self.telegram = telegram
        self.runtime = runtime

        self._last_state: tuple | None = None

    def is_allowed(self, act_cmd: ActionCommand) -> bool:
        if not act_cmd:
            self._update_status(None)
            return False

        result = self._check(act_cmd)

        self._update_status(act_cmd, result)
        self._handle_state_change(act_cmd, result)

        return result.allowed

    def _check(
        self,
        act_cmd: ActionCommand,
    ) -> GuardResult:

        if act_cmd.action == Action.CLOSE:
            levels = act_cmd.levels

            if not self.can_close_levels(levels):
                return GuardResult(
                    allowed=False,
                    reason="hedge_ratio",
                )

        return GuardResult(
            allowed=True,
        )

    def can_close_levels(
        self,
        levels,
    ) -> bool:

        if not levels:
            return True

        close_qty = sum(
            level.qty
            for level in levels
        )

        main_pos = self.proxy_driver.get_position(
            self.symbol,
            self.side,
        )
        main_qty = float(
            main_pos["size"]
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
        act_cmd: ActionCommand | None,
        result: GuardResult | None = None,
    ) -> None:
        if self.runtime is None:
            return

        if act_cmd is None or result is None or result.allowed:
            self.runtime.guard_status = None
            return

        action_name = act_cmd.action.value.upper()

        status = Text()
        status.append(
            action_name,
            style="white on red",
        )
        status.append(
            f" BLOCK({result.reason})"
        )

        self.runtime.guard_status = status    

    def _handle_state_change(
        self,
        act_cmd: ActionCommand,
        result: GuardResult,
    ) -> None:
        action_name = act_cmd.action.value.upper()
        state = (
            action_name,
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
            f"{action_name} BLOCKED | "
            f"reason={result.reason}"
        )

        self.logger.warning(message)
        self.telegram.send_telegram_message(message)        