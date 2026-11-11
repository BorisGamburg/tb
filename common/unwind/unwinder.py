"""Unwinder: закрытие заданного объёма по уровням стека.

Модуль не принимает решений «пора ли свёртывать»: условия и объём определяет
вызывающая стратегия. Unwinder получает «закрой qty монет» и делает три шага:
  1. нормализует объём (кратно qty_step, не больше объёма стека, не меньше
     min_qty);
  2. исполняет лимитный ордер закрытия по переданной цене и сверяет факт
     исполнения с запросом;
  3. списывает уровни стека по факту исполнения (FillApplier).

От state и строк статуса модуль не зависит.
"""
from math import floor

from action_processor.action import Action, ActionCommand
from action_processor.execution.execution_result import ExecutionResult
from action_processor.execution.limit_order_result import LimitOrderStatus
from common.unwind.fill_applier import FillApplier
from utils.utils import get_inverse_side

EPS = 1e-9

# Причина ордера в логах и учёте.
REASON = "UNWIND_CLOSE"


class Unwinder:

    def __init__(self, action_service, trading_info, logger):
        self.action_service = action_service
        self.trading_info = trading_info
        self.logger = logger
        self.fill_applier = FillApplier(
            trading_info, action_service, logger
        )

    def run(
        self,
        levels,
        side: str,
        symbol: str,
        qty: float,
        price: float,
        min_pnl: float = 0.0,
        profit_order: str = "most_first",
    ) -> ExecutionResult | None:
        """Закрывает qty монет по уровням стека.

        levels  - уровни стека (тот же список, что видит учёт: закрытые
                  уровни удаляются из него);
        side    - сторона свёртываемых уровней ("Buy" / "Sell");
        price   - лимитная цена закрытия;
        min_pnl - желаемый итог ордера: оптимизатор списания старается
                  уложиться не ниже, иначе минимизирует убыток;
        profit_order - порядок списания прибыльных уровней: "most_first"
                  (от самых прибыльных, по умолчанию) или "least_first"
                  (от наименее прибыльных).

        Возвращает результат исполнения. None - ордер не отправлялся
        (объём после нормализации меньше min_qty).
        """

        # Нормализуем объём
        qty = self._normalize_qty(levels, qty)
        if qty is None:
            return None

        # Исполняем ордер и проверяем результат.
        exec_result = self._execute_and_verify(
            levels, side, symbol, qty, price
        )
        if not exec_result.executed:
            return exec_result

        # Проводим оптимальное списание уровней стека по факту
        try:
            self.fill_applier.apply(
                side, levels, exec_result, min_pnl, profit_order
            )
        except Exception as e:
            raise RuntimeError(
                f"UNWIND accounting failed after execution | "
                f"exec: price={exec_result.price} qty={exec_result.qty} "
                f"fee={exec_result.fee} status={exec_result.status} | "
                f"request: side={side} qty={qty} price={price} "
                f"min_pnl={min_pnl} | profit_order={profit_order} | "
                f"error: {e!r}"
            ) from e

        return exec_result

    def check_breakeven(
        self,
        levels,
        side: str,
        qty: float,
        price: float,
        min_pnl: float = 0.0,
        profit_order: str = "most_first",
    ):
        """Укладывается ли закрытие qty монет по price в min_pnl.

        Ордер не отправляется. Объём нормализуется так же, как в run, а
        PnL считается теми же формулами и тем же оптимизатором, что и при
        списании (FillApplier.estimate), поэтому оценка и факт согласованы
        с точностью до разницы комиссии и цены исполнения.

        Возвращает Result оптимизатора (res.breakeven, res.pnl в 1e-8 USDT)
        или None, если объём после нормализации меньше min_qty.
        """
        qty = self._normalize_qty(levels, qty)
        if qty is None:
            return None
        return self.fill_applier.estimate(
            side, levels, price, qty, min_pnl, profit_order
        )

    def _normalize_qty(self, levels, qty: float) -> float | None:
        """Объём кратно qty_step, не больше объёма стека. None - меньше min_qty."""
        step = self.trading_info.qty_step
        q = min(qty, sum(lv.qty for lv in levels))
        q = round(floor(q / step + EPS) * step, 12)
        if q < self.trading_info.min_qty - EPS:
            return None
        return q

    def _check_exec_result(
        self, exec_result: ExecutionResult, qty: float
    ) -> None:
        if exec_result.status not in (
            LimitOrderStatus.FILLED,
            LimitOrderStatus.PARTIALLY_FILLED,
        ):
            raise ValueError(
                f"Unexpected UNWIND status: {exec_result.status}"
            )
        if exec_result.qty <= 0:
            raise ValueError(
                f"UNWIND executed with non-positive qty: {exec_result.qty}"
            )
        tolerance = self.trading_info.qty_step / 2
        if exec_result.qty > qty + tolerance:
            raise RuntimeError(
                f"UNWIND filled more than requested | "
                f"filled={exec_result.qty} | requested={qty}"
            )

    def _execute_and_verify(
        self, levels, side: str, symbol: str, qty: float, price: float
    ) -> ExecutionResult:
        """Исполняет ордер закрытия и сверяет факт с запросом.

        Не исполнился -> возвращается как есть (проверять нечего).
        Исполнился -> результат проверен, иначе исключение.
        """
        command = ActionCommand(
            action=Action.CLOSE,
            symbol=symbol,
            side=get_inverse_side(side),
            qty=qty,
            levels=list(levels),
            reason=REASON,
            limit_price=price,
        )
        exec_result = self.action_service.execution.execute(command)
        if not exec_result.executed:
            return exec_result

        self._check_exec_result(exec_result, qty)
        return exec_result