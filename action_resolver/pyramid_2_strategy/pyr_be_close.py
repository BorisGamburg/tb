from action_processor.execution.limit_order_result import LimitOrderStatus
from action_resolver.resolve_result import ResolveResult


class PyrBeClose:
    """Полное закрытие стека по безубытку в Profit-режиме.

    Close band - полоса над безубытком стека (BE):
        0 <= buffer <= be_close_buffer_pct,
    где buffer - расстояние от цены закрытия до BE в % от цены.
    Если цена, падая сверху, вошла в полосу, закрываем весь стек.
    Ниже BE (buffer < 0) не закрываем: это Recovery, а не Profit.
    """

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        unwinder,
        be_close_buffer_pct: float,
        check_distance,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.unwinder = unwinder
        self.be_close_buffer_pct = be_close_buffer_pct

        # Проверка минимальной дистанции между двумя уровнями:
        # () -> ResolveResult | None (None - дистанция достаточна).
        self.check_distance = check_distance

    def process(self) -> ResolveResult | None:
        """None - закрывать по BE не нужно, иначе результат закрытия."""
        # Один уровень (только Base) не трогаем: ждём второй уровень
        # или новый Base.
        if len(self.state_store.data.stack.entries) < 2:
            return None

        # Проверяем, что цена в полосе закрытия
        band = self._get_band_hit()
        if band is None:
            return None

        # При двух уровнях закрываем, только если дистанция достаточна
        skip = self.check_distance()
        if skip is not None:
            return skip

        # Цена в полосе -> фиксируем причину закрытия в логе
        close_price, stack_be, buffer_pct = band
        self._log_close_reason(close_price, stack_be, buffer_pct)

        # Закрываем весь стек и возвращаем результат
        exec_result = self._execute_close(close_price)
        return self._get_close_result(exec_result)

    def _get_band_hit(self) -> tuple[float, float, float] | None:
        """(цена закрытия, BE, буфер %), если цена в полосе, иначе None."""
        data = self.state_store.data

        stack_be = self.state_store.stack_mng.calculate_break_even_price(
            data.side,
            self.trading_info.fee_taker,
        )
        if stack_be is None:
            return None

        # Цена закрытия с исполняемой стороны (Buy: Bid, Sell: Ask)
        close_price = float(
            self.app_ctx.price_service.get_market_close_price(
                symbol=data.symbol,
                side=data.side,
            )
        )

        if data.side == "Buy":
            buffer_pct = (close_price - stack_be) / close_price * 100
        else:
            buffer_pct = (stack_be - close_price) / close_price * 100

        # Цена перечитана после определения режима и могла уйти ниже BE ->
        # в убыток не закрываем.
        if buffer_pct < 0 or buffer_pct > self.be_close_buffer_pct:
            return None

        return close_price, stack_be, buffer_pct

    def _log_close_reason(
        self,
        close_price: float,
        stack_be: float,
        buffer_pct: float,
    ) -> None:
        entries = self.state_store.data.stack.entries
        total_qty = sum(level.qty for level in entries)

        self.app_ctx.logger.info(
            f"[BE CLOSE] price={close_price} | be={stack_be} "
            f"| buffer={buffer_pct:.4f}% "
            f"| max_buffer={self.be_close_buffer_pct:.4f}% "
            f"| levels={len(entries)} | qty={total_qty}"
        )

    def _execute_close(self, close_price: float):
        """Закрывает весь объём стека через Unwinder."""
        data = self.state_store.data
        entries = data.stack.entries

        return self.unwinder.run(
            levels=entries,
            side=data.side,
            symbol=data.symbol,
            qty=sum(level.qty for level in entries),
            price=close_price,
            min_pnl=0.0,
        )

    def _get_close_result(self, exec_result) -> ResolveResult:
        # Объём после нормализации меньше min_qty -> ордер не отправлялся
        if exec_result is None:
            return ResolveResult(
                executed=False,
                status="BE CLOSE: SKIPPED (QTY < MIN)",
            )

        if not exec_result.executed:
            return ResolveResult(
                executed=False,
                status="BE CLOSE: NOT FILLED",
            )

        status = (
            "FILLED"
            if exec_result.status == LimitOrderStatus.FILLED
            else "PARTIALLY FILLED"
        )

        # Стек закрыт полностью -> возвращаемся на минимальный TF входа
        self._reset_entry_tf_if_stack_empty()

        return ResolveResult(
            executed=True,
            status=(
                f"BE CLOSE: {status} "
                f"| price={exec_result.price} "
                f"| qty={exec_result.qty}"
            ),
        )

    def _reset_entry_tf_if_stack_empty(self) -> None:
        """После полного закрытия стека сбрасывает tf_index в 0."""
        data = self.state_store.data

        if data.stack.entries:
            return

        if data.tf_index == 0:
            return

        old_tf = data.entry_tf
        data.tf_index = 0
        self.state_store.save()

        self.app_ctx.logger.info(
            f"Entry TF reset after full close: "
            f"entry_tf changed from {old_tf} to {data.entry_tf}"
        )