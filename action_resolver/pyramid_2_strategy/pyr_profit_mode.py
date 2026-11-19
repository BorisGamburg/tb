from action_resolver.resolve_result import ResolveResult
from action_resolver.pyramid_2_strategy.pyr_close_processor import (
    PyrCloseProcessor,
)
from common.rearm import Rearm
from action_resolver.pyramid_2_strategy.pyr_extension_close import (
    PyrExtensionClose,
)
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_opener import (
    PyrHaBreakoutOpener,
)
from common.level_distance_checker import is_level_distance_allowed


class PyrProfitMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        open_checker,
        close_processor: PyrCloseProcessor,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
        self.close_processor = close_processor

        self.rearm = Rearm(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            get_qty=open_checker.get_qty,
            step_ratio=open_checker.step_ratio,
        )

        self.extension_close = PyrExtensionClose(
            state_store=state_store,
            app_ctx=app_ctx,
            close_processor=close_processor,
            rearm=self.rearm,
            step_ratio=open_checker.step_ratio,
        )

        # Используем тот же HA Breakout, который уже создан в EntryChecker.
        self.ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            ha_signal=open_checker.ha_signal,
        )

    def resolve(self) -> ResolveResult:
        close_result = self.extension_close.process()

        if close_result is not None:
            return close_result

        return self._process_ha_breakout()

    def _check_ha_signal(self) -> ResolveResult | None:
        """None - сигнал есть, иначе готовый результат пропуска."""
        if self.ha_opener.has_signal():
            return None
        return ResolveResult(
            executed=False,
            status="HA BREAKOUT: NO SIGNAL",
        )

    def _process_ha_breakout(self) -> ResolveResult:
        # Проверяем HA Signal
        skip = self._check_ha_signal()
        if skip is not None:
            return skip

        # Проверяем qty
        qty, skip = self._check_qty()
        if skip is not None:
            return skip

        # Проверяем дистанцию
        skip = self._check_distance()
        if skip is not None:
            return skip
        
        # Проверяем буфер
        buffer_info, skip = self._check_buffer(qty)
        if skip is not None:
            return skip
        
        # Открываем уровень
        return self.ha_opener.open(qty, buffer_info)

    def _check_buffer(
        self,
        qty: float,
    ) -> tuple[str | None, ResolveResult | None]:
        """Возвращает информацию о буфере либо результат пропуска."""
        buffer_ok, buffer_info = self._check_buffer_after_open(qty)

        if not buffer_ok:
            return None, ResolveResult(
                executed=False,
                status=f"HA BREAKOUT: SKIPPED | {buffer_info}",
            )

        return buffer_info, None
    

    def _check_distance(self) -> ResolveResult | None:
        """None — дистанция разрешена, иначе результат пропуска."""
        data = self.state_store.data

        cur_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )

        if is_level_distance_allowed(
            cur_price=cur_price,
            entries=data.stack.entries,
            hedge_step_ratio=self.open_checker.step_ratio,
        ):
            return None

        return ResolveResult(
            executed=False,
            status="HA BREAKOUT: SKIPPED (DISTANCE)",
        )

    def _check_buffer_after_open(self, qty: float) -> tuple[bool, str]:
        """Хватит ли буфера до BE, если открыть новый уровень сейчас.

        Возвращает (достаточно ли, описание для статуса).
        """
        data = self.state_store.data

        # Текущая цена активной стороны спреда
        active_price = self.ha_opener.get_active_price()

        # Какой будет буфер, если открыть уровень сейчас
        buffer_after_open_pct = self._calc_buffer_after_open(active_price, qty)

        # Минимальный буфер из конфига
        min_buffer_pct = float(data.min_be_buffer_pct)

        if buffer_after_open_pct < min_buffer_pct:
            return False, (
                f"BUFFER {buffer_after_open_pct:.4f}% "
                f"< {min_buffer_pct:.4f}%"
            )

        return True, (
            f"BUFFER {buffer_after_open_pct:.4f}% "
            f">= {min_buffer_pct:.4f}%"
        )    

    def _calc_buffer_after_open(self, active_price: float, qty: float) -> float:
        """Буфер (в %) между ценой и новым BE стека после модельного открытия."""
        data = self.state_store.data
        fee_taker = self.trading_info.fee_taker

        # Моделируем новый уровень, не меняя реальный стек.
        # Создаем стек для моделирования
        simulated_stack = self.state_store.stack_mng.clone()

        # Добавляем в simulated_stack новый уровень
        simulated_stack.push(
            price=active_price,
            qty=qty,
            initial_qty=qty,
            fee=active_price * qty * fee_taker,
        )

        # Рассчитываем безубыток simulated_stack
        simulated_stack_be = simulated_stack.calculate_break_even_price(
            side=data.side,
            fee_taker=fee_taker,
        )
        if simulated_stack_be is None:
            # Не смогли рассчитать безубыток -> исключение
            raise RuntimeError(
                "Cannot calculate BE after simulated HA Breakout entry"
            )

        # Безубыток рассчитан
        # Рассчитываем буфер simulated_stack
        if data.side == "Buy":
            buffer_pct = (active_price - simulated_stack_be) / active_price * 100
        else:
            buffer_pct = (simulated_stack_be - active_price) / active_price * 100

        # Буфер рассчитан -> выходим
        return buffer_pct

    def _check_qty(self) -> tuple[float | None, ResolveResult | None]:
        """Возвращает qty либо результат пропуска."""
        qty = self.open_checker.get_qty()

        if qty <= 0:
            return None, ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (QTY = 0)",
            )

        return qty, None