from dataclasses import dataclass


@dataclass
class BuildResult:
    allowed: bool
    side: str
    qty: float
    report: str


def calc_hedge_qty(
    main_qty: float,
    hedge_qty_ratio: float,
    trading_info,
) -> float:
    hedge_qty = (
        main_qty *
        hedge_qty_ratio
    )
    return trading_info.get_valid_order_qty(hedge_qty)


def _is_level_distance_allowed(
    work_price: float,
    entries,
    hedge_step_ratio: float,
) -> tuple[bool, str]:
    for entry in entries:
        dist = abs(
            work_price - entry.price
        ) / work_price

        if dist < hedge_step_ratio:
            report = (
                f"Nearest level: {entry.price:.2f}, "
                f"distance={dist:.4f} "
                f"< required={hedge_step_ratio:.4f}.\n"
                "Build: denied "
            )
            return False, report

    return True, ""


def check_build(
    trend_active: bool,
    work_price: float,
    entries,
    hedge_step_ratio: float,
    main_pos_size: float,
    hedge_pos_size: float,
    hedge_qty_ratio: float,
    hedge_side: str,
    trading_info,
) -> BuildResult:
    report = ""

    # Рассчитываем объем одного уровня защиты
    hedge_qty = calc_hedge_qty(
        main_qty=main_pos_size,
        hedge_qty_ratio=hedge_qty_ratio,
        trading_info=trading_info,
    )

    # Размер уровня защиты меньше минимально допустимого
    if hedge_qty == 0.0:
        return BuildResult(
            allowed=False,
            side=hedge_side,
            qty=hedge_qty,
            report="Hedge qty below minimum. Build: denied ",
        )

    # Без активного тренда новые уровни защиты не строим
    if not trend_active:
        report += (
            "Trend: inactive "
            "Build: denied "
        )

        return BuildResult(
            allowed=False,
            side=hedge_side,
            qty=hedge_qty,
            report=report,
        )

    # Проверяем дистанцию до существующих уровней
    distance_allowed, distance_report = _is_level_distance_allowed(
        work_price=work_price,
        entries=entries,
        hedge_step_ratio=hedge_step_ratio,
    )

    if not distance_allowed:
        return BuildResult(
            allowed=False,
            side=hedge_side,
            qty=hedge_qty,
            report=distance_report,
        )

    report += (
        "Build: allowed "
    )

    return BuildResult(
        allowed=True,
        side=hedge_side,
        qty=hedge_qty,
        report=report,
    )
