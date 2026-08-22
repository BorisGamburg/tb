import threading
from pybit.unified_trading import WebSocket

class BalanceMng:
    def __init__(self, exchange_driver):
        self.exchange_driver = exchange_driver
        self._balance = 0.0
        self._lock = threading.Lock()
        
        # 1. Загружаем начальный баланс через HTTP
        self._initial_fetch()

        # 2. Запускаем собственный WebSocket для обновлений
        self.ws = WebSocket(
            testnet=False,
            api_key=self.exchange_driver.api_key,
            api_secret=self.exchange_driver.api_secret,
            channel_type="private"
        )
        self.ws.wallet_stream(callback=self.update_from_ws)

    def _initial_fetch(self):
        """Первичная загрузка баланса."""
        self._balance = float(self.exchange_driver.get_balance())

    def update_from_ws(self, msg):
        """Коллбэк для обновлений из вебсокета."""
        if "data" in msg:
            with self._lock:
                for coin in msg['data'][0]['coin']:
                    if coin['coin'] == 'USDT':
                        self._balance = float(coin['walletBalance'])

    def get_val(self) -> float:
        """Атомарное получение текущего баланса."""
        with self._lock:
            return self._balance
            
    def stop(self):
        """Остановка вебсокета."""
        self.ws.exit()