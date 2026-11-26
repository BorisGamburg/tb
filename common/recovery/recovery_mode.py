"""RecoveryMode: универсальный Recovery-модуль пирамиды.

Один вызов resolve() = один шаг:
  1. пробуем компенсацию (Base закрывается вместе с убыточными уровнями,
     затем REARM);
  2. если компенсации нет, пробуем открыть новый Base по HA-сигналу.

Модуль не определяет режим стратегии, не смотрит на положение цены
относительно BE или Base и не проверяет дистанцию между уровнями:
решение, запускать ли его, принимает вызывающая стратегия.

Требования к конфигу стратегии (state_store.data): symbol, side, stack,
min_pnl, advance_tf(), reset_tf().
Таймфрейм сигнала берётся из TimeframeSet, который передан в ha_opener.
"""
from common.compensation.compensation_planner import CompensationPlanner
from common.compensation.recovery_compensation import (
    CompensationOutcome,
    RecoveryCompensation,
)
from common.rearm import Rearm
from common.recovery.base_open import BaseOpen
from common.recovery.ha_breakout_opener import PyrHaBreakoutOpener
from common.unwind.unwinder import Unwinder
from action_resolver.resolve_result import ResolveResult


class RecoveryMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        unwinder: Unwinder,
        ha_opener: PyrHaBreakoutOpener,
        get_qty,
        step_ratio: float,
        rearm_if_empty: bool = True,
    ):
        """
        ha_opener      - HA-сигнал, цена входа и открытие уровня;
        get_qty        - () -> float, объём нового уровня (Base, REARM);
        step_ratio     - шаг (доля от цены) для проверки дистанции;
        rearm_if_empty - False: не делать REARM, если после компенсации
                         стек пуст.
        """
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.unwinder = unwinder

        self.compensation_planner = CompensationPlanner(
            qty_step=trading_info.qty_step,
            min_qty=trading_info.min_qty,
            fee_taker=trading_info.fee_taker,
        )

        self.rearm = Rearm(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            get_qty=get_qty,
            step_ratio=step_ratio,
        )

        self.compensation = RecoveryCompensation(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            unwinder=unwinder,
            planner=self.compensation_planner,
            rearm=self.rearm,
            rearm_if_empty=rearm_if_empty,
        )

        self.base_open = BaseOpen(
            state_store=state_store,
            app_ctx=app_ctx,
            get_qty=get_qty,
            step_ratio=step_ratio,
            ha_opener=ha_opener,
        )

    def resolve(self) -> ResolveResult:
        compensation_result = self._process_compensation()

        if compensation_result is not None:
            return compensation_result

        return self.base_open.process()

    def _process_compensation(self) -> ResolveResult | None:
        result = self.compensation.run()

        if result.outcome is CompensationOutcome.NO_PLAN:
            # Компенсации нет -> дальше проверяем HA Breakout
            return None

        if result.outcome is CompensationOutcome.NOT_FILLED:
            return ResolveResult(
                executed=False,
                status="COMPENSATION: NOT FILLED",
            )

        status = (
            "FILLED"
            if result.outcome is CompensationOutcome.FILLED
            else "PARTIALLY FILLED"
        )
        info = (
            f"COMPENSATION: {status} "
            f"| requested={result.requested_qty:g} "
            f"| executed={result.executed_qty:g} "
            f"| price={result.price:g}"
        )

        if result.rearm_status is not None:
            info += f" | {result.rearm_status}"

        return ResolveResult(executed=True, status=info)
