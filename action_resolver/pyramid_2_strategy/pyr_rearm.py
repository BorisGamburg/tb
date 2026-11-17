from action_processor.action import Action, ActionCommand
from common.level_distance_checker import is_level_distance_allowed


class PyrRearm:
    """REARM: открытие нового уровня после закрытия уровня пирамиды."""

    def __init__(
        self,
        state_store,
        app_ctx,
        action_service,
        open_checker,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.action_service = action_service
        self.open_checker = open_checker

    def try_rearm(self) -> str:
        # Инит
        data = self.state_store.data
        entries = data.stack.entries

        # Получаем текущую цену
        cur_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )

        # Проверяем дистанцию
        distance_allowed = is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=self.open_checker.step_ratio,
        )
        if not distance_allowed:
            # Дистанция меньше шага -> rearm не выполняем
            self.app_ctx.logger.info(
                "[REARM] skipped: distance to stack < step"
            )
            return "REARM: SKIPPED DISTANCE"

        # Дистанция ОК -> получаем количество для rearm
        qty = self.open_checker.get_qty()
        if qty <= 0:
            self.app_ctx.logger.info(
                "[REARM] skipped: qty = 0"
            )
            return "REARM: SKIPPED QTY"

        # Формируем команду на rearm
        rearm_command = ActionCommand(
            action=Action.OPEN,
            symbol=data.symbol,
            side=data.side,
            qty=qty,
            reason="REARM",
        )

        # Отправляем команду на rearm через ActionService.
        # Повторяем, пока ордер не исполнится.
        while True:
            rearm_result = self.action_service.process_action(
                rearm_command
            )
            if rearm_result.executed:
                break

        return "REARM: EXECUTED"
