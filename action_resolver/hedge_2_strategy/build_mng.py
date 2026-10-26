from dataclasses import dataclass

from common.level_distance_checker import is_level_distance_allowed


@dataclass
class BuildResult:
    allowed: bool
    side: str
    qty: float
    report: str
    trend_active: bool
    distance_allowed: bool

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
    # Проверяем дистанцию до существующих уровней
    distance_allowed = is_level_distance_allowed(
        cur_price=work_price,
        entries=entries,
        hedge_step_ratio=hedge_step_ratio,
    )

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
            trend_active=trend_active,
            distance_allowed=distance_allowed,
        )

    # Без активного тренда новые уровни защиты не строим
    if not trend_active:
        report = (
            "Trend: inactive "
            "Build: denied "
        )

        return BuildResult(
            allowed=False,
            side=hedge_side,
            qty=hedge_qty,
            report=report,
            trend_active=trend_active,
            distance_allowed=distance_allowed,
        )

    if not distance_allowed:
        return BuildResult(
            allowed=False,
            side=hedge_side,
            qty=hedge_qty,
            report="",
            trend_active=trend_active,
            distance_allowed=distance_allowed,
        )

    return BuildResult(
        allowed=True,
        side=hedge_side,
        qty=hedge_qty,
        report="Build: allowed ",
        trend_active=trend_active,
        distance_allowed=distance_allowed,
    )
