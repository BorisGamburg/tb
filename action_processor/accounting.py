from action_processor.state.state import State
from action_processor.state.stack_mng import StackMng
from action_processor.action import Action
from action_processor.process_result import ProcessResult

class Accounting:
    def __init__(self, state_store: State):
        self.state_store = state_store
        self.stack_mng: StackMng = state_store.stack_mng

    def apply(self, process_result: ProcessResult):
        """Применяет результат исполнения: обновляет стек и сохраняет state."""
        if process_result.qty is None or process_result.qty <= 0:
            return (
                f"[ACCOUNTING] SKIP | action={process_result.action_command} "
                f"| price={process_result.price} | qty={process_result.qty}"
            )
    
        if process_result.action_command.action == Action.OPEN:
            message = self._apply_open(process_result)
        elif process_result.action_command.action == Action.CLOSE:
            message = self._apply_close(process_result)
        elif process_result.action_command.action == Action.CLOSE_POSITION:
            message = self._apply_close_position(process_result)    
        elif process_result.action_command.action == Action.CLOSE_PARTIAL:
            message = self._apply_close_partial(process_result)                    
        else:
            raise ValueError(f"⚠️ Unrecognized action: {process_result.action_command}")

        self.state_store.save()
        return message
    
    def _apply_close(self, process_result: ProcessResult):
        levels = process_result.action_command.levels or []
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

    def _apply_open(self, process_result: ProcessResult):
        assert process_result.price is not None
        assert process_result.qty is not None

        fee = process_result.fee or 0.0

        self.stack_mng.push(
            process_result.price,
            process_result.qty,
            fee,
        )

        return (
            f"[ACCOUNTING] OPEN | qty={process_result.qty} "
            f"| price={process_result.price} "
            f"| stack={len(self.stack_mng.data.entries)}"
        )
    
    def _apply_close_position(self, process_result: ProcessResult):
        self.stack_mng.clear()
    
        return (
            f"[ACCOUNTING] CLOSE_POSITION | "
            f"qty={process_result.qty} "
            f"| price={process_result.price}"
        )

    def _apply_close_partial(self, process_result: ProcessResult):
        # Получаем уровень, который мы закрываем частично
        levels = process_result.action_command.levels or []
        if len(levels) != 1:
            raise ValueError(
                f"CLOSE_PARTIAL expects exactly one level | "
                f"levels={levels}"
            )
        level = levels[0]

        # Проверяем, что количество для закрытия частично корректно
        if process_result.qty is None or process_result.qty <= 0:
            raise ValueError(
                f"CLOSE_PARTIAL requires positive qty | "
                f"qty={process_result.qty}"
            )
        if process_result.qty >= level.qty:
            raise ValueError(
                f"CLOSE_PARTIAL qty must be less than level qty | "
                f"level_qty={level.qty} | "
                f"close_qty={process_result.qty}"
            )

        # Уменьшаем количество на уровне
        level.qty -= process_result.qty

        # Возвращаем сообщение о закрытии частичного ордера
        return (
            f"[ACCOUNTING] CLOSE_PARTIAL | "
            f"price={level.price} | "
            f"closed_qty={process_result.qty} | "
            f"remaining_qty={level.qty}"
        )