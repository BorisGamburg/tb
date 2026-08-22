from prog.proxy_server.proxy_driver import ProxyDriver
from prog.utils.utils import get_candle_color 


class HARevers:
    """
    Класс для расчета и хранения последней и предпоследней полных HA свеч.
    """
    def __init__(
        self, 
        symbol: str, 
        side: str,
        prov_driver: ProxyDriver,
        logger,
        label:str = ""
    ):
        self.symbol = symbol
        self.side = side
        self.candles = None
        self.logger = logger
        self.prov_driver = prov_driver
        self.label = label

    def check_revers(self, timeframe: str):
        # Получаем последнюю и предпоследнюю закрытые HA свечи
        self.calc_cur_and_sec_last_ha_candles(timeframe)

        # Получаем сторону разворота 
        side_reverse = self._check_reverse_side()

        # debug
        # if side_reverse != "None":
        #     self.logger.info(f"{self.label} HA Revers: {side_reverse}")

        # Если разворот в нужную сторону - возвращаем True
        if self.side == side_reverse:
            return True
        else:
            return False

    def calc_cur_and_sec_last_ha_candles(self, timeframe: str):
        data = self.prov_driver.get_data(self.symbol, tf=timeframe)

        self.cur_ha_candle = data['curr_ha']
        self.prev_ha_candle = data['prev_ha']

        #print(f"{self.label} - Cur HA candle: {self.cur_ha_candle}")
        # print(f"{self.label} - Prev HA candle: {self.prev_ha_candle}")

    def _check_reverse_side(self):

        prev_color = self.get_ha_candle_color(self.prev_ha_candle)
        cur_color = self.get_ha_candle_color(self.cur_ha_candle)

        self.logger.debug(f"{self.label} prev HA: {prev_color}")
        self.logger.debug(f"{self.label} curr HA: {cur_color}")

        if prev_color == "Red" and cur_color == "Green":
            return "Buy"

        if prev_color == "Green" and cur_color == "Red":
            return "Sell"

        return "None"
            
    def get_ha_candle_color(self, candle):
            """Прослойка для вызова библиотечной функции"""
            return get_candle_color(candle['HA_open'], candle['HA_close'])