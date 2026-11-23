def calc_required_protect_ratio(
    unrealised_pnl: float,
    entry_price: float,
    main_qty: float,
    protect_ratio_factor: float,
    max_hedge_ratio: float,
    protect_ratio_offset: float = 0.0,
) -> float:
    """
    Требуемая доля защиты: прямая y = k * x + b, ограниченная [0, max].

    x — знаковый убыток (доля от стоимости позиции на входе,
        при прибыли отрицательный),
    k — protect_ratio_factor (наклон),
    b — protect_ratio_offset (смещение, в долях основной позиции).
    """
    signed_loss_ratio = calc_signed_loss_ratio(
        unrealised_pnl=unrealised_pnl,
        entry_price=entry_price,
        main_qty=main_qty,
    )

    raw_ratio = (
        signed_loss_ratio * protect_ratio_factor
        + protect_ratio_offset
    )

    return min(
        max(0.0, raw_ratio),
        max_hedge_ratio,
    )

def calc_required_hedge_qty(
    unrealised_pnl: float,
    entry_price: float,
    main_qty: float,
    protect_ratio_factor: float,
    max_hedge_ratio: float,
    protect_ratio_offset: float = 0.0,
) -> float:
    protect_ratio = calc_required_protect_ratio(
        unrealised_pnl=unrealised_pnl,
        entry_price=entry_price,
        main_qty=main_qty,
        protect_ratio_factor=protect_ratio_factor,
        max_hedge_ratio=max_hedge_ratio,
        protect_ratio_offset=protect_ratio_offset,
    )
    return (
        protect_ratio *
        main_qty
    )

def calc_signed_loss_ratio(
    unrealised_pnl: float,
    entry_price: float,
    main_qty: float,
) -> float:
    """
    Возвращает знаковую долю убытка относительно стоимости позиции
    на момент входа: убыток > 0, прибыль < 0.
    """

    entry_value = entry_price * main_qty

    if entry_value <= 0:
        raise ValueError(
            f"Ошибка расчета защиты: "
            f"некорректная стоимость позиции "
            f"(entry_price={entry_price}, "
            f"main_qty={main_qty})"
        )

    return -unrealised_pnl / entry_value

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

    return max(
        0.0,
        calc_signed_loss_ratio(
            unrealised_pnl=unrealised_pnl,
            entry_price=entry_price,
            main_qty=main_qty,
        ),
    )
