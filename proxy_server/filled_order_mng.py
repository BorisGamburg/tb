from pprint import pprint
import threading
import time
from pybit.unified_trading import WebSocket
from prog.proxy_server.shared_proxy import SharedProxy

class FilledOrderMng:
    def __init__(self, shared_proxy: SharedProxy, history_days=1):
        self.exchange_driver = shared_proxy.exchange_driver
        self.logger = shared_proxy.logger
        self.history_lifetime_ms = history_days * 24 * 60 * 60 * 1000
        self._filled_orders = {}  # {order_id: timestamp_ms}
        self._lock = threading.Lock()

        # 1. Сначала загружаем историю из API (чтобы не было дыр)
        self.sync_from_api(days=history_days)

        # 2. Создаем и запускаем собственный WebSocket поток
        self.ws = WebSocket(
            testnet=False,
            api_key=self.exchange_driver.api_key,
            api_secret=self.exchange_driver.api_secret,
            channel_type="private"
        )
        
        # Подписываемся только на поток ордеров
        self.ws.order_stream(callback=self._update_handler)
        
        self.logger.info("🔌 FilledOrderMng: Собственный WebSocket запущен.")

    def sync_from_api(self, days=2):
        """Загрузка истории из API Bybit при старте."""
        try:
            # Загружаем историю ордеров за указанный период с биржи
            history = self.exchange_driver.get_order_history(days_back=days)
            if not history:
                return
            symbol_history = [o for o in history if o.get('symbol') == "DUSKUSDT"]
            print(symbol_history)
            
            # Заполняем внутренний кэш исполненных ордеров
            with self._lock:
                for o in history:
                    if o.get('orderStatus') == 'Filled':
                        oid = o['orderId']
                        ts = int(o['updatedTime'])
                        self._filled_orders[oid] = {
                            "ts": ts,
                            "symbol": o.get('symbol')
                        }

            self.logger.info(f"✅ FilledOrderMng: Синхронизация завершена. В базе: {len(self._filled_orders)}")
        
        except Exception as e:
            self.logger.error(f"❌ FilledOrderMng: Ошибка синхронизации: {e}")

    def _update_handler(self, msg):
        """Внутренний обработчик событий WebSocket."""
        if "data" in msg:
            now_ms = int(time.time() * 1000)
            with self._lock:
                for o in msg['data']:
                    if o.get('orderStatus') == 'Filled':
                        oid = o['orderId']
                        ts = int(o.get('updatedTime', now_ms))
                        self._filled_orders[oid] = {
                            "ts": ts,
                            "symbol": o.get('symbol')
                        }
                
                # Чистка старых данных (старше 2 дней)
                self._cleanup(now_ms)

    def _cleanup(self, now_ms):
        # ВАЖНО: теперь достаем 'ts' из словаря data
        self._filled_orders = {
            oid: data for oid, data in self._filled_orders.items() 
            if now_ms - data['ts'] < self.history_lifetime_ms
        }

    def get_orders(self, symbol: str = None):
        """Метод для передачи списка ID боту через ZMQ с фильтрацией по символу."""
        with self._lock:
            if symbol:
                # Отдаем только те ордера, которые принадлежат этому символу
                symbol_upper = symbol.upper()
                filtered_orders = {}
                for oid, data in self._filled_orders.items():
                    if data.get('symbol') == symbol_upper:
                        filtered_orders[oid] = data
                return filtered_orders
            else:
                # Отдаем все ордера
                return self._filled_orders

    def stop(self):
        """Корректная остановка WebSocket."""
        try:
            self.ws.exit()
        except:
            pass