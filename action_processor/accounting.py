from action_processor.state.state import State
from action_processor.state.stack_mng import StackMng
from action_processor.execution.execution_result import ExecutionResult
from action_processor.action import Action

class Accounting:
    def __init__(self, state_store: State):
        self.state_store = state_store
        self.stack_mng: StackMng = state_store.stack_mng

    def apply(self, result: ExecutionResult):
        """Применяет результат исполнения: обновляет стек и сохраняет state."""
        if result.qty is None or result.qty <= 0:
            return (
                f"[ACCOUNTING] SKIP | action={result.action_command} "
                f"| price={result.price} | qty={result.qty}"
            )
    
        if result.action_command.action == Action.OPEN:
            message = self._apply_open(result)
        elif result.action_command.action == Action.CLOSE:
            message = self._apply_close(result)
        elif result.action_command.action == Action.CLOSE_POSITION:
            message = self._apply_close_position(result)    
        elif result.action_command.action == Action.CLOSE_PARTIAL:
            message = self._apply_close_partial(result)                    
        else:
            raise ValueError(f"⚠️ Unrecognized action: {result.action_command}")

        self.state_store.save()
        return message
    
    def _apply_close(self, result: ExecutionResult):
        levels = result.action_command.levels or []
        levels_str = ", ".join(
            f"[{lvl.price:.8f}, {lvl.qty}]"
            for lvl in levels
        )

        for level in levels:
            self.stack_mng.remove_entry(level)

        return (
            f"[ACCOUNTING] CLOSE | "
            f"levels={levels_str}"
        )          

    def _apply_open(self, result: ExecutionResult):
        assert result.price is not None
        assert result.qty is not None

        fee = result.fee or 0.0

        self.stack_mng.push(
            result.price,
            result.qty,
            fee,
        )

        return (
            f"[ACCOUNTING] OPEN | qty={result.qty} "
            f"| price={result.price} "
            f"| stack={len(self.stack_mng.data.entries)}"
        )
    
    def _apply_close_position(self, result: ExecutionResult):
        self.stack_mng.clear()
    
        return (
            f"[ACCOUNTING] CLOSE_POSITION | "
            f"qty={result.qty} "
            f"| price={result.price}"
        )

    def _apply_close_partial(self, result: ExecutionResult):
        # Получаем уровень, который мы закрываем частично
        levels = result.action_command.levels or []
        if len(levels) != 1:
            raise ValueError(
                f"CLOSE_PARTIAL expects exactly one level | "
                f"levels={levels}"
            )
        level = levels[0]

        # Проверяем, что количество для закрытия частично корректно
        if result.qty is None or result.qty <= 0:
            raise ValueError(
                f"CLOSE_PARTIAL requires positive qty | "
                f"qty={result.qty}"
            )
        if result.qty >= level.qty:
            raise ValueError(
                f"CLOSE_PARTIAL qty must be less than level qty | "
                f"level_qty={level.qty} | "
                f"close_qty={result.qty}"
            )

        # Уменьшаем количество на уровне
        level.qty -= result.qty

        # Возвращаем сообщение о закрытии частичного ордера
        return (
            f"[ACCOUNTING] CLOSE_PARTIAL | "
            f"price={level.price} | "
            f"closed_qty={result.qty} | "
            f"remaining_qty={level.qty}"
        )