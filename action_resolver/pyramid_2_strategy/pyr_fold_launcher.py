"""Запускатель свёртывания стека по порогу L/P.

Цепочка: проверка размера стека -> план (pyr_loss_fold_planner) ->
исполнение ордера -> учёт по факту (pyr_writeoff_optimizer + reduce_levels).
"""
from math import ceil, floor

from action_processor.action import Action, ActionCommand
from action_processor.execution.execution_result import ExecutionResult
from action_processor.execution.limit_order_result import LimitOrderStatus
from action_resolver.pyramid_2_strategy.pyr_loss_fold_planner import (
    Params,
    plan as make_plan,
)
from action_resolver.pyramid_2_strategy.pyr_writeoff_optimizer import (
    optimize_reductions,
)
from utils.utils import get_inverse_side

# Оптимизатор работает с целыми: PnL на шаг qty_step считаем в 1e-8 USDT.
PNL_SCALE = 10 ** 8


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
        # Состояние свёртывания для строки статуса (обновляется в run()).
        self.status: str = ""

    def run(self) -> ExecutionResult | None:
        """None - запускать нечего (размер стека мал или плана нет)."""

        # Получаем данные 
        data = self.state.data
        side = data.side
        entries = self.state.stack_mng.data.entries

        # Стек пустой -> выходим
        if not entries:
            self.status = ""
            return None

        # Проверяем, что размер стека достаточен для свёртывания.

        # Получаем текущую цену 
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

        # Размер стека (в % от баланса) и строка статуса.
        stack_pct = self._stack_pct(entries)
        self.status = self._build_status(
            stack_pct, data.min_stack_pct, data.trigger_pct, plan
        )
        if stack_pct < data.min_stack_pct:
            # Стек мал для свёртывания -> выходим
            return None

        if not plan.triggered or not plan.pieces:
            # Ничего свертывать не нужно -> выходим
            return None

        # Исполняем ордер свёртывания стека.
        exec_result = self._execute_plan(plan, entries, side)
        if not exec_result.executed:
            return exec_result
        
        # Проверяем корректность результата исполнения ордера.
        self._check_exec_result(exec_result, plan)

        # Проводим оптимальное списание уровней стека 
        try:
            self._account(side, entries, exec_result)
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

        return exec_result

    def _stack_pct(self, entries) -> float:
        """Стоимость стека (qty * цена входа) в % от баланса."""
        stack_value = sum(lv.qty * lv.price for lv in entries)
        balance = self.proxy_driver.get_balance()
        if balance <= 0:
            return float("inf")
        return stack_value / balance * 100

    @staticmethod
    def _build_status(stack_pct, min_stack_pct, trigger_pct, plan) -> str:
        """Одна строка о состоянии свёртывания для статусной строки."""
        ratio = "∞" if plan.ratio == float("inf") else f"{plan.ratio * 100:.1f}%"
        if stack_pct < min_stack_pct:
            return (
                f"FOLD: 🔴 STACK {stack_pct:.1f}% < {min_stack_pct:g}% | "
                f"L/P {ratio}"
            )
        if not plan.triggered:
            return (
                f"FOLD: ⚪ L/P {ratio} ≤ {trigger_pct:g}% | "
                f"L {plan.L:.4f} P {plan.P:.4f}"
            )
        if not plan.pieces:
            return (
                f"FOLD: 🟠 L/P {ratio} > {trigger_pct:g}% | "
                f"NO PROFIT TO COVER"
            )
        return (
            f"FOLD: 🟢 L/P {ratio} > {trigger_pct:g}% | "
            f"CLOSE {plan.total_qty:g}"
        )

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

    def _account(self, side, entries, exec_result: ExecutionResult):
        # Копия: reduce_levels удаляет закрытые уровни из списка стека.
        levels = list(entries)
        step = self.trading_info.qty_step

        # Преобразуем уровни стека в целые уровни для оптимизатора
        int_levels = self._to_int_levels(side, levels, exec_result)

        # Преобразуем qty и min_pnl в целые для оптимизатора
        int_close_qty = round(exec_result.qty / step)
        int_min_pnl = ceil(self.state.data.min_pnl * PNL_SCALE)

        # Вызываем оптимизатор
        res = optimize_reductions(
            int_levels, int_close_qty, int_min_pnl, loss_order="most_first"
        )
        if res is None:
            raise RuntimeError(
                f"Executed qty exceeds stack qty | "
                f"q_units={int_close_qty} | units={[u for _, u in int_levels]}"
            )
        if not res.breakeven:
            self.logger.warning(
                f"[FOLD] no break-even distribution | "
                f"pnl={res.pnl / PNL_SCALE:.8f} | min_pnl={self.state.data.min_pnl} | "
                f"price={exec_result.price} | qty={exec_result.qty}"
            )

        # Преобразуем обратно целые списания в реальные величины
        reductions = [round(u * step, 12) for u in res.reductions]

        # Применяем списания к уровням стека 
        self.action_service.accounting.reduce_levels(levels, reductions)

        self.logger.info(
            f"[FOLD] closed | price={exec_result.price} | "
            f"qty={exec_result.qty} | pnl={res.pnl / PNL_SCALE:.8f} | "
            f"reductions={reductions}"
        )

    def _to_int_levels(
        self,
        side: str,
        levels: list,
        exec_result: ExecutionResult,
    ) -> list[tuple[int, int]]:
        """Описывает уровни стека целыми числами для оптимизатора:
        (PnL одного шага qty_step в 1e-8 USDT, число шагов на уровне).
        PnL считается по реальным цене и комиссии исполнения."""
        step = self.trading_info.qty_step
        sign = 1.0 if side == "Buy" else -1.0

        # Комиссия закрытия на монету (ордер один, одинакова для всех уровней).
        close_fee_per_coin = exec_result.fee / exec_result.qty

        int_levels = []
        for lv in levels:
            base = lv.initial_qty if lv.initial_qty > 0 else lv.qty
            open_fee_per_coin = lv.fee / base
            pnl_per_coin = (
                sign * (exec_result.price - lv.price)
                - open_fee_per_coin
                - close_fee_per_coin
            )
            # Консервативно: PnL на шаг округляем вниз.
            pnl_step_scaled = floor(pnl_per_coin * step * PNL_SCALE)
            qty_steps_count = floor(lv.qty / step + 1e-9)
            int_levels.append((pnl_step_scaled, qty_steps_count))

        return int_levels        

    def _execute_plan(self, plan, entries, side: str) -> ExecutionResult:
        """Собирает команду закрытия по плану и исполняет ордер."""
        levels = [entries[pc.level_idx] for pc in plan.pieces]
        command = ActionCommand(
            action=Action.CLOSE,
            symbol=self.state.data.symbol,
            side=get_inverse_side(side),
            qty=plan.total_qty,
            levels=levels,
            reason="PYRAMID_FOLD_CLOSE",
        )
        return self.action_service.execution.execute(command)