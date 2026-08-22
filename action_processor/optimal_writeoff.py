from math import floor
from prog.action_processor.coin_distributor import find_distribution


def apply_optimal_writeoff(
    entries,
    side,
    fill_price: float,
    profit_qty: float,
    required_compensation: float,
    qty_quantum: float,
    logger,
) -> bool:    
    if not entries:
        return False        

    # Преобразуем данные из трейдинга в данные для coin distributor
    profitable_levels, coin_values, level_capacities, total_coins = convert_trading_data_to_coin_inputs(
        entries=entries,
        fill_price=fill_price,
        profit_qty=profit_qty,
        side=side,
        qty_quantum=qty_quantum,
    )

    # Find distribution
    logger.info(
        f"COIN DISTRIBUTOR INPUT | "
        f"total_coins={total_coins} "
        f"coin_values={coin_values} "
        f"level_capacities={level_capacities} "
        f"target_value={required_compensation}"
    )    
    distribution = find_distribution(
        total_coins=total_coins,
        level_capacities=level_capacities,
        coin_values=coin_values,
        target_value=required_compensation,
    )
    if distribution is None:
        logger.warning(
            "UNWIND DISTRIBUTION FAILED | "
            "solver returned None"
        )
        return False

    apply_distribution(
        distribution=distribution,
        profitable_levels=profitable_levels,
        entries=entries,
        qty_quantum=qty_quantum,
        logger=logger
    )

    log_distribution(distribution, logger)

    return True

def convert_trading_data_to_coin_inputs(
    entries,
    fill_price: float,
    profit_qty: float,
    side: str,
    qty_quantum: float
):
    profitable_levels = []
    coin_values = []
    level_capacities = []
    total_coins = int(round(profit_qty / qty_quantum))   

    sorted_entries = sort_nearest_to_farthest(
        entries,
        side,
    )

    for level in sorted_entries:
        pnl_per_1_qty = (
            fill_price - level.price
            if side == "Buy"
            else level.price - fill_price
        )

        # Only profitable levels
        if pnl_per_1_qty <= 0:
            continue

        pnl_per_1_coin = (
            pnl_per_1_qty * qty_quantum
        )

        profitable_levels.append(level)

        coin_values.append(pnl_per_1_coin)

        coin_capacity = int(
            round(level.qty / qty_quantum)
        )
        level_capacities.append(
            coin_capacity
        )

    return (
        profitable_levels,
        coin_values,
        level_capacities,
        total_coins
    )

def apply_distribution(
    distribution,
    profitable_levels,
    entries,
    qty_quantum: float,
    logger
):
    for idx in range(len(distribution)):
        quant_count = distribution[idx]

        if quant_count <= 0:
            continue

        consume_qty = quant_count * qty_quantum
        consume_qty = normalize_qty(consume_qty, qty_quantum)


        level = profitable_levels[idx]

        epsilon = 1e-12
        if consume_qty - level.qty > epsilon:
            raise RuntimeError(
                f"Distribution overconsume | "
                f"price={level.price} "
                f"consume={consume_qty} "
                f"level_qty={level.qty}"
            )

        level.qty -= consume_qty
        level.qty = normalize_qty(level.qty, qty_quantum)

        logger.info(
            f"UNWIND DISTRIBUTION APPLY | "
            f"price={level.price:.8f} "
            f"consume_qty={consume_qty:.1f} "
            f"remaining_qty={level.qty}"
        )

    cleanup_zero_levels(
        entries=entries,
        logger=logger,
    )       

def log_distribution(distribution, logger) -> None:
    distribution_str = ", ".join(
        str(x) for x in distribution
    )
    logger.info(
        f"UNWIND DISTRIBUTION RESOLVED | "
        f"distribution=[{distribution_str}]"
    )

def cleanup_zero_levels(
    entries,
    logger,
):
    epsilon = 1e-12

    before = len(entries)

    entries[:] = [
        x for x in entries
        if x.qty > epsilon
    ]

    removed = before - len(entries)

    if removed > 0:
        logger.info(
            f"STACK CLEANUP | removed_zero_levels={removed}"
        )

def sort_nearest_to_farthest(
    entries,
    side,
):
    if side == "Buy":
        # Для Buy:
        # ближайшие profitable уровни имеют максимальную цену
        # (ближе к fill_price сверху вниз)
        return sorted(
            entries,
            key=lambda x: x.price,
            reverse=True,
        )

    # Для Sell:
    # ближайшие profitable уровни имеют минимальную цену
    return sorted(
        entries,
        key=lambda x: x.price,
    )

def normalize_qty(qty, quantum):
    steps = round(qty / quantum)
    return steps * quantum    