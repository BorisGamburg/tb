from action_processor.action import (
    Action,
    ActionCommand,
)
from action_resolver.hedge_2_strategy.build_mng import (
    BuildResult,
)
from action_resolver.hedge_2_strategy.optimization_mng import (
    OptimizationResult,
)
from utils.utils import get_inverse_side
from action_processor.action_source import ActionSource


def transform(
    result,
    symbol: str,
    side: str,
):
    if isinstance(result, BuildResult):
        return _transform_build(result, symbol)

    if isinstance(result, OptimizationResult):
        return _transform_optimization(result, symbol, side)

    raise Exception(
        f"Unsupported result type: {type(result)}"
    )


def _transform_build(
    result: BuildResult,
    symbol: str
):
    if not result.allowed:
        return ActionCommand(
            action=Action.NO_ACTION,
            symbol=symbol,
        )

    return ActionCommand(
        action=Action.OPEN,
        symbol=symbol,
        side=result.side,
        qty=result.qty,
        source=ActionSource.HEDGE_OPEN
    )


def _transform_optimization(
    result: OptimizationResult,
    symbol: str,
    side: str
):
    if not result.found:
        return ActionCommand(
            action=Action.NO_ACTION,
            symbol=symbol,
        )

    levels = [
        lvl for lvl in (result.losing_level, result.profitable_level)
        if lvl is not None
    ]

    return ActionCommand(
        action=Action.CLOSE,
        symbol=symbol,
        side=get_inverse_side(side),
        qty=result.qty,
        levels=levels,
        source=ActionSource.HEDGE_CLOSE
    )