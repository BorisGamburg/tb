class HAReversalSignal:

    def __init__(self, proxy_driver, symbol: str):
        self.proxy_driver = proxy_driver
        self.symbol = symbol

    def is_entry(self, tf: str, side: str):

        prev_color, curr_color = self._get_closed_ha_color(tf)

        payload = {
            "prev_color": prev_color,
            "curr_color": curr_color,
        }

        # Проверка на doji
        if prev_color == "doji" or curr_color == "doji":
            return False, payload

        # --- SIGNAL ---
        if side == "Sell":
            signal = prev_color == "green" and curr_color == "red"
        elif side == "Buy":
            signal = prev_color == "red" and curr_color == "green"
        else:
            raise RuntimeError(f"Invalid side: {side}")

        return signal, payload
    
    def is_exit(self, tf: str, side: str) -> bool:

        prev, curr = self._get_closed_ha_color(tf)

        if prev == "doji" or curr == "doji":
            return False        

        # --- SIGNAL ---
        if side == "Sell":
            signal = prev == "red" and curr == "green"
        elif side == "Buy":
            signal = prev == "green" and curr == "red"
        else:
            raise RuntimeError(f"Invalid side: {side}")

        return signal           

    def _get_closed_ha_color(self, tf: str):

        ha = self.proxy_driver.get_ha(
            symbol=self.symbol,
            tf=tf
        )

        if not ha or "prev2" not in ha or "prev1" not in ha:
            raise RuntimeError("Invalid HA data")

        prev = ha["prev2"]["color"]
        curr = ha["prev1"]["color"]

        VALID = ("green", "red", "doji")

        if prev not in VALID or curr not in VALID:
            raise RuntimeError(f"Invalid HA colors: prev={prev}, curr={curr}")

        return prev, curr        