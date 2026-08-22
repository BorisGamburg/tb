import logging
from typing import List, Optional
from prog.action_processor.state.stack_schema import StackData, StackElem

class StackMng:
    """Управляет операциями стека ордеров, используя данные из StateStore."""
    def __init__(self, stack_data: StackData, logger: logging.Logger):
        self.data = stack_data # Ссылка на StateDataSchema.order_stack (StackData)
        self.logger = logger
    
    def size(self) -> int:
        """Возвращает текущий размер стека."""
        return len(self.data.entries)
        
    def push(
        self,
        price: float,
        qty: float,
        fee: float = 0.0,
    ) -> StackElem:
        entry = StackElem(
            price=price,
            qty=qty,
            fee=fee,
        )

        self.data.entries.append(entry)

        self.logger.debug(
            f"Стек: Добавлен ордер по {price} (Qty: {qty}). Новый размер: {self.size()}"
        )

        return entry

    def pop(self) -> Optional[StackElem]:
        if self.data.entries:
            entry = self.data.entries.pop()
            self.logger.debug(
                f"Стек: Удален ордер по {entry.price}. Новый размер: {self.size()}"
            )
            return entry

        self.logger.warning("Стек пуст, pop невозможен.")
        return None    

    def peek(self) -> StackElem | None:
        if self.is_empty():
            return None
        return self.data.entries[-1]    

    def is_empty(self):
        """Проверка, пуст ли стек."""
        return len(self.data.entries) == 0

    def peek_second_last(self) -> StackElem | None:
        if len(self.data.entries) < 2:
            self.logger.debug(
                "Попытка просмотреть предпоследний элемент в стеке с менее чем двумя элементами."
            )
            return None
        return self.data.entries[-2]    

    def to_string(self) -> str:
        return str(self.data.entries)
    
    def remove_entry(self, entry):
        self.data.entries.remove(entry)
        return 
    
    def sort_stack(self, side: str):
        reverse = side == "Buy"
        self.data.entries.sort(key=lambda x: x.price, reverse=reverse)       

    def merge_levels(
        self,
        level1: StackElem,
        level2: StackElem,
    ):
        # Проверки
        self._validate_merge_levels(
            level1,
            level2,
        )

        # Вычисление объединенного количества   
        total_qty = level1.qty + level2.qty

        # Проверка, что объединенное количество положительное
        if total_qty <= 0:
            raise ValueError("Merged level has zero quantity")

        # Вычисление средней цены для объединенного уровня                     
        merged_price = (
            level1.price * level1.qty +
            level2.price * level2.qty
        ) / total_qty

        merged_fee = getattr(level1, 'fee', 0.0) + getattr(level2, 'fee', 0.0)

        # Создание merge-уровня
        merged = StackElem(
            price=merged_price,
            qty=total_qty,
            fee=merged_fee,
        )
        self.data.entries.append(merged)

        # Удаление исходных уровней из стека
        self.data.entries.remove(level1)
        self.data.entries.remove(level2)

        # Лог
        self.logger.info(
            f"Merged levels: "
            f"({level1.price:.6f}, {level1.qty:.4f}) + "
            f"({level2.price:.6f}, {level2.qty:.4f}) -> "
            f"({merged.price:.6f}, {merged.qty:.4f})"
        )        

        return merged      

    def _validate_merge_levels(
        self,
        level1: StackElem,
        level2: StackElem,
    ):
        # Проверка, что оба уровня присутствуют в стеке
        if level1 not in self.data.entries:
            raise ValueError("level1 is not in stack")

        if level2 not in self.data.entries:
            raise ValueError("level2 is not in stack")

        # Проверка, что уровни не совпадают
        if level1 is level2:
            raise ValueError("Cannot merge the same level")

        # Проверка, что уровни имеют положительные количества
        if level1.qty <= 0:
            raise ValueError(
                f"Invalid level1 qty: {level1.qty}"
            )

        if level2.qty <= 0:
            raise ValueError(
                f"Invalid level2 qty: {level2.qty}"
            )      

    def clone(self):
        data_copy = self.data.model_copy(deep=True)

        return StackMng(
            stack_data=data_copy,
            logger=self.logger,
        )
    
