from pprint import pprint
from typing import Any, Dict, Optional
import math
import time
from prog.proxy_server.proxy_driver import ProxyDriver


class CandleMng:
    def __init__(self, 
        symbol: str, 
        prov_driver: ProxyDriver,
        logger,
        label: str = "", 
    ) -> None:
        # Хранилище состояния: {timeframe_str: last_closed_timestamp_int}
        self.candle_close_time: Dict[str, int] = {} 
        self.symbol = symbol
        self.logger = logger
        self.label = label
        self.prov_driver = prov_driver

    def _get_cur_candle_close_time(self, timeframe_min: str) -> int:
        """
        Расчет таймстампа закрытия текущей свечи.
        
        Логика: Находим начало текущего интервала 
        и прибавляем к нему длительность таймфрейма.
        
        :param timeframe: Таймфрейм в минутах (строка или число).
        :return: Таймстамп Unix (в секундах) закрытия текущей свечи.
        """
        
        # 1. Определение длительности таймфрейма в секундах
        # Пытаемся преобразовать строку в число минут.
        tf_seconds = int(timeframe_min) * 60
        
        # 2. Получение текущего системного таймстампа
        current_timestamp = int(time.time())
        
        # 3. Расчет начала текущей свечи 
        start_of_current_candle = math.floor(current_timestamp / tf_seconds) * tf_seconds
        
        # 4. Расчет времени закрытия текущей свечи
        close_time_of_current_candle = start_of_current_candle + tf_seconds
        
        return close_time_of_current_candle
    
    def check_candle_close(self, timeframe: str) -> bool:
        """
        Возвращает True, если свеча закрылась с момента последней проверки
        для заданного таймфрейма.
        """
        # Проверяем первый ли это вызов для данного таймфрейма.
        cur_cct = self.candle_close_time.get(timeframe, None)
        if cur_cct is None:
            # Первый вызов - инициализируем состояние
            self.candle_close_time[timeframe] = self._get_cur_candle_close_time(timeframe)
            return False
        
        # Не первый вызов - проверяем закрытие свечи

        # Получаем таймстамп с текущим временем 
        cur_timestamp = int(time.time())

        # Сравниваем текущий таймстамп с временем закрытия текущей свечи
        if cur_timestamp > cur_cct:
            # Свеча закрылась - обновляем candle_close_time
            self.candle_close_time[timeframe] = self._get_cur_candle_close_time(timeframe)
            return True
        
        # Свеча еще не закрылась
        return False

    def get_last_closed_candle(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """
        Просто берем данные. Если сервер жив, данные будут.
        """
        try:
            # Стучимся к нашему prov_driver
            data = self.prov_driver.get_data(symbol, timeframe)

            if data is None:
                raise ValueError("data is None")
            
            # Возвращаем готовую свечу. 
            # Если ключа нет, Python сам выкинет ошибку, и мы ее увидим в логах.
            return data['prev_ha'] 

        except Exception as e:
            self.logger.error(f"Ошибка при получении свечи через сервер: {e}")
            return None

    def get_candle_color(self, open_p: float, close_p: float) -> str:
        """Проверка цвета свечи: возвращает True если цвет соответствует `self.HEDGE_SIDE`."""
        if close_p < open_p:
            return "Red"
        elif close_p > open_p:
            return "Green"
        else:
            return "Neutral"
