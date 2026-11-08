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

    def run(self) -> ExecutionResult | None:
        """None - запускать нечего (размер стека мал или плана нет)."""
        data = self.state.data
        side = data.side
        entries = self.state.stack_mng.data.entries

        if not entries:
            return None

        if not self._is_stack_big_enough(entries, data.min_stack_pct):
            return None

        price = self._get_exec_price(data.symbol, side)

        params = Params(
            trigger=data.trigger_pct / 100,
            target=data.target_pct / 100,
            min_pnl=data.min_pnl,
            fee_taker=self.trading_info.fee_taker,
            qty_step=self.trading_info.qty_step,
            min_qty=self.trading_info.min_qty,
        )
        plan = make_plan(entries, price, side, params)
        if not plan.triggered or not plan.pieces:
            return None

        levels = [entries[pc.level_idx] for pc in plan.pieces]
        caps = [pc.qty for pc in plan.pieces]

        command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(side),
            qty=plan.total_qty,
            levels=levels,
            reason="PYRAMID_FOLD_CLOSE",
        )

        exec_result = self.action_service.execution.execute(command)
        if not exec_result.executed:
            return exec_result

        self._check_exec_result(exec_result, plan)

        try:
            self._account(side, levels, caps, exec_result)
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

    def _is_stack_big_enough(self, entries, min_stack_pct: float) -> bool:
        stack_value = sum(lv.qty * lv.price for lv in entries)
        balance = self.proxy_driver.get_balance()
        return stack_value >= balance * min_stack_pct / 100

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

    def _account(self, side, levels, caps, exec_result: ExecutionResult):
        step = self.trading_info.qty_step
        sign = 1.0 if side == "Buy" else -1.0

        # Реальные цена и комиссия исполнения (комиссия ордера на монету).
        fee_per_coin = exec_result.fee / exec_result.qty

        group = []
        for lv, cap in zip(levels, caps):
            base = lv.initial_qty if lv.initial_qty > 0 else lv.qty
            per_coin = (
                sign * (exec_result.price - lv.price)
                - lv.fee / base
                - fee_per_coin
            )
            # Консервативно: PnL на шаг округляем вниз.
            coef = floor(per_coin * step * PNL_SCALE)
            group.append((coef, round(cap / step)))

        q_units = round(exec_result.qty / step)
        min_pnl = ceil(self.state.data.min_pnl * PNL_SCALE)

        res = optimize_reductions(
            group, q_units, min_pnl, loss_order="most_first"
        )
        if res is None:
            raise RuntimeError(
                f"Executed qty exceeds planned levels qty | "
                f"q_units={q_units} | caps={[u for _, u in group]}"
            )
        if not res.breakeven:
            self.logger.warning(
                f"[FOLD] no break-even distribution | "
                f"pnl={res.pnl / PNL_SCALE:.8f} | min_pnl={self.state.data.min_pnl} | "
                f"price={exec_result.price} | qty={exec_result.qty}"
            )

        reductions = [round(u * step, 12) for u in res.reductions]
        self.action_service.accounting.reduce_levels(levels, reductions)

        self.logger.info(
            f"[FOLD] closed | price={exec_result.price} | "
            f"qty={exec_result.qty} | pnl={res.pnl / PNL_SCALE:.8f} | "
            f"reductions={reductions}"
        )