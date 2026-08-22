import time
import zmq
import threading
from typing import Any, cast


# --- СЛОЙ 1: ТРАНСПОРТ (Низкоуровневая связь) ---
class ZmqTransport:
    def __init__(self, logger, pipe_path):
        self.logger = logger
        self.pipe_path = pipe_path
        self.context = zmq.Context()
        self._thread_local = threading.local()

    def _get_socket(self):
        """Ленивая инициализация сокета для потока."""
        if not hasattr(self._thread_local, "socket"):
            socket = self.context.socket(zmq.REQ)
            socket.connect(self.pipe_path)
            # Настройки таймаутов
            socket.setsockopt(zmq.RCVTIMEO, 30000) # 30 сек на ответ
            socket.setsockopt(zmq.SNDTIMEO, 10000) # 10 сек на отправку
            socket.setsockopt(zmq.LINGER, 0)       # Закрывать мгновенно
            self._thread_local.socket = socket
        return self._thread_local.socket

    def disconnect(self):
        """Принудительное уничтожение сокета при зависании."""
        if hasattr(self._thread_local, "socket"):
            try:
                self._thread_local.socket.close()
            except Exception:
                pass
            del self._thread_local.socket

    def request(self, payload: dict):
        """Чистый цикл: отправить-получить."""
        socket = self._get_socket()
        socket.send_json(payload)
        return socket.recv_json()


# --- СЛОЙ 2: RUNNER (Логика повторов и отказоустойчивости) ---
class RetryRunner:
    def __init__(self, logger, pipe_path, max_attempts=3):
        self.logger = logger
        self.transport = ZmqTransport(logger, pipe_path)
        self.max_attempts = max_attempts

    def call(self, cmd: str, data: dict = None):
        payload = {"cmd": cmd, "data": data or {}}
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.transport.request(payload)
                if isinstance(result, dict) and "error" in result:
                    msg = result["error"]
                    raise RuntimeError(f"ProxyDriver: {msg}")

                return result
            
            except zmq.Again:
                self.logger.warning(f"⏳ [RETRY {attempt}/{self.max_attempts}] Таймаут '{cmd}'. Переподключение...")
                self.transport.disconnect()
                if attempt < self.max_attempts:
                    time.sleep(1) # Пауза, чтобы сервер успел подняться
            
            except Exception as e:
                self.logger.error(f"💥 [SYSTEM_ERROR] Попытка {attempt} ({cmd}): {e}")
                self.transport.disconnect()
                if attempt == self.max_attempts:
                    raise
        
        return {"error": "timeout", "status": "failed"}


# --- СЛОЙ 3: PROXY DRIVER (Бизнес-интерфейс для бота) ---
class ProxyDriver:
    def __init__(self, logger, pipe_path="ipc:///tmp/bybit_data.pipe.v22"):
        self.logger = logger
        # Драйвер создает внутри себя всю цепочку управления
        self.runner = RetryRunner(logger, pipe_path)

    def _execute(self, cmd, data=None):
        """Внутренний хелпер для запуска команд через раннер."""
        return self.runner.call(cmd, data)

    # --- Публичные методы (API) ---

    def get_data(self, symbol: str, tf: str):
        """Получение данных свечей и текущей цены."""
        return self._execute("get_candle_data", {"symbol": symbol.upper(), "tf": tf})

    def get_last_price(self, symbol: str, tf: str = "1") -> float:
        """Быстрое получение последней цены."""
        data = self.get_data(symbol, tf)
        price = data.get("last_price")
        return float(price) if price else 0.0

    def get_balance(self) -> float:
        """Получение баланса аккаунта."""
        result = self._execute("get_balance")
        return float(result.get("balance", 0))

    def get_position(self, symbol: str, side: str = "Buy") -> dict:
        """Получение данных конкретной позиции."""
        return self._execute("get_positions", {"symbol": symbol.upper(), "side": side})

    def get_active_orders(self, symbol: str) -> list:
        """Получение списка активных ордеров из памяти прокси."""
        result = self._execute("get_active_orders", {"symbol": symbol.upper()})
        return result.get("orders", [])

    def execute(self, method: str, **kwargs):
        """Универсальный метод для выполнения команд (ордера, настройки и т.д.)."""
        return self._execute("proxy", {"method": method, "kwargs": kwargs})
    
    def get_bb_ohlc(self, symbol: str, tf: str):
        """
        Получение OHLC свечей и Bollinger Bands.
        Используется стратегиями BB.
        """
        return self._execute(
            "get_bb_ohlc",
            {
                "symbol": symbol.upper(),
                "tf": tf
            }
        )
    
    def get_atr_ohlc(self, symbol: str, tf: str, length: int = 14):
        """
        Получение OHLC свечей и значений ATR (Average True Range).
        :param symbol: Торговая пара (напр. BTCUSDT)
        :param tf: Таймфрейм (напр. '5', '15', '60')
        :param length: Период расчета ATR (по умолчанию 14)
        """
        return self._execute(
            "get_atr_ohlc",
            {
                "symbol": symbol.upper(),
                "tf": tf,
                "length": length
            }
        )
    
    def get_cci(self, symbol: str, tf: str, length: int = 20):
        """
        Получение значений CCI и его slope.
        :param symbol: Торговая пара (например BTCUSDT)
        :param tf: Таймфрейм ('1', '5', '15' и т.д.)
        :param length: Период CCI (по умолчанию 20)
        """
        return self._execute(
            "get_cci",
            {
                "symbol": symbol.upper(),
                "tf": tf,
                "length": length
            }
        )   

    def get_adx(self, symbol: str, tf: str, length: int = 14):
        """
        Получение значений ADX, +DI, -DI и наклона (slope).
        :param symbol: Торговая пара (например BTCUSDT)
        :param tf: Таймфрейм ('1', '5', '15' и т.д.)
        :param length: Период ADX (по умолчанию 14)
        """
        return self._execute(
            "get_adx",
            {
                "symbol": symbol.upper(),
                "tf": tf,
                "length": length
            }
        ) 
    
    def get_ha(self, symbol: str, tf: str):
        """
        Получение последних 3 HA свечей (prev2, prev1, curr) и их цвета.
        :param symbol: Торговая пара (например BTCUSDT)
        :param tf: Таймфрейм ('1', '5', '15' и т.д.)
        """
        return self._execute(
            "get_ha",
            {
                "symbol": symbol.upper(),
                "tf": tf
            }
        )    
    
    def get_rsi(self, symbol: str, tf: str, length: int = 14):
        """
        Получение значений RSI для:
        - живой свечи
        - последней закрытой
        - предпоследней закрытой
        
        :param symbol: Торговая пара (например BTCUSDT)
        :param tf: Таймфрейм ('1', '5', '15' и т.д.)
        :param length: Период RSI (по умолчанию 14)
        """
        return self._execute(
            "get_rsi",
            {
                "symbol": symbol.upper(),
                "tf": tf,
                "length": length
            }
        )    
    
    def get_ema(self, symbol: str, tf: str, length: int = 21):
        """
        Получение значений EMA:
        - текущее значение (живая свеча)
        - последняя закрытая
        - предыдущая закрытая
        - slope EMA

        :param symbol: Торговая пара (например BTCUSDT)
        :param tf: Таймфрейм ('1', '5', '15' и т.д.)
        :param length: Период EMA (по умолчанию 21)
        """
        return self._execute(
            "get_ema",
            {
                "symbol": symbol.upper(),
                "tf": tf,
                "length": length
            }
        )    
    
    def get_ohlc(self, symbol: str, tf: str, n: int = 50):
        """
        Получение последних OHLC свечей без индикаторов.

        :param symbol: торговая пара (например BTCUSDT)
        :param tf: таймфрейм ('1','5','15','60' и т.д.)
        :param n: количество свечей
        """

        result = self._execute(
            "get_ohlc",
            {
                "symbol": symbol.upper(),
                "tf": tf,
                "n": n
            }
        )

        return result.get("candles", [])  

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        """
        Получение актуального тикера.

        Возвращает словарь вида:
        {
            "symbol": "BTCUSDT",
            "bid": 62950.1,
            "ask": 62950.2,
            "last": 62950.2,
            "timestamp": 1754230000.123,
        }
        """
        return cast(
                dict[str, Any],
                self._execute(
                    "get_ticker",
                    {
                        "symbol": symbol.upper(),
                    },
                ),
            )