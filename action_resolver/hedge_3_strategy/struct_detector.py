class StructureDetector:

    def __init__(self, proxy_driver, symbol, lookback: int = 30):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.lookback = lookback

    def _get_candles(self, tf: str):

        candles = self.proxy_driver.get_ohlc(
            symbol=self.symbol,
            tf=tf,
            n=self.lookback
        )

        if not candles or len(candles) < self.lookback:
            raise RuntimeError(
                f"Not enough candles: {len(candles) if candles else 0} < {self.lookback}"
            )

        return candles    

    def is_break_down(self, tf: str, snapshot) -> bool:
        candles = self._get_candles(tf)
        candles_closed = candles[:-1]  # удаляем живую свечу
        atr = self._get_last_atr(tf)
        swing_lows = self._get_swing_lows(candles_closed, atr)        

        if len(swing_lows) < 2:
            return False

        last_swing_low = swing_lows[-1]
        current_close = candles_closed[-1]["close"]

        snapshot.set("structure", "last_swing_low", last_swing_low)
        snapshot.set("structure", "current_close", current_close)

        return current_close < last_swing_low

    def is_entry(self, tf: str, side: str, snapshot) -> bool:
        """
        Entry = пробой в сторону позиции
        """

        if side == "Buy":
            return self.is_break_up(tf, snapshot)

        if side == "Sell":
            return self.is_break_down(tf, snapshot)

        raise RuntimeError(f"Invalid side: {side}")

    def is_exit(self, tf: str, side: str, snapshot) -> bool:
        """
        Exit = противоположный пробой (структурный разворот)
        """

        if side == "Buy":
            return self.is_break_down(tf, snapshot)

        if side == "Sell":
            return self.is_break_up(tf, snapshot)

        raise RuntimeError(f"Invalid side: {side}")        

    def _get_last_atr(self, tf: str, period: int = 14) -> float:

        response = self.proxy_driver.get_atr_ohlc(
            symbol=self.symbol,
            tf=tf,
            length=period
        )

        if not response:
            raise RuntimeError("ATR response is empty")

        atr_values = response.get("atr")

        # Берём только ЗАКРЫТУЮ свечу
        atr = atr_values[-2]

        return atr        

    def _get_swing_highs(self, candles, atr: float):

        if atr <= 0:
            raise RuntimeError(f"Invalid ATR: {atr}")

        k = 0.1  # вынести в конфиг
        threshold = k * atr

        highs = [c["high"] for c in candles]
        swings = []

        for i in range(1, len(highs) - 1):

            left = highs[i-1]
            mid = highs[i]
            right = highs[i+1]

            if (mid > left + threshold) and (mid > right + threshold):
                swings.append(mid)

        return swings        

    def _get_swing_lows(self, candles, atr: float):

        if atr <= 0:
            raise RuntimeError(f"Invalid ATR: {atr}")

        k = 0.1
        threshold = k * atr

        lows = [c["low"] for c in candles]
        swings = []

        for i in range(1, len(lows) - 1):

            left = lows[i-1]
            mid = lows[i]
            right = lows[i+1]

            if (mid < left - threshold) and (mid < right - threshold):
                swings.append(mid)

        return swings       

    def is_break_up(self, tf: str, snapshot) -> bool:

        candles = self._get_candles(tf)
        candles_closed = candles[:-1]

        atr = self._get_last_atr(tf)
        swing_highs = self._get_swing_highs(candles_closed, atr)

        if len(swing_highs) < 2:
            return False

        last_swing_high = swing_highs[-1]
        current_close = candles_closed[-1]["close"]

        snapshot.set("structure", "last_swing_high", last_swing_high)
        snapshot.set("structure", "current_high", current_close)

        return current_close > last_swing_high         