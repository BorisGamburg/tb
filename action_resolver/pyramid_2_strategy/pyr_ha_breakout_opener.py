from action_processor.action import Action, ActionCommand
from action_resolver.resolve_result import ResolveResult


class PyrHaBreakoutOpener:
    """HA Breakout: проверка сигнала, цена входа и открытие уровня."""

    def __init__(
        self,
        state_store,
        app_ctx,
        action_service,
        ha_signal,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.action_service = action_service
        self.ha_signal = ha_signal

    def has_signal(self) -> bool:
        data = self.state_store.data

        signal_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )
        signal_result = self.ha_signal.is_entry(
            tf=data.entry_tf,
            side=data.side,
            price=signal_price,
        )
        return signal_result.ok

    def get_active_price(self) -> float:
        data = self.state_store.data

        # Цена той же стороны спреда, по которой открывается лимитный ордер.
        active_price = self.app_ctx.price_service.get_active_price(
            symbol=data.symbol,
            side=data.side,
        )
        if active_price <= 0:
            raise ValueError(
                f"Invalid active price for HA Breakout: {active_price}"
            )
        return active_price

    def open(
        self,
        qty: float,
        info: str,
        is_base: bool = False,
    ) -> ResolveResult:
        data = self.state_store.data

        # Формируем команду
        open_command = ActionCommand(
            action=Action.OPEN,
            symbol=data.symbol,
            side=data.side,
            qty=qty,
            reason="PYRAMID_HA_BREAKOUT",
        )

        # Посылаем команду на исполнение и учет.
        # Ошибки открытия не перехватываем: исключение выходит наружу.
        open_result = self.action_service.process_action(open_command)
        if not open_result.executed:
            # Команда не выполнена
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: NOT FILLED",
            )

        # Открыт Base -> переходим на следующий таймфрейм списка
        if is_base:
            self._advance_entry_tf()

        # Команда выполнена
        return ResolveResult(
            executed=True,
            status=f"HA BREAKOUT: OPENED | {info}",
        )

    def _advance_entry_tf(self) -> None:
        data = self.state_store.data

        # Последний таймфрейм в списке -> остаёмся на нём
        if data.tf_index >= len(data.timeframes) - 1:
            return

        current_tf = data.entry_tf

        # Переходим на следующий таймфрейм списка
        data.tf_index += 1
        self.state_store.save()

        self.app_ctx.logger.info(
            f"Base level opened: entry_tf changed "
            f"from {current_tf} to {data.entry_tf}"
        )