from common.unwind.unwinder import Unwinder
from common.level_distance_checker import is_level_distance_allowed
from action_resolver.pyramid_2_strategy.pyr_close_processor import (
    PyrCloseProcessor,
)
from action_resolver.pyramid_2_strategy.pyr_rearm import PyrRearm
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_opener import (
    PyrHaBreakoutOpener,
)
from action_resolver.resolve_result import ResolveResult
from common.compensation.compensation_planner import CompensationPlanner
from action_processor.action import Action, ActionCommand
from action_processor.execution.close_limit_mng import ExitType
from action_processor.execution.limit_order_result import LimitOrderStatus
from utils.utils import get_inverse_side


class PyrRecoveryMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        open_checker,
        close_processor: PyrCloseProcessor,
        unwinder: Unwinder,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
        self.close_processor = close_processor
        self.unwinder = unwinder

        self.compensation_planner = CompensationPlanner(
            qty_step=trading_info.qty_step,
            min_qty=trading_info.min_qty,
            fee_taker=trading_info.fee_taker,
        )

        self.rearm = PyrRearm(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            open_checker=open_checker,
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
        data = self.state_store.data

        # Цена закрытия с исполняемой стороны (Buy: Bid, Sell: Ask)
        close_price = float(
            self.app_ctx.price_service.get_market_close_price(
                symbol=data.symbol,
                side=data.side,
            )
        )

        # Считаем компенсацию: что закрывать и в каком объёме
        plan = self.compensation_planner.plan(
            levels=data.stack.entries,
            side=data.side,
            price=close_price,
            min_pnl=float(data.min_pnl),
        )
        if plan is None:
            # Компенсации нет -> дальше проверяем HA Breakout
            return None

        # Уровни, участвующие в компенсационном закрытии
        levels = [
            plan.base_level,
            *(reduction.level for reduction in plan.reductions),
        ]

        # Формируем команду на закрытие одним общим ордером
        command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(data.side),
            qty=plan.total_qty,
            levels=levels,
            reason="PYRAMID_COMPENSATION",
            limit_price=close_price,
        )

        # Отправляем ордер через существующий механизм исполнения
        exec_result = self.action_service.execution.execute(
            command,
            exit_type=ExitType.ACTIVE,
        )
        if not exec_result.executed:
            return ResolveResult(
                executed=False,
                status="COMPENSATION: NOT FILLED",
            )

        status = (
            "FILLED"
            if exec_result.status == LimitOrderStatus.FILLED
            else "PARTIALLY FILLED"
        )

        return ResolveResult(
            executed=True,
            status=(
                f"COMPENSATION: {status} "
                f"| requested={plan.total_qty:g} "
                f"| executed={exec_result.qty:g} "
                f"| price={exec_result.price:g}"
            ),
        )


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
        return self.ha_opener.open(qty, "NEW BASE")

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