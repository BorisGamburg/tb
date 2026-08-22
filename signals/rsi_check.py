from typing import Optional
from prog.proxy_server.proxy_driver import ProxyDriver


class RSICheck:

    def __init__(self, symbol: str, logger, prov_driver: ProxyDriver):
        self.symbol = symbol
        self.logger = logger
        self.data_serv = prov_driver

    def _get_remote_rsi(self, tf: str) -> Optional[float]:
        try:
            data = self.data_serv.get_data(self.symbol, tf=tf)

            if data and 'rsi' in data:
                return data['rsi']

        except Exception as e:
            self.logger.error(f"Ошибка получения RSI {self.symbol}: {e}")

        return None

    def check(self, tf: str, side: str, threshold: float) -> bool:
        """
        Простая проверка RSI.

        Sell: RSI > threshold  
        Buy:  RSI < threshold
        """

        rsi = self._get_remote_rsi(tf)

        if rsi is None:
            return False
        
        #self.logger.info(f"RSI Check - RSI: {rsi:.2f}, Threshold: {threshold}, Side: {side}")

        if side == "Sell":
            return rsi > threshold
        else:
            return rsi < threshold