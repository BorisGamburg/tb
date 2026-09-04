from action_processor.action import Action, ActionCommand
from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.ha_reversal import HAReversalSignal
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from rich.text import Text
from common.trading_info import TradingInfo


class EntryChecker:
    def __init__(
        self,
        runtime,
        state_store: State,
        map_mng: GridMTFMapMng,
        proxy_driver,
        price_service,
        symbol: str,
        side: str,
        trading_info: TradingInfo,
    ):
        self.runtime = runtime
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.symbol = symbol
        self.side = side
        self.trading_info = trading_info

        self.ha_signal = HAReversalSignal(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

    def _get_rsi_last_closed(self, tf):

        data = self.proxy_driver.get_rsi(
            symbol=self.symbol,
            tf=tf
        )

        return data.get("rsi_last_closed")

    def _is_rsi_entry_threshold_ok(
        self,
        rsi,
        threshold
    ) -> bool:

        if rsi is None or threshold is None:
            return False

        if self.side == "Sell":
            return rsi >= threshold

        return rsi <= threshold

    def _is_rsi_entry_ok(self) -> bool:
        entries = self.state_store.stack_mng.data.entries
        level = len(entries)
        tpl = self.map_mng.get_template_by_level(level)

        # --- TF RSI ---
        rsi_tf = self._get_rsi_last_closed(
            tpl.tf_filter
        )
        tf_threshold = tpl.tf_rsi_entry_threshold
        rsi_tf_entry_ok = self._is_rsi_entry_threshold_ok(
            rsi_tf,
            tf_threshold
        )

        # --- HTF RSI ---
        rsi_htf = self._get_rsi_last_closed(
            tpl.htf_filter
        )
        htf_threshold = tpl.htf_rsi_entry_threshold
        rsi_htf_entry_ok = self._is_rsi_entry_threshold_ok(
            rsi_htf,
            htf_threshold
        )

        overall = "PASS" if rsi_tf_entry_ok and rsi_htf_entry_ok else "BLOCK"

        tf_th = (
            f"{tf_threshold:.0f}"
            if tf_threshold is not None
            else "N/A"
        )
        htf_th = (
            f"{htf_threshold:.0f}"
            if htf_threshold is not None
            else "N/A"
        )

        tf_v = (
            f"{rsi_tf:.1f}"
            if rsi_tf is not None
            else "N/A"
        )
        htf_v = (
            f"{rsi_htf:.1f}"
            if rsi_htf is not None
            else "N/A"
        )

        tf_s = "PASS" if rsi_tf_entry_ok else "BLOCK"
        htf_s = "PASS" if rsi_htf_entry_ok else "BLOCK"

        status = Text()
        status.append(
            overall,
            style="black on green" if overall == "PASS" else "white on red",
        )
        status.append(f" [{tpl.tf_filter}m:")
        status.append(
            tf_s,
            style="black on green" if tf_s == "PASS" else "white on red",
        )
        status.append(f"({tf_v}/{tf_th}) | {tpl.htf_filter}m:")
        status.append(
            htf_s,
            style="black on green" if htf_s == "PASS" else "white on red",
        )
        status.append(f"({htf_v}/{htf_th})]")

        self.runtime.rsi_entry_status = status

        return rsi_tf_entry_ok and rsi_htf_entry_ok    

    def check(self):
        entries = self.state_store.stack_mng.data.entries
        level = len(entries)
        tf = self.map_mng.get_tf_for_level(level)

        # Проверяем все фильтры независимо
        ha_ok, ha_message = self.ha_signal.is_entry(tf, self.side)
        rsi_ok = self._is_rsi_entry_ok()
        distance_ok = self._is_distance_ok(entries)

        # Все статусы уже сформированы к этому моменту
        self.runtime.ha_entry_status = ha_message

        # Принимаем решение только после проверки всех фильтров
        if not ha_ok or not rsi_ok or not distance_ok:
            return None

        # Формируем команду
        qty = self._get_qty()     
        return ActionCommand(
            action=Action.OPEN,
            symbol=self.symbol,
            side=self.side,
            qty=qty,
            reason="ha_reversal",
        )

    def _get_qty(self):
        cur_map_elem = self.map_mng.get_cur_map_elem()
        qty_factor = cur_map_elem.qty_pct / 100

        balance = self.proxy_driver.get_balance()
        qty_in_usd = qty_factor * balance

        price = self.proxy_driver.get_last_price(self.symbol)

        qty = qty_in_usd / price

        qty = self.trading_info.get_valid_order_qty(qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid OPEN qty: {qty} "
                f"(qty_factor={qty_factor})"
            )

        return qty    

    def _is_distance_ok(
        self,
        entries,
    ) -> bool:

        if not entries:
            self.runtime.distance_entry_status = "PASS"
            return True

        price = self.proxy_driver.get_last_price(
            self.symbol
        )

        last_entry = entries[-1]

        level = len(entries) 
        current_tf = self.map_mng.get_tf_for_level(level)
        

        atr = self._get_last_atr(current_tf)

        k = 1.0
        min_distance_ratio = 0.0035

        required_move = max(
            k * atr,
            min_distance_ratio * price
        )

        if self.side == "Sell":
            dist_ok = (
                price >
                last_entry.price + required_move
            )
        else:
            dist_ok = (
                price <
                last_entry.price - required_move
            )

        self.runtime.distance_entry_status = "PASS" if dist_ok else "BLOCK"

        return dist_ok

    def _get_last_atr(
        self,
        tf: str,
        period: int = 14
    ) -> float:

        response = self.proxy_driver.get_atr_ohlc(
            symbol=self.symbol,
            tf=tf,
            length=period
        )

        if "error" in response:
            raise RuntimeError(response["error"])

        atr_values = response.get("atr")

        if not atr_values or len(atr_values) < 2:
            raise RuntimeError("ATR data invalid")

        atr = atr_values[-2]

        if atr is None or atr <= 0:
            raise RuntimeError(
                f"Invalid ATR: {atr}"
            )

        return atr