"""Запускатель свёртывания стека по порогу L/P.

Цепочка: проверка размера стека -> план (pyr_loss_fold_planner) ->
исполнение ордера с проверкой -> учёт по факту (PyrFillApplier).

Модуль универсальный: ничего не знает про строки статуса. run() возвращает
результат исполнения и сырые данные, которые сам использовал (FoldReport).
Что из них показывать и как - решает вызывающая стратегия.
"""
from dataclasses import dataclass
from typing import Any

from action_processor.action import Action, ActionCommand
from action_processor.execution.execution_result import ExecutionResult
from action_processor.execution.limit_order_result import LimitOrderStatus
from action_resolver.pyramid_2_strategy.pyr_fill_applier import PyrFillApplier
from action_resolver.pyramid_2_strategy.pyr_loss_fold_planner import (
    Params,
    plan as make_plan,
)
from utils.utils import get_inverse_side


@dataclass(frozen=True, slots=True)
class FoldReport:
    """Сырые входы и выход проверки свёртывания на тике."""
    entries: Any        # уровни стека, по которым считался план
    stack_pct: float    # стоимость стека, % от баланса
    price: float        # исполняемая цена
    params: Params      # параметры планировщика
    plan: Any           # результат планировщика (make_plan)


class PyrFoldLauncher:

    def __init__(
        self,
        state,
        proxy_driver,
        action_service,
        trading_info,
        logger,
    ):
        self.state = state
        self.proxy_driver = proxy_driver
        self.action_service = action_service
        self.trading_info = trading_info
        self.logger = logger
        self.fill_applier = PyrFillApplier(
            state, trading_info, action_service, logger
        )

    def run(self) -> tuple[ExecutionResult | None, FoldReport | None]:
        """Возвращает (exec_result, report).

        exec_result None - запускать нечего (стек пуст, мал, плана нет).
        report None - стек пуст, расчёт не выполнялся.
        """

        # Получаем данные
        data = self.state.data
        side = data.side
        entries = self.state.stack_mng.data.entries

        # Стек пустой -> выходим
        if not entries:
            return None, None

        # Проверяем, что размер стека достаточен для свёртывания.

        # Получаем текущую цену
        # Баланс запрашиваем до цены, чтобы между расчётом плана и
        # выставлением ордера не было лишних запросов к бирже.
        stack_pct = self._stack_pct(entries)
        price = self._get_exec_price(data.symbol, side)

        # Формируем план свёртывания стека.
        params = Params(
            trigger=data.trigger_pct / 100,
            target=data.target_pct / 100,
            min_pnl=data.min_pnl,
            fee_taker=self.trading_info.fee_taker,
            qty_step=self.trading_info.qty_step,
            min_qty=self.trading_info.min_qty,
        )
        plan = make_plan(entries, price, side, params)

        report = FoldReport(
            entries=entries,
            stack_pct=stack_pct,
            price=price,
            params=params,
            plan=plan,
        )

        if stack_pct < data.min_stack_pct:
            # Стек мал для свёртывания -> выходим
            return None, report

        if not plan.triggered or not plan.pieces:
            # Ничего свертывать не нужно -> выходим
            return None, report

        # Исполняем ордер свёртывания стека и проверяем результат.
        exec_result = self._execute_and_verify(plan, entries, side, price)
        if not exec_result.executed:
            return exec_result, report

        # Проводим оптимальное списание уровней стека
        try:
            self.fill_applier.apply(side, entries, exec_result)
        except Exception as e:
            raise RuntimeError(
                f"FOLD CLOSE accounting failed after execution | "
                f"exec: price={exec_result.price} qty={exec_result.qty} "
                f"fee={exec_result.fee} status={exec_result.status} | "
                f"plan: total_qty={plan.total_qty} pnl={plan.pnl} "
                f"L={plan.L} P={plan.P} ratio={plan.ratio} "
                f"pieces={[(p.level_idx, p.role, p.qty) for p in plan.pieces]} | "
                f"error: {e!r}"
            ) from e

        return exec_result, report

    def _stack_pct(self, entries) -> float:
        """Стоимость стека (qty * цена входа) в % от баланса."""
        stack_value = sum(lv.qty * lv.price for lv in entries)
        balance = self.proxy_driver.get_balance()
        if balance <= 0:
            return float("inf")
        return stack_value / balance * 100

    def _get_exec_price(self, symbol: str, side: str) -> float:
        # Исполняемая сторона: лонг закрываем по bid, шорт по ask.
        ticker = self.proxy_driver.get_ticker(symbol)
        return ticker["bid"] if side == "Buy" else ticker["ask"]

    def _check_exec_result(self, exec_result: ExecutionResult, plan) -> None:
        if exec_result.status not in (
            LimitOrderStatus.FILLED,
            LimitOrderStatus.PARTIALLY_FILLED,
        ):
            raise ValueError(
                f"Unexpected FOLD CLOSE status: {exec_result.status}"
            )
        if exec_result.qty <= 0:
            raise ValueError(
                f"FOLD CLOSE executed with non-positive qty: {exec_result.qty}"
            )
        tolerance = self.trading_info.qty_step / 2
        if exec_result.qty > plan.total_qty + tolerance:
            raise RuntimeError(
                f"FOLD CLOSE filled more than planned | "
                f"filled={exec_result.qty} | planned={plan.total_qty}"
            )

    def _execute_and_verify(
        self, plan, entries, side: str, price: float
    ) -> ExecutionResult:
        """Собирает команду закрытия по плану, исполняет ордер и сверяет факт с планом.

        Не исполнился -> возвращается как есть (проверять нечего).
        Исполнился -> результат проверен, иначе исключение.
        """
        levels = [entries[pc.level_idx] for pc in plan.pieces]
        command = ActionCommand(
            action=Action.CLOSE,
            symbol=self.state.data.symbol,
            side=get_inverse_side(side),
            qty=plan.total_qty,
            levels=levels,
            reason="PYRAMID_FOLD_CLOSE",
            limit_price=price,
        )
        exec_result = self.action_service.execution.execute(command)
        if not exec_result.executed:
            return exec_result

        self._check_exec_result(exec_result, plan)
        return exec_result