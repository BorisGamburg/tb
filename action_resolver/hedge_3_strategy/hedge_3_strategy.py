from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.hedge_3_strategy.hedge_mode_mng import HedgeModeMng
from action_resolver.hedge_3_strategy.mode_to_action_transformer import transform
from action_resolver.hedge_3_strategy.hedge_status import HedgeStatus
from action_resolver.resolve_result import ResolveResult
from common.trading_info import TradingInfo
from action_processor.action import Action, ActionCommand
from signals.ha_reversal_signal import HAReversalSignal
from action_resolver.hedge_3_strategy.build_mng import calc_hedge_qty
from action_processor.action_service import ActionService
from action_resolver.hedge_3_strategy.hedge_unwind import UnwindResult
from common.unwind.unwinder import Unwinder
from common.level_distance_checker import is_level_distance_allowed


class Hedge3Strategy(BaseStrategy):
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
        self.trading_info = trading_info

        self.action_service = ActionService(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

        self.unwinder = Unwinder(
            action_service=self.action_service,
            trading_info=trading_info,
            logger=app_ctx.logger,
        )

        self.hedge_mode_mng = HedgeModeMng(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
            unwinder=self.unwinder,
        )

        self.ha_signal = HAReversalSignal(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

        self._log_parameters()

    def __build_status_line(
        self,
        status: HedgeStatus,
        build_trend_active: bool = False,
        build_distance_allowed: bool = False,
    ) -> str:
        protection_ok = status.protection_current >= status.protection_required
        protection_mark = "✓" if protection_ok else "✗"

        mode_text = status.mode.name
        if status.mode.name == "UNWIND" and status.unwind_wait:
            mode_text = "UNWIND (WAIT)"

        if status.zone_low is not None and status.zone_high is not None:
            zone = f"{status.zone_low:.3f} — {status.zone_high:.3f}"
        else:
            zone = "—"

        if status.scheme == "B":
            tail = f"UNWIND: {status.scheme_info}"
        else:
            tail = f"ZONE: {zone}"

        build_indicator = ""
        if status.mode.name == "BUILD":
            ha_status = "ALLOW" if build_trend_active else "BLOCK"
            dist_marker = "🟢" if build_distance_allowed else "🔴"
            build_indicator = (
                f"  HA({self.state_store.data.start_tf}m): {ha_status} "
                f" DIST: {dist_marker}"
            )

        return (
            f"BID/ASK: {status.bid:.6f} — {status.ask:.6f} | "
            f"PROTECTION: cur={status.protection_current:.3f} "
            f"req={status.protection_required:.3f} {protection_mark} | "
            f"PNL: {status.pnl:+.6f} | "
            f"SCHEME: {status.scheme} | "
            f"MODE: {mode_text}"
            f"{build_indicator} | "
            f"{tail} | "
            f"RECOVERY: {'ON' if self.state_store.data.recovery_enabled else 'OFF'}  "
            f"TF: {self.state_store.data.recovery_timeframe}"
        )

    def _log_parameters(self) -> None:
        self.app_ctx.logger.info(
            f"Symbol: {self.state_store.data.symbol} | "
            f"Side: {self.state_store.data.side}"
        )

    def _check_recovery(self) -> tuple[bool, ActionCommand]:
        empty_result = ActionCommand(
            action=Action.NO_ACTION,
            symbol=self.symbol,
        )

        # Если recovery не нужен, то выходим
        if not self.state_store.data.recovery_enabled:
            return False, empty_result

        # Читаем параметры нужные для recovery
        rec_tf = self.state_store.data.recovery_timeframe
        side = self.state_store.data.side

        if not self._check_level_distance(side):
            return False, empty_result     

        is_reversal, _ = self.ha_signal.is_entry(tf=rec_tf, side=side)
        if is_reversal:
            # Получаем размер уровня для recovery
            qty = self._calc_recovery_qty()
            if qty == 0.0:
                return False, empty_result

            # Отключаем recovery-флаг
            self.state_store.data.recovery_enabled = False
            self.state_store.save()

            # Формируем команду для открытия уровня
            action_command = ActionCommand(
                action=Action.OPEN,
                symbol=self.symbol,
                side=side,
                qty=qty,
                reason="recovery_reversal",
            )

            return True, action_command

        return False, empty_result

    def _calc_recovery_qty(self) -> float:
        side = self.state_store.data.side
        main_side = "Sell" if side == "Buy" else "Buy"

        main_pos = self.proxy_driver.get_position(self.symbol, main_side)
        main_qty = float(main_pos["size"])

        hedge_qty_ratio = self.state_store.data.hedge_qty_pct / 100
        return calc_hedge_qty(
            main_qty=main_qty,
            hedge_qty_ratio=hedge_qty_ratio,
            trading_info=self.trading_info,
        )

    def resolve(
        self,
    ) -> ResolveResult:
        # 1. Проверяем одноразовый триггер Recovery
        recovery_triggered, action_command = self._check_recovery()
        if recovery_triggered:
            exec_result = self.action_service.process_action(action_command)

            return ResolveResult(
                executed=exec_result.executed,
                status="",
            )

        # Основная стратегия
        return self._check_mode_action()

    def _check_mode_action(
        self,
    ) -> ResolveResult:
        # Получаем режим
        mode_result, status = self.hedge_mode_mng.check()

        # Формируем статусную строку
        status_line = self._build_status_line(mode_result, status)

        # Сворачивание идёт через Unwinder, а не через команду действия
        if isinstance(mode_result, UnwindResult):
            return self._process_unwind(mode_result, status_line)

        # Преобразуем режим в команду действия
        action_command = transform(
            mode_result,
            symbol=self.symbol,
            side=self.state_store.data.side,
        )

        # Получаем ResolveResult и возвращаем его
        return self._get_resolve_result(action_command, status_line)

    def _process_unwind(
        self,
        result: UnwindResult,
        status_line: str,
    ) -> ResolveResult:
        if not result.found:
            # Безубыточного объёма нет: ждём следующего тика
            return ResolveResult(executed=False, status=status_line)

        entries = self.state_store.stack_mng.data.entries
        try:
            exec_result = self.unwinder.run(
                levels=entries,
                side=self.state_store.data.side,
                symbol=self.symbol,
                qty=result.qty,
                price=result.price,
                min_pnl=result.min_pnl,
                profit_order=result.profit_order,
            )
        except Exception as e:
            raise RuntimeError(
                f"HEDGE unwind failed | qty={result.qty} "
                f"price={result.price} steps={result.steps} | "
                f"error: {e!r}"
            ) from e

        executed = exec_result is not None and exec_result.executed
        return ResolveResult(executed=executed, status=status_line)

    def _get_resolve_result(
        self,
        action_command: ActionCommand,
        status_line: str,
    ) -> ResolveResult:
        if action_command.action == Action.NO_ACTION:
            return ResolveResult(
                executed=False,
                status=status_line,
            )

        if action_command.action == Action.OPEN:
            exec_result = self.action_service.process_action(
                action_command,
            )

            return ResolveResult(
                executed=exec_result.executed,
                status=status_line,
            )

        raise ValueError(
            f"Unsupported action in Hedge3Strategy: {action_command.action}"
        ) 

    def _build_status_line(self, mode_result, status):
        build_trend_active = (
            mode_result.trend_active
            if status.mode.name == "BUILD"
            else False
        )

        build_distance_allowed = (
            mode_result.distance_allowed
            if status.mode.name == "BUILD"
            else False
        )

        status_line = self.__build_status_line(
            status=status,
            build_trend_active=build_trend_active,
            build_distance_allowed=build_distance_allowed,
        )
        return status_line   

    def _check_level_distance(
        self,
        side: str,
    ) -> bool:
        cur_price = self.app_ctx.price_service.get_active_price(
            symbol=self.symbol,
            side=side,
        )

        entries = self.state_store.stack_mng.data.entries
        hedge_step_ratio = (
            self.state_store.data.hedge_step_pct / 100
        )

        return is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=hedge_step_ratio,
        )