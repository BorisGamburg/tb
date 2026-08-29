import time
from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.hedge_2_strategy.hedge_mode_mng import HedgeModeMng
from action_resolver.hedge_2_strategy.mode_to_action_transformer import transform
from action_resolver.hedge_2_strategy.hedge_status import HedgeStatus
from action_resolver.resolve_result import ResolveResult
from common.trading_info import TradingInfo
from action_processor.action import Action, ActionCommand


class Hedge2Strategy(BaseStrategy):
    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ) -> None:

        super().__init__()

        self.app_ctx = app_ctx
        self.state_store = state_store
        self.proxy_driver = app_ctx.proxy_driver

        self.symbol = state_store.data.symbol

        self.hedge_mode_mng = HedgeModeMng(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

        self._log_parameters()

    def resolve(self, external_command) -> ResolveResult:
        external_result = self._handle_external_command(external_command)
        if external_result is not None:
            return external_result

        # Получаем режим
        mode_result, status = self.hedge_mode_mng.check()

        # Преобразуем режим в команду действия
        action_command = transform(
            mode_result,
            symbol=self.symbol,
            side=self.state_store.data.side,
        )

        # Формируем статусную строку
        status_line = self._build_status_line(status=status)

        return ResolveResult(
            action_command=action_command,
            status=status_line,
            skip_sleep=False,
        )

    def _build_status_line(
        self,
        status: HedgeStatus,
    ) -> str:
        protection_ok = status.protection_current >= status.protection_required
        protection_mark = "✓" if protection_ok else "✗"
        return (
            f"BID/ASK: {status.bid:.6f} — {status.ask:.6f} | "
            f"PROTECTION: {status.protection_current:.3f}/"
            f"{status.protection_required:.3f} {protection_mark} | "
            f"PNL: {status.pnl:+.6f} | "
            f"MODE: {status.mode.name} | "
            f"PAIRS: {status.pairs}"
        )


    def _log_parameters(self) -> None:
        self.app_ctx.logger.info(
            f"Symbol: {self.state_store.data.symbol} | "
            f"Side: {self.state_store.data.side}"
        )

    def on_iteration(self) -> None:
        self.app_ctx.notifier.log(
            self.app_ctx.notifier.build_stack_report()
        )        

    def _handle_external_command(
        self,
        external_command,
    ) -> ResolveResult | None:

        if not external_command:
            return None

        command = external_command.get("command")

        if command == "CLOSE_POSITION":
            action_command = ActionCommand(
                action=Action.CLOSE_POSITION,
                symbol=self.symbol,
                side=self.state_store.data.side,
            )

            return ResolveResult(
                action_command=action_command,
                status="CLOSE_POSITION",
                skip_sleep=False,
            )

        if command == "TEST":
            print("TEST")
            return ResolveResult(
                action_command=None,
                status="TEST",
                skip_sleep=False,
            )

        return None        