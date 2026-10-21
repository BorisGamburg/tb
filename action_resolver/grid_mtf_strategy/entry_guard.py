from dataclasses import dataclass

from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from common.trading_info import TradingInfo
from utils.utils import get_inverse_side


@dataclass(frozen=True, slots=True)
class EntryGuardResult:
    allowed: bool
    reason: str | None = None


class EntryGuard:

    def __init__(
        self,
        state_store: State,
        map_mng: GridMTFMapMng,
        proxy_driver,
        trading_info: TradingInfo,
        logger,
        telegram,
    ):
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.trading_info = trading_info
        self.logger = logger
        self.telegram = telegram

        self.symbol = state_store.data.symbol
        self.side = state_store.data.side

        self._last_state: tuple | None = None

    def _get_main_qty(self) -> float:
        position = self.proxy_driver.get_position(
            self.symbol,
            self.side,
        )
        return float(position["size"])

    def _get_opposite_qty(self) -> float:
        position = self.proxy_driver.get_position(
            self.symbol,
            get_inverse_side(self.side),
        )
        return float(position["size"])

    def _get_open_qty(self) -> float:
        level = len(
            self.state_store.stack_mng.data.entries
        )

        template = self.map_mng.get_template_by_level(level)
        qty_factor = template.qty_pct / 100

        balance = self.proxy_driver.get_balance()
        price = self.proxy_driver.get_last_price(self.symbol)

        qty = qty_factor * balance / price
        qty = self.trading_info.get_valid_order_qty(qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid OPEN qty: {qty} "
                f"(qty_factor={qty_factor})"
            )

        return qty

    def is_allowed(self) -> EntryGuardResult:
        main_qty = self._get_main_qty()
        opposite_qty = self._get_opposite_qty()
        open_qty = self._get_open_qty()

        new_main_qty = main_qty + open_qty

        allowed = new_main_qty <= opposite_qty / 2

        result = EntryGuardResult(
            allowed=allowed,
            reason=None if allowed else "position_ratio",
        )

        self._handle_state_change(result)

        return result

    def _handle_state_change(
        self,
        result: EntryGuardResult,
    ) -> None:
        state = (
            result.allowed,
            result.reason,
        )

        if state == self._last_state:
            return

        self._last_state = state

        if result.allowed:
            return

        message = (
            f"{self.symbol} | "
            f"ENTRY GUARD | "
            f"OPEN BLOCKED | "
            f"reason={result.reason}"
        )

        self.logger.warning(message)
        self.telegram.send_telegram_message(message)