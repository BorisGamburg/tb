import threading
import time
from pybit.unified_trading import WebSocket
from pprint import pprint
from prog.drivers.bybit_driver import BybitDriver

class PositionMng:
    def __init__(self, exchange_driver: BybitDriver, logger):
        self.exchange_driver = exchange_driver
        self.logger = logger
        self._positions = {}
        self._lock = threading.Lock()
        
        # 1. Первичная загрузка
        self._initial_fetch()

        # 2. Запуск WebSocket
        self.ws = WebSocket(
            testnet=False,
            api_key=self.exchange_driver.api_key,
            api_secret=self.exchange_driver.api_secret,
            channel_type="private"
        )
        self.ws.position_stream(callback=self.update_from_ws)

        # 3. ЗАПУСК ФОНОВОГО ПОТОКА ДЛЯ ОБНОВЛЕНИЯ ПО API
        self._stop_event = threading.Event()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

        time.sleep(2) 
        if self.ws.is_connected():
            self.logger.info("✅ WebSocket: Соединение установлено")
        else:
            self.logger.error("❌ WebSocket: Ошибка подключения!")


    def _initial_fetch(self):
        """Первичная загрузка всех позиций."""
        all_pos = self.exchange_driver.get_all_active_positions()
        with self._lock:
            self._positions.clear()
            for p in all_pos:
                # ОПРЕДЕЛЯЕМ СТОРОНУ ПО ИНДЕКСУ (как в WS)
                idx = int(p['positionIdx']) 
                side = "Buy" if idx == 1 else "Sell" if idx == 2 else p.get('side')
                
                if not side: continue
                
                key = f"{p['symbol']}_{side}"
                self._positions[key] = {
                    "symbol": p['symbol'],
                    "size": float(p['size']),
                    "entry_price": float(p['entry_price']),
                    "side": side,
                    "unrealisedPnl": float(p.get("unrealisedPnl", 0))
                }

    def update_from_ws(self, msg):
        """Коллбэк для обновлений позиций через WebSocket."""
        if "data" in msg:
            with self._lock:
                for p in msg['data']:
                    symbol = p.get('symbol')
                    idx = int(p.get('positionIdx', 0))
                    side = "Buy" if idx == 1 else "Sell" if idx == 2 else p.get('side')
                    
                    if not symbol or not side:
                        continue
                        
                    key = f"{symbol}_{side}"
                    size = float(p.get('size', 0))

                    # Берем текущие данные из памяти
                    old_pos = self._positions.get(key, {})
                    
                    # ПРОВЕРКА ЦЕНЫ: сохраняем старую, если новая не пришла в WS
                    raw_entry = p.get('entryPrice')
                    if raw_entry:
                        new_entry = float(raw_entry)
                    else:
                        new_entry = old_pos.get('entry_price', 0.0)

                    raw_pnl = p.get("unrealisedPnl")
                    if raw_pnl is not None:
                        pnl = float(raw_pnl)
                    else:
                        pnl = old_pos.get("unrealisedPnl", 0.0)

                    # Обновляем структуру
                    self._positions[key] = {
                        "symbol": symbol,
                        "size": size,
                        "entry_price": new_entry if size > 0 else 0.0,
                        "unrealisedPnl": pnl,
                        "side": side
                    }
                    
                    if self.logger:
                        self.logger.debug(f"Обновление позиции {key}: size={size} price={new_entry}")



    def get_pos(self, symbol: str, side: str) -> dict:
        """Получение конкретной позиции."""
        with self._lock:
            return self._positions.get(
                f"{symbol}_{side}",
                {"size": 0, "entry_price": 0, "unrealisedPnl": 0}
            )

    def get_all(self) -> dict:
        """Получение всех позиций сразу."""
        with self._lock:
            return self._positions.copy()

    def stop(self):
        """Остановка всего менеджера."""
        self._stop_event.set() # Останавливаем фоновый поток
        self.ws.exit()         # Закрываем вебсокет
        self.logger.info("PositionMng остановлен.")
        
    def _refresh_loop(self):
        """Цикл, который делает проверку по API раз в 15 минут."""
        while not self._stop_event.is_set():
            # Ждем 5 минут (300 секунд)
            # Используем wait(timeout), чтобы поток можно было мгновенно остановить при выходе
            if self._stop_event.wait(timeout=300):
                break
                
            try:
                self.logger.info("🔄 Плановая сверка позиций через API (Health Check)...")
                self._initial_fetch()
            except Exception as e:
                self.logger.error(f"❌ Ошибка при плановой сверке: {e}")        