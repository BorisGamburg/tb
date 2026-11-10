"""Учёт исполненного ордера свёртывания: распределение закрытого объёма
по уровням стека (writeoff_optimizer) и применение списаний к стеку."""
from math import ceil, floor

from action_processor.execution.execution_result import ExecutionResult
from common.unwind.writeoff_optimizer import (
    optimize_reductions,
)

# Оптимизатор работает с целыми: PnL на шаг qty_step считаем в 1e-8 USDT.
PNL_SCALE = 10 ** 8


class FillApplier:

    def __init__(self, trading_info, action_service, logger):
        self.trading_info = trading_info
        self.action_service = action_service
        self.logger = logger

    def apply(
        self,
        side: str,
        entries,
        exec_result: ExecutionResult,
        min_pnl: float,
    ) -> None:
        # Копия: reduce_levels удаляет закрытые уровни из списка стека.
        levels = list(entries)
        step = self.trading_info.qty_step

        # Преобразуем уровни стека в целые уровни для оптимизатора
        int_levels = self._to_int_levels(side, levels, exec_result)

        # Преобразуем qty и min_pnl в целые для оптимизатора
        int_close_qty = round(exec_result.qty / step)
        int_min_pnl = ceil(min_pnl * PNL_SCALE)

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
                f"pnl={res.pnl / PNL_SCALE:.8f} | min_pnl={min_pnl} | "
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