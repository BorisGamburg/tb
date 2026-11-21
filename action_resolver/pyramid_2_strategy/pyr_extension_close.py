from action_processor.action import Action, ActionCommand
from action_resolver.resolve_result import ResolveResult
from utils.utils import get_inverse_side


class PyrExtensionClose:
    """Закрытие Extension по шагу прибыли и REARM после полного закрытия."""

    def __init__(
        self,
        state_store,
        app_ctx,
        close_processor,
        rearm,
        step_ratio: float,
        min_close_steps: int
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.close_processor = close_processor
        self.rearm = rearm
        self.step_ratio = step_ratio
        self.min_close_steps = min_close_steps

    def process(self) -> ResolveResult | None:
        """None - закрывать нечего, иначе результат закрытия."""
        # Инит
        data = self.state_store.data

        # Проверяем наличие extension уровней
        extensions = self._get_extension_levels()
        if not extensions:
            return None

        # Проверяем минимальную дистанцию для закрытия для 2 уровней
        skip = self._check_distance_for_two_levels()
        if skip is not None:
            return skip

        # Ищем уровень для закрытия
        close_level = self._get_close_level(extensions)
        if close_level is None:
            return None

        # Уровень для закрытия найден
        
        # Фиксируем причину закрытия в логе
        self.log_close_reason(data, close_level)        

        # Формируем команду на закрытие.
        close_command = self.get_close_command(data, close_level)

        # Отправляем команду на закрытие через CloseProcessor.
        close_result = self.close_processor.execute_profit_close(
            close_command
        )

        # Проверяем результат исполнения команды.
        skip = self._check_close_result(close_result)
        if skip is not None:
            return skip

        # Проверяем закрылся уровень полностью или частично.
        if not close_result.fully_closed:
            # Частичное закрытие уровня -> rearm не выполняем
            return ResolveResult(
                executed=True,
                status=(
                    f"PROFIT CLOSE: PARTIAL "
                    f"| price={close_level.price}"
                ),
            )

        # Полное закрытие уровня -> пробуем выполнить rearm.
        rearm_status = self.rearm.try_rearm()

        # Возвращаем результат закрытия уровня с информацией о rearm.
        return ResolveResult(
            executed=True,
            status=(
                f"PROFIT CLOSE: FULL "
                f"| price={close_level.price} "
                f"| {rearm_status}"
            ),
        )

    def get_close_command(self, data, close_level):
        close_command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(data.side),
            qty=close_level.qty,
            levels=[close_level],
            reason="PYRAMID_PROFIT_CLOSE",
        )
        return close_command

    def log_close_reason(self, data, close_level):
        if data.side == "Buy":
            target_price = close_level.price * (1 + self.step_ratio)
        else:
            target_price = close_level.price * (1 - self.step_ratio)

        self.app_ctx.logger.info(
            f"[PROFIT CLOSE] level={close_level.price} | qty={close_level.qty} "
            f"| target={target_price} | step_ratio={self.step_ratio}"
        )

    def _check_close_result(self, close_result) -> ResolveResult | None:
        """None - команда на закрытие исполнена, иначе результат пропуска."""
        if close_result.execution_result.executed:
            return None

        return ResolveResult(
            executed=False,
            status="PROFIT CLOSE: NOT FILLED",
        )

    def _check_distance_for_two_levels(self) -> ResolveResult | None:
        """None - дистанция достаточна, иначе результат пропуска.

        Проверяется только при двух уровнях в стеке.
        """
        if len(self.state_store.data.stack.entries) != 2:
            return None

        distance_steps = self._get_distance_steps()
        if distance_steps > self.min_close_steps:
            return None

        return ResolveResult(
            executed=False,
            status=(
                f"PROFIT CLOSE: WAITING FOR DISTANCE "
                f"| {distance_steps:.2f} <= {self.min_close_steps}"
            ),
        )

    def _get_extension_levels(self):
        """Все уровни, кроме Base (Buy: самый нижний, Sell: самый верхний)."""
        data = self.state_store.data
        entries = data.stack.entries

        if not entries:
            return []

        if data.side == "Buy":
            base_level = min(entries, key=lambda level: level.price)
        else:
            base_level = max(entries, key=lambda level: level.price)

        return [
            level
            for level in entries
            if level is not base_level
        ]

    def get_target_price(self) -> float | None:
        """Ближайшая к цене цель закрытия Extension (для статуса).

        Buy: bid должен подняться до цели (берём наименьшую).
        Sell: ask должен опуститься до цели (берём наибольшую).
        """
        data = self.state_store.data
        extensions = self._get_extension_levels()

        if not extensions:
            return None

        if data.side == "Buy":
            return min(
                level.price * (1 + self.step_ratio) for level in extensions
            )

        return max(
            level.price * (1 - self.step_ratio) for level in extensions
        )

    def _get_close_level(self, extensions):
        """Уровень Extension для закрытия по текущему Ask/Bid.

        None - цель закрытия ни у одного уровня не достигнута.
        """
        data = self.state_store.data

        # Получаем Ask/Bid
        ticker = self.app_ctx.proxy_driver.get_ticker(data.symbol)
        bid = float(ticker["bid"])
        ask = float(ticker["ask"])

        return self._find_close_level(extensions, bid, ask)

    def _find_close_level(self, extensions, bid, ask):
        data = self.state_store.data

        for level in extensions:
            if data.side == "Buy":
                close_price_reached = (
                    bid >= level.price * (1 + self.step_ratio)
                )
            else:
                close_price_reached = (
                    ask <= level.price * (1 - self.step_ratio)
                )

            if close_price_reached:
                return level

        return None

    def _get_distance_steps(self) -> float:
        data = self.state_store.data
        entries = data.stack.entries

        if data.side == "Buy":
            base_level = min(entries, key=lambda level: level.price)
        else:
            base_level = max(entries, key=lambda level: level.price)

        other_level = next(
            level for level in entries
            if level is not base_level
        )

        distance_pct = (
            abs(other_level.price - base_level.price)
            / base_level.price
        )

        return distance_pct / self.step_ratio