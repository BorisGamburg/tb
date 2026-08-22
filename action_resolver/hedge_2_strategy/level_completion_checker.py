from enum import Enum

from pydantic import BaseModel

from prog.action_processor.state.stack_mng import StackMng
from prog.action_processor.state.stack_schema import StackElem


class CompletionStatus(Enum):
    NOT_FOUND = "not_found"
    ALREADY_FULL = "already_full"
    LEVEL_SPACING_FAILED = "level_spacing_failed"
    OK = "ok"


class LevelCompletionResult(BaseModel):
    status: CompletionStatus
    level: StackElem | None = None
    add_qty: float = 0.0


def check_level_completion(
    stack_mng: StackMng,
    side: str,
    last_price: float,
    full_level_qty: float,
    min_order_qty: float,
    step_ratio: float,
) -> LevelCompletionResult:

    # Работаем только с клоном стека.
    stack_copy = stack_mng.clone()

    # Сортировка необходима для корректной работы
    # _find_nearest_profitable_level().
    stack_copy.sort_stack(side)

    # Находим ближайший прибыльный уровень.
    nearest_profit_level = _find_nearest_profitable_level(
        stack_mng=stack_copy,
        side=side,
        last_price=last_price,
    )

    # Если ближайший прибыльный уровень не найден, возвращаем результат с NOT_FOUND.
    if nearest_profit_level is None:
        return LevelCompletionResult(
            status=CompletionStatus.NOT_FOUND,
        )

    # Проверяем, меньше ли дополнение минимального размера ордера.
    if full_level_qty - nearest_profit_level.qty < 1.5 * min_order_qty:
        return LevelCompletionResult(
            status=CompletionStatus.ALREADY_FULL,
            level=nearest_profit_level,
        )    

    # Вычисляем количество, которое нужно добавить до полного уровня.
    add_qty = full_level_qty - nearest_profit_level.qty

    # Добавляем в клон виртуальный уровень, моделирующий будущую сделку.
    virtual_level = stack_copy.push(
        price=last_price,
        qty=add_qty,
    )

    # Выполняем виртуальное объединение прибыльного уровня
    # с виртуальным уровнем.
    merged_level = stack_copy.merge_levels(
        level1=nearest_profit_level,
        level2=virtual_level,
    )

    # merge_levels() меняет структуру стека.
    # Для поиска соседей необходимо восстановить сортировку.
    stack_copy.sort_stack(side)
    
    # Находим соседние уровни для объединенного уровня.
    previous_level, next_level = _find_neighbors(
        stack_mng=stack_copy,
        level=merged_level,
    )

    # Проверяем минимальное расстояние
    # до соседних уровней.
    level_spacing_ok = _check_level_spacing(
        base_level=merged_level,
        previous_level=previous_level,
        next_level=next_level,
        step_ratio=step_ratio,
    )

    if not level_spacing_ok:
        return LevelCompletionResult(
            status=CompletionStatus.LEVEL_SPACING_FAILED,
            level=nearest_profit_level,
            add_qty=add_qty,
        )    

    return LevelCompletionResult(
        status=CompletionStatus.OK,
        level=nearest_profit_level,
        add_qty=add_qty,
    )

def _find_nearest_profitable_level(
    stack_mng: StackMng,
    side: str,
    last_price: float,
) -> StackElem | None:
    """
    Находит ближайший прибыльный уровень.

    Предполагается, что стек уже отсортирован:

    - для Buy — по убыванию цены;
    - для Sell — по возрастанию цены.

    Поэтому первый найденный прибыльный уровень является ближайшим
    к текущей цене.

    Настоящий стек эта функция не сортирует.
    """

    if side == "Buy":
        for level in stack_mng.data.entries:
            if level.price < last_price:
                return level

    elif side == "Sell":
        for level in stack_mng.data.entries:
            if level.price > last_price:
                return level

    else:
        raise ValueError(f"Unknown side: {side}")

    return None

def _find_neighbors(
    stack_mng: StackMng,
    level: StackElem,
) -> tuple[StackElem | None, StackElem | None]:
    """
    Находит соседние уровни для указанного уровня.

    Предполагается, что стек уже отсортирован.

    Возвращает кортеж:

        (previous_level, next_level)

    Если одного из соседей нет, вместо него возвращается None.
    """

    entries = stack_mng.data.entries

    index = entries.index(level)

    previous_level = None
    if index > 0:
        previous_level = entries[index - 1]

    next_level = None
    if index < len(entries) - 1:
        next_level = entries[index + 1]

    return previous_level, next_level

def _check_level_spacing(
    base_level: StackElem,
    previous_level: StackElem | None,
    next_level: StackElem | None,
    step_ratio: float,
) -> bool:
    """
    Проверяет, что расстояние от базового уровня
    до соседних уровней не меньше минимального шага лестницы.

    Минимальный допустимый шаг вычисляется относительно
    цены базового уровня.
    """

    min_distance = base_level.price * step_ratio

    if previous_level is not None:
        distance = abs(previous_level.price - base_level.price)

        if distance < min_distance:
            return False

    if next_level is not None:
        distance = abs(next_level.price - base_level.price)

        if distance < min_distance:
            return False

    return True

