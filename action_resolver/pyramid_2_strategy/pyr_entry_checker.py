from common.trading_info import TradingInfo
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_signal import (
    HAReversalSignal,
)
from action_resolver.pyramid_2_strategy.pyr_qty_calculator import PyrQtyCalculator


class PyrEntryChecker:

    def __init__(
        self,
        proxy_driver,
        symbol: str,
        side: str,
        step_pct: float,
        qty_pct: float,
        trading_info: TradingInfo,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side
        self.step_ratio = step_pct / 100

        self.qty_calculator = PyrQtyCalculator(
            proxy_driver=proxy_driver,
            symbol=symbol,
            qty_pct=qty_pct,
            trading_info=trading_info,
        )

        self.ha_signal = HAReversalSignal(
            proxy_driver=proxy_driver,
            symbol=symbol,
        )

    def _get_pyramid_qty(self) -> float:
        _, qty = self.qty_calculator.calculate()
        return qty

    def get_qty(self) -> float:
        """Объём нового уровня пирамиды (вход, REARM, HA Breakout)."""
        return self._get_pyramid_qty()