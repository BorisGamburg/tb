from abc import ABC, abstractmethod
import logging
from prog.proxy_server.proxy_driver import ProxyDriver


class BaseSignals(ABC):

    def __init__(
        self,
        symbol: str,
        side: str,
        logger: logging.Logger,
        proxy_driver: ProxyDriver
    ):
        self.symbol = symbol
        self.side = side
        self.logger = logger
        self.proxy_driver = proxy_driver

    @abstractmethod
    def check_avdo(self, map_elem):
        """
        Проверка сигнала усреднения.
        Возвращает:
        (bool, reason)
        """
        pass

    @abstractmethod
    def check_prta(self, map_elem):
        """
        Проверка сигнала тейк-профита.
        Возвращает:
        (bool, reason)
        """
        pass

    @abstractmethod
    def get_avdo_rsi(self, map_elem):
        """
        Используется для отображения RSI в state-файле.
        """
        pass
