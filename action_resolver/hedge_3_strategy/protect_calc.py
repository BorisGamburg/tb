def calc_required_protect_ratio(
    unrealised_pnl: float,
    entry_price: float,
    main_qty: float,
    protect_ratio_factor: float,
    max_hedge_ratio: float,
) -> float:
    loss_ratio = calc_loss_ratio(
        unrealised_pnl=unrealised_pnl,
        entry_price=entry_price,
        main_qty=main_qty,
    )

    return min(
        loss_ratio * protect_ratio_factor,
        max_hedge_ratio,
    )

def calc_required_hedge_qty(
    unrealised_pnl: float,
    entry_price: float,
    main_qty: float,
    protect_ratio_factor: float,
    max_hedge_ratio: float,
) -> float:
    protect_ratio = calc_required_protect_ratio(
        unrealised_pnl=unrealised_pnl,
        entry_price=entry_price,
        main_qty=main_qty,
        protect_ratio_factor=protect_ratio_factor,
        max_hedge_ratio=max_hedge_ratio,
    )
    return (
        protect_ratio *
        main_qty
    )

def calc_loss_ratio(
    unrealised_pnl: float,
    entry_price: float,
    main_qty: float,
) -> float:
    """
    Возвращает долю текущего убытка относительно стоимости позиции
    на момент входа.

    Прибыль считается как отсутствие убытка (0.0).
    """

    entry_value = entry_price * main_qty

    if entry_value <= 0:
        raise ValueError(
            f"Ошибка расчета защиты: "
            f"некорректная стоимость позиции "
            f"(entry_price={entry_price}, "
            f"main_qty={main_qty})"
        )

    return max(
        0.0,
        -unrealised_pnl / entry_value,
    )