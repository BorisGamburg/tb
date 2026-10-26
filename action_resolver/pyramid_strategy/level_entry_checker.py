from dataclasses import dataclass

from action_resolver.hedge_2_strategy.ha_trend_checker import (
    HATrendChecker,
)
from action_resolver.hedge_2_strategy.level_distance_checker import (
    is_level_distance_allowed,
)
from common.trading_info import TradingInfo
from services.bb_service import BBService
from signals.ha_reversal_signal import HAReversalSignal


@dataclass
class PyramidEntryResult:
    allowed: bool
    qty: float
    trend_active: bool
    ha_reversal: bool
    bb_allowed: bool
    position_allowed: bool
    distance_allowed: bool


class PyramidEntryChecker:

    def __init__(
        self,
        proxy_driver,
        symbol: str,
        side: str,
        timeframe: str,
        step_pct: float,
        qty_pct: float,
        trading_info: TradingInfo,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side
        self.timeframe = timeframe
        self.step_ratio = step_pct / 100
        self.qty_ratio = qty_pct / 100
        self.trading_info = trading_info

        self.main_side = (
            "Sell" if side == "Buy" else "Buy"
        )

        self.ha_trend = HATrendChecker(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
            side=self.side,
        )

        self.ha_signal = HAReversalSignal(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

        self.bb_service = BBService(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

    def _get_current_price(self) -> float:
        return float(
            self.proxy_driver.get_last_price(
                self.symbol
            )
        )

    def _check_position(
        self,
        cur_price: float,
        entries,
    ) -> bool:
        # Для Buy не должно быть уровней ниже цены.
        # Для Sell не должно быть уровней выше цены.
        if self.side == "Buy":
            return all(
                entry.price >= cur_price
                for entry in entries
            )

        return all(
            entry.price <= cur_price
            for entry in entries
        )

    def _check_trend(self) -> bool:
        return self.ha_trend.is_active(
            self.timeframe
        )

    def _check_ha_reversal(self) -> bool:
        ha_reversal, _ = self.ha_signal.is_entry(
            self.timeframe,
            self.side,
        )
        return ha_reversal

    def _check_bb(
        self,
        cur_price: float,
    ) -> bool:
        bb = self.bb_service.get_live(
            self.timeframe
        )

        if self.side == "Buy":
            return cur_price < bb["mid"]

        return cur_price > bb["mid"]

    def _check_distance(
        self,
        cur_price: float,
        entries,
    ) -> bool:
        return is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=self.step_ratio,
        )

    def _get_pyramid_qty(self) -> float:
        main_position = self.proxy_driver.get_position(
            self.symbol,
            self.main_side,
        )

        main_qty = float(
            main_position["size"]
        )

        pyramid_qty = self.trading_info.get_valid_order_qty(
            main_qty * self.qty_ratio
        )

        return pyramid_qty

    def check(
        self,
        entries,
    ) -> PyramidEntryResult:
        # 1. Получаем текущую цену
        cur_price = self._get_current_price()

        # 2. Сначала проверяем расположение уровней
        position_allowed = self._check_position(cur_price, entries)
        if not position_allowed:
            return self._position_rejected()

        # 3. Проверяем активность тренда
        trend_active = self._check_trend()

        # 4. Проверяем разворот HA
        ha_reversal = self._check_ha_reversal()

        # 5. Проверяем положение цены относительно BB
        bb_allowed = self._check_bb(cur_price)

        # 6. Проверяем дистанцию до существующих уровней
        distance_allowed = self._check_distance(cur_price, entries)

        # 7. Рассчитываем объём уровня
        pyramid_qty = self._get_pyramid_qty()

        # 8. Принимаем итоговое решение
        allowed = (
            trend_active
            and ha_reversal
            and bb_allowed
            and distance_allowed
            and pyramid_qty > 0
        )

        return PyramidEntryResult(
            allowed=allowed,
            qty=pyramid_qty,
            trend_active=trend_active,
            ha_reversal=ha_reversal,
            bb_allowed=bb_allowed,
            position_allowed=position_allowed,
            distance_allowed=distance_allowed,
        )

    def _position_rejected(self) -> PyramidEntryResult:
        return PyramidEntryResult(
            allowed=False,
            qty=0.0,
            trend_active=False,
            ha_reversal=False,
            bb_allowed=False,
            position_allowed=False,
            distance_allowed=False,
        )    