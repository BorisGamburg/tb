import threading
from pybit.unified_trading import WebSocket
from prog.proxy_server.shared_proxy import SharedProxy

class ActiveOrderMng:
    def __init__(self, shared_proxy: SharedProxy):
        self.exchange_driver = shared_proxy.exchange_driver
        self._orders = {}  # {order_id: data}
        self._lock = threading.Lock()
        
        # 1. Загружаем ВСЕ ордера через пагинацию (может занять несколько секунд при 100+ ордерах)
        self._initial_fetch()

        # 2. Запускаем WebSocket
        self.ws = WebSocket(
            testnet=False,
            api_key=self.exchange_driver.api_key,
            api_secret=self.exchange_driver.api_secret,
            channel_type="private"
        )
        self.ws.order_stream(callback=self.update_from_ws)

    def _initial_fetch(self):
        """Полная синхронизация при запуске."""
        orders = self.exchange_driver.get_all_active_orders()
        with self._lock:
            for o in orders:
                self._orders[o['order_id']] = o

    def update_from_ws(self, msg):
        """Обновление в реальном времени."""
        if "data" in msg:
            with self._lock:
                for o in msg['data']:
                    oid = o['orderId']
                    status = o['orderStatus']
                    
                    # Если ордер закрыт окончательно
                    if status in ["Filled", "Cancelled", "Deactivated", "Rejected"]:
                        self._orders.pop(oid, None)
                    else:
                        # Обновляем/добавляем активный ордер
                        self._orders[oid] = {
                            "order_id": oid,
                            "symbol": o['symbol'],
                            "side": o['side'],
                            "price": float(o['price']) if o['price'] else 0.0,
                            "qty": float(o['qty']),
                            "orderType": o['orderType'],
                            "orderStatus": status
                        }

    def get_active_orders(self, symbol: str) -> list:
        """Получить список всех живых ордеров по символу из памяти."""
        with self._lock:
            return [o for o in self._orders.values() if o['symbol'] == symbol]

    def count_all(self) -> int:
        """Общее количество ордеров в сетках."""
        with self._lock:
            return len(self._orders)

    def stop(self):
        self.ws.exit()