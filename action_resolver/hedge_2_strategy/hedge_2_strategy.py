import time

from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.hedge_2_strategy.hedge_mode_mng import HedgeModeMng
from action_resolver.hedge_2_strategy.mode_to_action_transformer import transform
from action_resolver.hedge_2_strategy.hedge_status import HedgeStatus
from action_resolver.resolve_result import ResolveResult
from common.trading_info import TradingInfo


class Hedge2Strategy(BaseStrategy):
    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ) -> None:

        super().__init__()

        self.state_store = state_store
        self.proxy_driver = app_ctx.proxy_driver
        self.logger = app_ctx.logger

        self.symbol = state_store.data.symbol

        self.hedge_mode_mng = HedgeModeMng(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

    def resolve(self, external_command) -> ResolveResult:
        if external_command and external_command.get("command") == "TEST":
            print("TEST")
            return ResolveResult(
                action_command=None,
                status="TEST",
                skip_sleep=False,
            )

        if external_command and external_command.get("command") == "TEST_TIMEOUT":
            time.sleep(10)

        self.logger.info(self.build_stack_report())

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

    def _get_current_tf_info(self) -> str:
        """Определяет активный темплейт и таймфрейм для текущего уровня стека."""
        map_mng = getattr(self.state_store, 'map_mng', None)
        stack = self.state_store.data.stack
        level = len(stack.entries) if stack and stack.entries else 0

        if not map_mng:
            return "MAP_MNG: N/A"

        try:
            tf = map_mng.get_tf_for_level(level)

            template_name = "unknown"
            if hasattr(map_mng, 'templates_sorted') and level < len(map_mng.templates_sorted):
                template_name, _ = map_mng.templates_sorted[level]
            elif hasattr(map_mng, 'templates_sorted') and level >= len(map_mng.templates_sorted):
                template_name = "MAX_LEVEL"

            return f"TEMPLATE: {template_name} | TF: {tf}"

        except Exception as e:
            return f"TF_INFO: Error ({e})"

    def build_stack_report(self) -> str:
        stack = self.state_store.data.stack
        level = len(stack.entries) if stack and stack.entries else 0

        tf_info = self._get_current_tf_info()

        lines = [
            tf_info,
            f"STACK SIZE: {level}"
        ]

        if level > 0:
            sorted_entries = sorted(
                stack.entries,
                key=lambda x: x.price,
                reverse=True,
            )

            visible_entries = sorted_entries[-10:]

            for i, e in enumerate(visible_entries):
                lines.append(
                    f"[{i:02d}] "
                    f"{e.price:>10.6f} | "
                    f"{e.qty:>8.2f}"
                )
        else:
            lines.append("STACK: empty")

        return "\n".join(lines)
