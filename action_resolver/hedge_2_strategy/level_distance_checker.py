def is_level_distance_allowed(
    cur_price: float,
    entries,
    hedge_step_ratio: float,
) -> bool:
    for entry in entries:
        dist = abs(
            cur_price - entry.price
        ) / cur_price

        if dist < hedge_step_ratio:
            return False

    return True