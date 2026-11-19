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
        data = self.state_store.data
        extensions = self._get_extension_levels()

        if not extensions:
            return None

        # При двух уровнях проверяем минимальную дистанцию для закрытия.
        if len(data.stack.entries) == 2:
            distance_steps = self._get_distance_steps()

            if distance_steps <= self.min_close_steps:
                return ResolveResult(
                    executed=False,
                    status=(
                        f"PROFIT CLOSE: WAITING FOR DISTANCE "
                        f"| {distance_steps:.2f} <= {self.min_close_steps}"
                    ),
                )        

        # Получаем Ask/Bid
        ticker = self.app_ctx.proxy_driver.get_ticker(data.symbol)
        bid = float(ticker["bid"])
        ask = float(ticker["ask"])

        # Ищем уровень для закрытия
        close_level = self._find_close_level(extensions, bid, ask)
        if close_level is None:
            return None

        # Уровень для закрытия найден, формируем команду на закрытие.
        close_command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(data.side),
            qty=close_level.qty,
            levels=[close_level],
            reason="PYRAMID_PROFIT_CLOSE",
        )

        # Отправляем команду на закрытие через CloseProcessor.
        close_result = self.close_processor.execute_profit_close(
            close_command
        )

        exec_result = close_result.execution_result

        # Проверяем результат исполнения команды.
        if not exec_result.executed:
            return ResolveResult(
                executed=False,
                status="PROFIT CLOSE: NOT FILLED",
            )

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