from common.unwind.unwinder import Unwinder
from common.rearm import Rearm
from action_resolver.pyramid_2_strategy.pyr_base_open import PyrBaseOpen
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_opener import (
    PyrHaBreakoutOpener,
)
from action_resolver.resolve_result import ResolveResult
from common.compensation.compensation_planner import CompensationPlanner
from common.compensation.recovery_compensation import (
    CompensationOutcome,
    RecoveryCompensation,
)


class PyrRecoveryMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        open_checker,
        unwinder: Unwinder,
        check_distance,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
        self.unwinder = unwinder

        # Проверка минимальной дистанции между двумя уровнями (min_close_steps),
        # общая с Profit-режимом: () -> ResolveResult | None
        # (None - дистанция достаточна или уровней не два).
        self.check_distance = check_distance

        self.compensation_planner = CompensationPlanner(
            qty_step=trading_info.qty_step,
            min_qty=trading_info.min_qty,
            fee_taker=trading_info.fee_taker,
        )

        self.rearm = Rearm(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            get_qty=open_checker.get_qty,
            step_ratio=open_checker.step_ratio,
        )

        self.compensation = RecoveryCompensation(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            unwinder=unwinder,
            planner=self.compensation_planner,
            rearm=self.rearm,
        )

        # Используем тот же HA Breakout, который уже создан в EntryChecker.
        self.ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            ha_signal=open_checker.ha_signal,
        )

        self.base_open = PyrBaseOpen(
            state_store=state_store,
            app_ctx=app_ctx,
            open_checker=open_checker,
            ha_opener=self.ha_opener,
        )

    def resolve(self) -> ResolveResult:
        compensation_result = self._process_compensation()

        if compensation_result is not None:
            return compensation_result

        return self.base_open.process()

    def _process_compensation(self) -> ResolveResult | None:
        # При двух уровнях компенсируем, только если дистанция между ними
        # достаточна (min_close_steps). Иначе компенсации нет -> дальше
        # проверяем HA Breakout. При трёх и более уровнях не проверяется.
        if self.check_distance() is not None:
            return None

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