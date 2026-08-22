SHIFT_OK = 0
SHIFT_TARGET_LEVEL_DOES_NOT_EXIST = 1
SHIFT_SOURCE_LEVEL_EMPTY = 2
SHIFT_TARGET_LEVEL_FULL = 3


def coin_shift_atomic(
    coins_on_levels,
    level_capacities,
    from_level,
):
    """
    Atomically shift one coin upward:

        from_level -> from_level + 1

    Example:
        coins_on_levels = [8, 2, 0]
        level_capacities = [8, 10, 10]
        from_level = 0

        result:
            [7, 3, 0]
    """

    to_level = from_level + 1

    # Target level must exist
    if to_level >= len(coins_on_levels):
        return (
            SHIFT_TARGET_LEVEL_DOES_NOT_EXIST,
            None,
        )

    # Source level must contain at least one coin
    if coins_on_levels[from_level] <= 0:
        return (
            SHIFT_SOURCE_LEVEL_EMPTY,
            None,
        )

    # Target level must have free capacity
    if coins_on_levels[to_level] >= level_capacities[to_level]:
        return (
            SHIFT_TARGET_LEVEL_FULL,
            None,
        )

    new_coins_on_levels = coins_on_levels.copy()

    new_coins_on_levels[from_level] -= 1
    new_coins_on_levels[to_level] += 1

    return (
        SHIFT_OK,
        new_coins_on_levels,
    )

def build_minimal_lower_distribution(
    coins_on_levels,
    level_capacities,
    coins_to_place,
):
    # Создаем список заполненный нулями такой же длины как coins_on_levels
    lower_distribution = [0] * len(coins_on_levels)
    remaining_coins = coins_to_place
    for level in range(len(coins_on_levels)):
        capacity = level_capacities[level]

        qty = min(remaining_coins, capacity)

        lower_distribution[level] = qty

        remaining_coins -= qty
        if remaining_coins <= 0:
            break

    return lower_distribution


def consume_rest(
    coins_on_levels,
    level_capacities,
    increment_level,
    new_distribution,
):
    total_coins = sum(coins_on_levels)
    higher_level_coins = sum(new_distribution[increment_level:])
    coins_to_place = total_coins - higher_level_coins
    lower_distribution = build_minimal_lower_distribution(
        coins_on_levels=coins_on_levels,
        level_capacities=level_capacities,
        coins_to_place=coins_to_place,
    )

    for level in range(increment_level):
        new_distribution[level] = lower_distribution[level]

    return new_distribution


def get_increment_level(coins_on_levels, level_capacities):
    for level in range(2, len(coins_on_levels)):
        if coins_on_levels[level] < level_capacities[level]:
            return level
    return None


def add_to_inc_level(coins_on_levels, level_capacities):
    increment_level = get_increment_level(coins_on_levels, level_capacities)
    if increment_level is None:
        return None, None
    new_distribution = coins_on_levels.copy()
    new_distribution[increment_level] += 1
    return increment_level, new_distribution


NEXT_DISTRIBUTION_OK = 0
NEXT_DISTRIBUTION_NO_MORE_STATES = 1


def coin_shift(
    coins_on_levels,
    level_capacities,
):
    levels_count = len(coins_on_levels)

    # Пробуем сделать атомарный shift начиная с нижнего уровня
    for from_level in range(levels_count - 1):
        shift_code, shifted_distribution = coin_shift_atomic(
            coins_on_levels=coins_on_levels,
            level_capacities=level_capacities,
            from_level=from_level,
        )
        if shift_code != SHIFT_OK:
            continue

        # На каком-то из уровней shift выполнился
        target_level = from_level + 1
        rebuilt_distribution = consume_rest(
            coins_on_levels=coins_on_levels,
            level_capacities=level_capacities,
            increment_level=target_level,
            new_distribution=shifted_distribution,
        )

        return (
            NEXT_DISTRIBUTION_OK,
            rebuilt_distribution,
        )

    # No more states
    return (
        NEXT_DISTRIBUTION_NO_MORE_STATES,
        None,
    )

def find_distribution(
    total_coins,
    level_capacities,
    coin_values,
    target_value,
):
    # Build minimal starting distribution
    distribution = build_minimal_lower_distribution(
        coins_on_levels=[0] * len(level_capacities),
        level_capacities=level_capacities,
        coins_to_place=total_coins,
    )
    while True:
        # Calculate total value
        total_value = 0
        for level in range(len(distribution)):
            total_value += (
                distribution[level]
                * coin_values[level]
            )
        # Solution found
        if total_value >= target_value:
            return distribution

        # Build next distribution
        result_code, next_distribution = coin_shift(
            coins_on_levels=distribution,
            level_capacities=level_capacities,
        )
        # No more states
        if result_code == NEXT_DISTRIBUTION_NO_MORE_STATES:
            return None

        distribution = next_distribution