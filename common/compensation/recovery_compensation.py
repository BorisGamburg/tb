"""RecoveryCompensation: компенсационное закрытие и восстановление Base.

Модуль делает одну операцию целиком:
  1. берёт цену закрытия с исполняемой стороны спреда;
  2. просит CompensationPlanner спланировать закрытие Base и убыточных
     уровней;
  3. отправляет один общий лимитный ордер по плану;
  4. списывает стек по факту исполнения (по реальным qty, цене, комиссии);
  5. если Base закрыт полностью, выполняет REARM.

Модуль не знает про режимы стратегии, HA-сигнал и строки статуса:
результат возвращается в виде RecoveryCompensationResult, а текст отчёта
собирает вызывающий. Реарм и планировщик передаются снаружи.
"""
from dataclasses import dataclass
from enum import Enum

from action_processor.action import Action, ActionCommand
from action_processor.execution.close_limit_mng import ExitType
from action_processor.execution.limit_order_result import LimitOrderStatus
from utils.utils import get_inverse_side


class CompensationOutcome(Enum):
    NO_PLAN = "NO_PLAN"  # компенсировать нечего
    NOT_FILLED = "NOT_FILLED"  # план был, ордер не исполнился
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"


@dataclass(frozen=True)
class RecoveryCompensationResult:
    outcome: CompensationOutcome
    requested_qty: float = 0.0
    executed_qty: float = 0.0
    price: float = 0.0
    # Статус реарма (строка от rearm.try_rearm()); None, если реарм
    # не выполнялся (Base не закрыт).
    rearm_status: str | None = None


class RecoveryCompensation:

    def __init__(
        self,
        state_store,
        app_ctx,
        action_service,
        unwinder,
        planner,
        rearm,
        rearm_if_empty: bool = True,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.action_service = action_service
        self.unwinder = unwinder
        self.planner = planner
        self.rearm = rearm
        # False: если после компенсации стек пуст, REARM не делаем
        self.rearm_if_empty = rearm_if_empty

    def run(self) -> RecoveryCompensationResult:
        close_price = self._get_close_price()

        plan = self._plan(close_price)
        if plan is None:
            return RecoveryCompensationResult(CompensationOutcome.NO_PLAN)

        # Фиксируем причину закрытия в логе (как [BE CLOSE], [PROFIT CLOSE])
        self._log_close_reason(plan, close_price)

        exec_result = self._execute(plan, close_price)
        if not exec_result.executed:
            return RecoveryCompensationResult(
                CompensationOutcome.NOT_FILLED,
                requested_qty=plan.total_qty,
            )

        self._apply_fill(plan, exec_result)

        rearm_status = None
        if self._is_base_closed(plan):
            if self.state_store.data.stack.entries or self.rearm_if_empty:
                rearm_status = self.rearm.try_rearm()
            else:
                rearm_status = "REARM: SKIPPED (STACK EMPTY)"

        outcome = (
            CompensationOutcome.FILLED
            if exec_result.status == LimitOrderStatus.FILLED
            else CompensationOutcome.PARTIALLY_FILLED
        )
        return RecoveryCompensationResult(
            outcome,
            requested_qty=plan.total_qty,
            executed_qty=exec_result.qty,
            price=exec_result.price,
            rearm_status=rearm_status,
        )

    def _get_close_price(self) -> float:
        """Цена закрытия с исполняемой стороны (Buy: Bid, Sell: Ask)."""
        data = self.state_store.data
        return float(
            self.app_ctx.price_service.get_market_close_price(
                symbol=data.symbol,
                side=data.side,
            )
        )

    def _plan(self, close_price: float):
        data = self.state_store.data
        return self.planner.plan(
            levels=data.stack.entries,
            side=data.side,
            price=close_price,
            min_pnl=float(data.min_pnl),
        )

    def _log_close_reason(self, plan, close_price: float) -> None:
        """Кто породил ордер, откуда сигнал и какой: RECOVERY_MODE
        (цена не выше BE стека) -> PyrRecoveryMode -> RecoveryCompensation,
        сигнал - план компенсации: прибыль Base покрывает убыточные уровни.
        min_close_steps здесь не проверяется (только в PyrBeClose).
        """
        data = self.state_store.data

        stack_be = self.state_store.stack_mng.calculate_break_even_price(
            data.side,
            float(self.planner.fee_taker),
        )
        if stack_be is None:
            be_text = "be=N/A"
        else:
            if data.side == "Buy":
                buffer_pct = (close_price - stack_be) / close_price * 100
            else:
                buffer_pct = (stack_be - close_price) / close_price * 100
            be_text = f"be={stack_be} | buffer={buffer_pct:+.4f}%"

        reductions = ", ".join(
            f"{item.level.price}:{item.qty:g}"
            for item in plan.reductions
        )

        self.app_ctx.logger.info(
            f"[COMPENSATION] source=RECOVERY_MODE "
            f"| signal=BASE_PROFIT_COVERS_LOSS "
            f"| reason=PYRAMID_COMPENSATION "
            f"| price={close_price} | {be_text} "
            f"| base={plan.base_level.price}:{plan.base_qty:g} "
            f"| reductions=[{reductions}] "
            f"| total_qty={plan.total_qty:g} "
            f"| expected_pnl={plan.expected_pnl:.8f} "
            f"| budget={plan.budget:.8f} "
            f"| budget_used={plan.budget_used:.8f} "
            f"| levels={len(data.stack.entries)}"
        )

    def _get_plan_levels(self, plan) -> list:
        """Уровни, участвующие в компенсации: Base и убыточные."""
        return [
            plan.base_level,
            *(reduction.level for reduction in plan.reductions),
        ]

    def _execute(self, plan, close_price: float):
        data = self.state_store.data

        command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(data.side),
            qty=plan.total_qty,
            levels=self._get_plan_levels(plan),
            reason="PYRAMID_COMPENSATION",
            limit_price=close_price,
        )

        return self.action_service.execution.execute(
            command,
            exit_type=ExitType.ACTIVE,
        )

    def _apply_fill(self, plan, exec_result) -> None:
        """Исполненный объём раскидывается по уровням на безубыток
        по реальным qty, цене и комиссии. Это не план, а учёт факта.
        Передаём только Base и убыточные уровни (прибыльные не участвуют).
        """
        data = self.state_store.data
        self.unwinder.fill_applier.apply(
            side=data.side,
            entries=self._get_plan_levels(plan),
            exec_result=exec_result,
            min_pnl=float(data.min_pnl),
        )

    def _is_base_closed(self, plan) -> bool:
        """Base исчез из стека. При частичном исполнении он остаётся."""
        return not any(
            level is plan.base_level
            for level in self.state_store.data.stack.entries
        )