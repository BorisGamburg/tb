from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass
class CompensationConsume:
    level: object
    qty: float
    realized_pnl: float


@dataclass
class CompensationResult:
    losing_level: object
    losing_close_qty: float
    total_realized_pnl: float
    consumes: list[CompensationConsume]
    fully_compensated: bool
    required_compensation: float | None = None
    realized_loss: float | None = None


def _calc_costs(
    current_price: float,
    close_qty: float,
    fee_rate: float,
    slippage_rate: float,
) -> float:

    notional = (
        current_price
        * close_qty
    )

    fee_cost = (
        notional
        * fee_rate
    )

    slippage_cost = (
        notional
        * slippage_rate
    )

    return fee_cost + slippage_cost

def _collect_profitable_levels(
    hedge_side: str,
    stack,
    current_price: float,
    losing_level,
):
    """
    Collect profitable levels ordered from nearest profitable
    to deepest profitable.
    """

    reverse = hedge_side == "Buy"

    ordered = sorted(
        stack,
        key=lambda x: x.price,
        reverse=reverse,
    )

    profitable = []

    for level in ordered:

        if level == losing_level:
            continue

        profit_pnl = _calc_level_profit_pnl(
            hedge_side=hedge_side,
            level=level,
            current_price=current_price,
        )

        if profit_pnl <= 0:
            continue

        profitable.append(level)

    return profitable  

def _calc_level_profit_pnl(
    hedge_side: str,
    level,
    current_price: float,
) -> float:

    if hedge_side == "Buy":
        return max(
            0.0,
            (current_price - level.price) * level.qty,
        )

    return max(
        0.0,
        (level.price - current_price) * level.qty,
    )

def _calc_required_qty(
    required_compensation: float,
    accumulated_profit: float,
    profit_per_unit: float,
) -> float | None:    
    """
    Solve equation:

        R = p*x + A

    where:

        R = required compensation
        p = profit per unit
        x = required qty
        A = accumulated profit

    Solution:

        x = (R - A) / p
    """

    if profit_per_unit <= 0:
        return None

    remaining_required_profit = (
        required_compensation
        - accumulated_profit
    )

    if remaining_required_profit <= 0:
        return None

    return (
        remaining_required_profit
        / profit_per_unit
    )

@dataclass
class QtySolveResult:
    required_qty: float
    consume_qty: float
    fully_solved: bool


def _solve_required_qty(
    required_compensation: float,
    accumulated_profit: float,
    profit_per_unit: float,
    available_qty: float,
) -> QtySolveResult | None:

    required_qty = _calc_required_qty(
        required_compensation=required_compensation,
        accumulated_profit=accumulated_profit,
        profit_per_unit=profit_per_unit,
    )

    if required_qty is None:
        return None

    if available_qty >= required_qty:

        consume_qty = required_qty
        fully_solved = True

    else:

        consume_qty = available_qty
        fully_solved = False

    return QtySolveResult(
        required_qty=required_qty,
        consume_qty=consume_qty,
        fully_solved=fully_solved,
    )

def _calc_profit_per_unit(
    hedge_side: str,
    entry_price: float,
    current_price: float,
) -> float:

    if hedge_side == "Buy":
        return current_price - entry_price

    return entry_price - current_price

@dataclass
class CompensationConsumesResult:
    consumes: list[CompensationConsume]
    accumulated_profit: float
    fully_compensated: bool


def _find_compensation_consumes(
    hedge_side: str,
    profitable_levels,
    current_price: float,
    required_compensation: float,
) -> CompensationConsumesResult:
    """
    Walk through profitable levels starting from nearest
    to current price and determine compensation consumes.
    """

    accumulated_profit = 0.0

    consumes: list[CompensationConsume] = []

    for level in profitable_levels:
        profit_per_unit = _calc_profit_per_unit(
            hedge_side=hedge_side,
            entry_price=level.price,
            current_price=current_price,
        )

        if profit_per_unit <= 0:
            continue

        solve_result = _solve_required_qty(
            required_compensation=required_compensation,
            accumulated_profit=accumulated_profit,
            profit_per_unit=profit_per_unit,
            available_qty=level.qty,
        )

        if solve_result is None:
            break

        realized_profit = (
            solve_result.consume_qty
            * profit_per_unit
        )

        accumulated_profit += realized_profit

        consumes.append(
            CompensationConsume(
                level=level,
                qty=solve_result.consume_qty,
                realized_pnl=realized_profit,
            )
        )

        if solve_result.fully_solved:
            break

    fully_compensated = (
        accumulated_profit >= required_compensation
    )

    return CompensationConsumesResult(
        consumes=consumes,
        accumulated_profit=accumulated_profit,
        fully_compensated=fully_compensated,
    )

def calc_loss_compensation(
    hedge_side: str,
    stack,
    losing_level,
    current_price: float,
    fee_rate: float,
    slippage_rate: float,
    min_profit: float,
    qty_step: float,
) -> CompensationResult | None:

    loss_per_unit = _calc_loss_per_unit(
        hedge_side=hedge_side,
        entry_price=losing_level.price,
        current_price=current_price,
    )

    if loss_per_unit <= 0:
        return None

    profitable_levels = _collect_profitable_levels(
        hedge_side=hedge_side,
        stack=stack,
        current_price=current_price,
        losing_level=losing_level,
    )

    if not profitable_levels:
        return None

    # ---------------------------------------------------------
    # Try full losing level compensation
    # ---------------------------------------------------------
    realized_loss = (
        loss_per_unit
        * losing_level.qty
    )

    estimated_costs = _calc_costs(
        current_price=current_price,
        close_qty=losing_level.qty,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )    

    required_compensation = (
        realized_loss
        + estimated_costs
        + min_profit
    )

    consume_result = _find_compensation_consumes(
        hedge_side=hedge_side,
        profitable_levels=profitable_levels,
        current_price=current_price,
        required_compensation=required_compensation,
    )

    # ---------------------------------------------------------
    # Full compensation possible
    # ---------------------------------------------------------
    if consume_result.fully_compensated:
        return CompensationResult(
            losing_level=losing_level,
            losing_close_qty=losing_level.qty,
            total_realized_pnl=(
                consume_result.accumulated_profit
                - required_compensation
            ),
            consumes=consume_result.consumes,
            fully_compensated=True
        )

    # ---------------------------------------------------------
    # Partial compensation
    # ---------------------------------------------------------

    partial_result = _calc_partial_losing_qty(
        accumulated_profit=consume_result.accumulated_profit,
        loss_per_unit=loss_per_unit,
        losing_level_qty=losing_level.qty,
        current_price=current_price,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        min_profit=min_profit,
        qty_step=qty_step,
    )

    if partial_result is None:
        return None

    partial_losing_qty, total_realized_pnl = partial_result

    return CompensationResult(
        losing_level=losing_level,
        losing_close_qty=partial_losing_qty,
        total_realized_pnl=total_realized_pnl,
        consumes=consume_result.consumes,
        fully_compensated=False,
        required_compensation=required_compensation,
        realized_loss=(
            partial_losing_qty
            * loss_per_unit
        )
    )


def _calc_partial_losing_qty(
    accumulated_profit: float,
    loss_per_unit: float,
    losing_level_qty: float,
    current_price: float,
    fee_rate: float,
    slippage_rate: float,
    min_profit: float,
    qty_step: float,
) -> tuple[float, float] | None:
    """
    Calculate how much qty from losing level can be closed
    using currently accumulated profit.

    Returns
    -------
    tuple:
        (
            partial_losing_qty,
            total_realized_pnl,
        )
    """

    total_costs = _calc_costs(
        current_price=current_price,
        close_qty=losing_level_qty,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )

    available_loss_cover_pnl = (
        accumulated_profit
        - total_costs
        - min_profit
    )

    if available_loss_cover_pnl <= 0:
        return None

    partial_losing_qty = (
        available_loss_cover_pnl
        / loss_per_unit
    )

    partial_losing_qty = min(
        partial_losing_qty,
        losing_level_qty,
    )

    partial_losing_qty = _floor_to_step(
        partial_losing_qty,
        qty_step,
    )

    if partial_losing_qty <= 0:
        return None

    total_realized_pnl = (
        available_loss_cover_pnl
        - (
            partial_losing_qty
            * loss_per_unit
        )
    )

    return (
        partial_losing_qty,
        total_realized_pnl,
    )

def _calc_loss_per_unit(
    hedge_side: str,
    entry_price: float,
    current_price: float,
) -> float:

    if hedge_side == "Buy":
        return entry_price - current_price

    return current_price - entry_price

def _floor_to_step(
    value: float,
    step: float,
) -> float:

    return (
        math.floor(value / step)
        * step
    )    