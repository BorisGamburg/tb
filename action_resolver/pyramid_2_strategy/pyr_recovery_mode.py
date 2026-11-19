from common.unwind.unwinder import Unwinder
from common.level_distance_checker import is_level_distance_allowed
from common.rearm import Rearm
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
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
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

    def resolve(self) -> ResolveResult:
        compensation_result = self._process_compensation()

        if compensation_result is not None:
            return compensation_result

        return self._process_ha_breakout()

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

    def _process_ha_breakout(self) -> ResolveResult:
        data = self.state_store.data

        # Проверяем HA Signal
        if not self.ha_opener.has_signal():
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: NO SIGNAL",
            )

        # Новый уровень должен стать Base (самым нижним для Buy, самым верхним для Sell)
        active_price = self.ha_opener.get_active_price()
        if not self._is_new_base_level(active_price):
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (NOT BASE)",
            )

        # Проверяем дистанцию до каждого уровня стека
        cur_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )
        distance_allowed = is_level_distance_allowed(
            cur_price=cur_price,
            entries=data.stack.entries,
            hedge_step_ratio=self.open_checker.step_ratio,
        )
        if not distance_allowed:
            # Проверка дистанции не прошла -> выходим
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (DISTANCE)",
            )

        # Дистанция ОК
        # Получаем qty
        qty = self.open_checker.get_qty()
        if qty <= 0:
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (QTY = 0)",
            )

        # Открываем уровень
        return self.ha_opener.open(qty, "NEW BASE", is_base=True)

    def _is_new_base_level(self, price: float) -> bool:
        """Станет ли уровень с ценой входа price новым Base.

        Buy: ниже цены входа любого существующего уровня.
        Sell: выше цены входа любого существующего уровня.
        """
        data = self.state_store.data
        entries = data.stack.entries

        if not entries:
            return True

        if data.side == "Buy":
            return price < min(level.price for level in entries)

        return price > max(level.price for level in entries)