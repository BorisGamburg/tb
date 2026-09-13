from action_processor.state.state import State
from action_processor.state.stack_mng import StackMng
from action_processor.action import Action

class Accounting:
    def __init__(self, state_store: State, logger):
        self.state_store = state_store
        self.stack_mng: StackMng = state_store.stack_mng
        self.logger = logger

    def apply(
        self,
        action: Action,
        price: float,
        qty: float,
        fee: float,
        levels: list | None = None,
    ):
        """Применяет результат исполнения: обновляет стек и сохраняет state."""
        if action == Action.OPEN:
            self._apply_open(
                price=price,
                qty=qty,
                fee=fee,
            )
        elif action == Action.CLOSE:
            self._apply_close(
                levels=levels or [],
            )
        elif action == Action.CLOSE_POSITION:
            self._apply_close_position(
                qty=qty,
                price=price,
            )
        elif action == Action.CLOSE_PARTIAL:
            self._apply_close_partial(
                levels=levels or [],
                qty=qty,
            )
        else:
            raise ValueError(f"⚠️ Unrecognized action: {action}")

        self.state_store.save()
    
    def _apply_close(self, levels):
        levels_str = ", ".join(
            f"[{lvl.price:.8f}, {lvl.qty}]"
            for lvl in levels
        )

        for level in levels:
            self.stack_mng.remove_entry(level)

        self.logger.info(
            f"[ACCOUNTING] CLOSE | "
            f"levels={levels_str}"
        )  

    def _apply_open(self, price: float, qty: float, fee: float):
        self.stack_mng.push(price, qty, fee)

        self.logger.info(
            f"[ACCOUNTING] OPEN | qty={qty} "
            f"| price={price} "
            f"| stack={len(self.stack_mng.data.entries)}"
        )
    
    def _apply_close_position(self, qty: float, price: float):
        self.stack_mng.clear()

        self.logger.info(
            f"[ACCOUNTING] CLOSE_POSITION | "
            f"qty={qty} "
            f"| price={price}"
        )

    def _apply_close_partial(self, levels, qty: float):
        # Получаем уровень, который мы закрываем частично
        if len(levels) != 1:
            raise ValueError(
                f"CLOSE_PARTIAL expects exactly one level | "
                f"levels={levels}"
            )
        level = levels[0]

        # Проверяем, что количество для закрытия частично корректно
        if qty <= 0:
            raise ValueError(
                f"CLOSE_PARTIAL requires positive qty | "
                f"qty={qty}"
            )
        if qty >= level.qty:
            raise ValueError(
                f"CLOSE_PARTIAL qty must be less than level qty | "
                f"level_qty={level.qty} | "
                f"close_qty={qty}"
            )

        # Уменьшаем количество на уровне
        level.qty -= qty

        self.logger.info(
            f"[ACCOUNTING] CLOSE_PARTIAL | "
            f"price={level.price} | "
            f"closed_qty={qty} | "
            f"remaining_qty={level.qty}"
        )

    def update_level_qty(self, level, qty: float):
        if qty <= 0:
            raise ValueError(
                f"Level qty must be positive | qty={qty}"
            )

        level.qty = qty

        self.logger.info(
            f"[ACCOUNTING] UPDATE_LEVEL_QTY | "
            f"price={level.price} | "
            f"qty={qty}"
        )

        self.state_store.save()

    def remove_level(self, level):
        self.stack_mng.remove_entry(level)

        self.logger.info(
            f"[ACCOUNTING] REMOVE_LEVEL | "
            f"price={level.price} | "
            f"qty={level.qty}"
        )

        self.state_store.save()        