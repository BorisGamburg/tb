"""Учёт исполненного ордера свёртывания: распределение закрытого объёма
по уровням стека (writeoff_optimizer) и применение списаний к стеку."""
from math import ceil, floor

from action_processor.execution.execution_result import ExecutionResult
from common.unwind.writeoff_optimizer import (
    optimize_reductions,
)

# Оптимизатор работает с целыми: PnL на шаг qty_step считаем в 1e-8 USDT.
PNL_SCALE = 10 ** 8

# Порядок списания убыточных уровней: от самых убыточных.
LOSS_ORDER = "most_first"


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
        profit_order: str = "most_first",
    ) -> None:
        # Копия: reduce_levels удаляет закрытые уровни из списка стека.
        levels = list(entries)
        step = self.trading_info.qty_step

        # Преобразуем уровни стека в целые уровни для оптимизатора
        int_levels = self._to_int_levels(
            side,
            levels,
            exec_result.price,
            exec_result.fee / exec_result.qty,
        )

        # Преобразуем qty и min_pnl в целые для оптимизатора
        int_close_qty = round(exec_result.qty / step)
        int_min_pnl = ceil(min_pnl * PNL_SCALE)

        # Вызываем оптимизатор
        res = optimize_reductions(
            int_levels,
            int_close_qty,
            int_min_pnl,
            profit_order=profit_order,
            loss_order=LOSS_ORDER,
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

        # Списания в логе: цена уровня и объём, только ненулевые. Индексы
        # в reductions относятся к порядку списка стека, а в отчёте стек
        # печатается по цене, поэтому индексы там не совпадают.
        reductions_log = ", ".join(
            f"{lv.price}:{r}" for lv, r in zip(levels, reductions) if r > 0
        )

        self.logger.info(
            f"[FOLD] closed | price={exec_result.price} | "
            f"qty={exec_result.qty} | pnl={res.pnl / PNL_SCALE:.8f} | "
            f"reductions=[{reductions_log}]"
        )

    def estimate(
        self,
        side: str,
        entries,
        price: float,
        qty: float,
        min_pnl: float,
        profit_order: str = "most_first",
    ):
        """Оценка списания без исполнения ордера: те же формулы, тот же
        оптимизатор, что и в apply. Комиссия закрытия - fee_taker от цены.

        Возвращает Result оптимизатора (res.breakeven - укладывается ли
        объём в min_pnl) или None, если qty больше объёма стека."""
        step = self.trading_info.qty_step
        int_levels = self._to_int_levels(
            side,
            list(entries),
            price,
            price * self.trading_info.fee_taker,
        )
        return optimize_reductions(
            int_levels,
            round(qty / step),
            ceil(min_pnl * PNL_SCALE),
            profit_order=profit_order,
            loss_order=LOSS_ORDER,
        )

    def _to_int_levels(
        self,
        side: str,
        levels: list,
        price: float,
        close_fee_per_coin: float,
    ) -> list[tuple[int, int]]:
        """Описывает уровни стека целыми числами для оптимизатора:
        (PnL одного шага qty_step в 1e-8 USDT, число шагов на уровне).

        price и close_fee_per_coin: при списании - реальные цена и комиссия
        исполнения, при оценке - плановая цена и ожидаемая комиссия.
        Комиссия закрытия на монету одинакова для всех уровней (ордер один).
        """
        step = self.trading_info.qty_step
        sign = 1.0 if side == "Buy" else -1.0

        int_levels = []
        for lv in levels:
            base = lv.initial_qty if lv.initial_qty > 0 else lv.qty
            open_fee_per_coin = lv.fee / base
            pnl_per_coin = (
                sign * (price - lv.price)
                - open_fee_per_coin
                - close_fee_per_coin
            )
            # Консервативно: PnL на шаг округляем вниз.
            pnl_step_scaled = floor(pnl_per_coin * step * PNL_SCALE)
            qty_steps_count = floor(lv.qty / step + 1e-9)
            int_levels.append((pnl_step_scaled, qty_steps_count))

        return int_levels