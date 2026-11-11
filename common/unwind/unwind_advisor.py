"""Советчик сворачивания: решает, нужно ли свёртывать стек и
сколько закрыть. Ничего не исполняет.

Условия (размер стека, порог L/P) и планировщик (unwind_planner)
живут здесь, а не в Unwinder: Unwinder только исполняет. Модуль общий
для стратегий, настройки каждая передаёт через UnwindConfig. Результат -
UnwindReport: сырые данные расчёта плюс объём к закрытию (qty_to_close).
Что из отчёта показывать в строке статуса, решает стратегия.
"""
from dataclasses import dataclass
from typing import Any

from common.unwind.unwind_planner import (
    Params,
    plan as make_plan,
)


@dataclass(frozen=True, slots=True)
class UnwindConfig:
    """Настройки сворачивания на данный вызов."""
    symbol: str
    side: str               # сторона свёртываемых уровней ("Buy" / "Sell")
    trigger_pct: float      # порог L/P, %
    target_pct: float       # целевое L/P после свёртывания, %
    min_pnl: float          # минимальный PnL свёртывания, USDT
    min_stack_pct: float    # минимальный размер стека, % от баланса


@dataclass(frozen=True, slots=True)
class UnwindReport:
    """Сырые входы и выход проверки свёртывания на тике."""
    entries: Any            # уровни стека, по которым считался план
    stack_pct: float        # стоимость стека, % от баланса
    price: float            # исполняемая цена
    params: Params          # параметры планировщика
    plan: Any               # результат планировщика (make_plan)
    qty_to_close: float     # сколько закрыть; 0 - свёртывать не нужно


class UnwindAdvisor:

    def __init__(self, proxy_driver, trading_info):
        self.proxy_driver = proxy_driver
        self.trading_info = trading_info

    def check(self, config: UnwindConfig, entries) -> UnwindReport | None:
        """None - стек пуст, расчёт не выполнялся."""
        side = config.side

        # Стек пустой -> выходим
        if not entries:
            return None

        # Баланс запрашиваем до цены, чтобы между расчётом плана и
        # выставлением ордера не было лишних запросов к бирже.
        stack_pct = self._stack_pct(entries)
        price = self._get_exec_price(config.symbol, side)

        # Формируем план свёртывания стека.
        params = Params(
            trigger=config.trigger_pct / 100,
            target=config.target_pct / 100,
            min_pnl=config.min_pnl,
            fee_taker=self.trading_info.fee_taker,
            qty_step=self.trading_info.qty_step,
            min_qty=self.trading_info.min_qty,
        )
        plan = make_plan(entries, price, side, params)

        # Условия свёртывания: стек достаточен, порог L/P сработал, план есть.
        qty_to_close = 0.0
        if (
            stack_pct >= config.min_stack_pct
            and plan.triggered
            and plan.pieces
        ):
            qty_to_close = plan.total_qty

        return UnwindReport(
            entries=entries,
            stack_pct=stack_pct,
            price=price,
            params=params,
            plan=plan,
            qty_to_close=qty_to_close,
        )

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