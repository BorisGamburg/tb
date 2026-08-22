import time
from prog.signals.base_signals import BaseSignals
from prog.action_resolver.ha_analyzer import HaAnalyzer  # Новый общий модуль


class BBSignals(BaseSignals):

    def __init__(self, symbol, side, logger, proxy_driver):
        super().__init__(symbol, side, logger, proxy_driver)
        self._last_reduce_ts = 0
        self.logger = logger
        self.bb_break_active = False

    def _get_candles(self, tf: str):
        data = self.proxy_driver.get_bb_ohlc(self.symbol, tf)
        candles = data.get("candles", [])
        bb = data.get("bb", [])
        return candles, bb

    def check_avdo(self, map_elem):
        # Используем единый tf
        tf = map_elem.tf
        candles, bb = self._get_candles(tf)
        return self._check_bb_signal(candles, bb, self.side, mode="avdo")
    
    def check_bb_break(self, data):
        if self.side == "Sell":
            if data["last_price"] < data["bb_low"]:
                self.logger.info(f"Пробой bb low")
                self.bb_break_active = True
        else:
            # Для Buy реализация по аналогии
            if data["last_price"] > data["bb_high"]:
                self.logger.info(f"Пробой bb high")
                self.bb_break_active = True
        
    def _get_data(self, map_elem):
        # Используем единый tf
        return self.proxy_driver.get_data(
            symbol=self.symbol,
            tf=str(map_elem.tf)
        )     

    def check_prta(self, map_elem):
        data = self._get_data(map_elem)
        price = data["last_price"]
        bb_mid = data["bb_mid"]

        # 1. Проверка зоны (быстрый выход, если цена еще не за Mid)
        if not self._is_price_in_profit_zone(price, bb_mid):
            return False, f"Price {price} not beyond BB Mid {bb_mid}"

        # 2. Проверка триггера разворота через общий HaAnalyzer
        if HaAnalyzer.is_reversal(self.side, data):
            side_action = "UP" if self.side == "Sell" else "DOWN"
            return True, f"PRTA: Price in zone + HA reversal {side_action}"

        return False, "In profit zone, but waiting for HA reversal"

    def check_ha(self, map_elem, direction: str):
        """
        direction:
            'reversal' — против позиции (для выхода)
            'trend'    — по позиции (для rearm)
        """
        data = self._get_data(map_elem)
        
        if direction == "reversal":
            if HaAnalyzer.is_reversal(self.side, data):
                return True, f"HA {self.side} reversal"
        
        elif direction == "trend":
            # Если не разворот — значит продолжение тренда (упрощенно)
            if not HaAnalyzer.is_reversal(self.side, data):
                return True, f"HA {self.side} continuation"

        return False, "no signal"

    def _is_price_in_profit_zone(self, current_price, bb_mid):
        if self.side == "Sell":
            return current_price < bb_mid
        return current_price > bb_mid

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (оставлены без изменений) ---

    def _check_reduce(self):
        now = time.time()
        if now - self._last_reduce_ts < 60:
            return False
        self._last_reduce_ts = now
        return True

    def get_avdo_rsi(self, map_elem):
        return 0.0
    
    def _check_bb_signal(self, candles, bb, side, mode: str):
        if len(candles) < 3 or len(bb) < 1:
            return False, "Low history"
        
        c0, c1, c2 = candles[-1], candles[-2], candles[-3]
        bb_last = bb[-1]
        price, bb_mid = c0["close"], bb_last["mid"]

        if side == "Sell":
            if mode == "avdo":
                above_mid = price > bb_mid
                reversal = c1["close"] < c2["close"]
                if above_mid and reversal:
                    return True, "BB mid + reversal short"
                return False, "no signal"
            raise ValueError(f"Invalid mode: {mode}")
        else:
            # Для BUY логика будет зеркальной
            if mode == "avdo":
                below_mid = price < bb_mid
                reversal = c1["close"] > c2["close"]
                if below_mid and reversal:
                    return True, "BB mid + reversal long"
                return False, "no signal"
            raise ValueError(f"Invalid mode: {mode}")