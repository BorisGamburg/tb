from common.recovery.ha_breakout_opener import PyrHaBreakoutOpener
from common.recovery.tf_advance import advance_entry_tf
from action_resolver.resolve_result import ResolveResult
from common.level_distance_checker import is_level_distance_allowed


class BaseOpen:
    """Открытие нового Base в Recovery-режиме пирамиды.

    Последовательность проверок: сигнал -> новый Base -> дистанция -> qty,
    затем открытие уровня как Base.
    """

    def __init__(
        self,
        state_store,
        app_ctx,
        get_qty,
        step_ratio: float,
        ha_opener: PyrHaBreakoutOpener,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.get_qty = get_qty
        self.step_ratio = step_ratio
        self.ha_opener = ha_opener

    def process(self) -> ResolveResult:
        # Проверяем HA Signal
        skip = self._check_ha_signal()
        if skip is not None:
            return skip

        # Новый уровень должен стать Base
        skip = self._check_new_base()
        if skip is not None:
            return skip

        # Проверяем дистанцию до каждого уровня стека
        skip = self._check_distance()
        if skip is not None:
            return skip

        # Проверяем qty
        qty, skip = self._check_qty()
        if skip is not None:
            return skip

        # Открываем уровень
        result = self.ha_opener.open(qty, "NEW BASE")

        # Открыт новый Base -> переходим на следующий таймфрейм списка
        if result.executed:
            advance_entry_tf(self.state_store, self.app_ctx)

        return result

    def _check_ha_signal(self) -> ResolveResult | None:
        """None - сигнал есть, иначе готовый результат пропуска."""
        if self.ha_opener.has_signal():
            return None
        return ResolveResult(
            executed=False,
            status="HA BREAKOUT: NO SIGNAL",
        )

    def _check_new_base(self) -> ResolveResult | None:
        """None - уровень станет новым Base, иначе результат пропуска.

        Base - самый нижний уровень для Buy, самый верхний для Sell.
        """
        active_price = self.ha_opener.get_active_price()
        if self._is_new_base_level(active_price):
            return None
        return ResolveResult(
            executed=False,
            status="HA BREAKOUT: SKIPPED (NOT BASE)",
        )

    def _check_distance(self) -> ResolveResult | None:
        """None - дистанция до каждого уровня разрешена, иначе пропуск."""
        data = self.state_store.data

        cur_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )

        if is_level_distance_allowed(
            cur_price=cur_price,
            entries=data.stack.entries,
            hedge_step_ratio=self.step_ratio,
        ):
            return None

        return ResolveResult(
            executed=False,
            status="HA BREAKOUT: SKIPPED (DISTANCE)",
        )

    def _check_qty(self) -> tuple[float | None, ResolveResult | None]:
        """Возвращает qty либо результат пропуска."""
        qty = self.get_qty()

        if qty <= 0:
            return None, ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (QTY = 0)",
            )

        return qty, None

    def _is_new_base_level(self, price: float) -> bool:
        """Станет ли уровень с ценой входа price новым Base.

        Buy: ниже цены входа любого существующего уровня.
        Sell: выше цены входа любого существующего уровня.
        """
        data = self.state_store.data
        entries = data.stack.entries

        if not entries:
            return True

        if data.side == "Buy":
            return price < min(level.price for level in entries)

        return price > max(level.price for level in entries)