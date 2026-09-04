import math
import traceback
import pandas as pd
from time import time
from pybit.unified_trading import HTTP
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from pybit.exceptions import InvalidRequestError
import time
from typing import Any, Dict, cast
from prog.utils.utils import round_to_step
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=5, period=1)
def _global_api_limiter(func, *args, **kwargs):
    return func(*args, **kwargs)

class BybitDriver:
    def __init__(self, demo, api_key, api_secret, logger, telegram, timeout=5):
        self.demo = demo
        self.api_key = api_key
        self.api_secret = api_secret
        self.logger = logger
        self.telegram = telegram
        self.timeout = timeout
        self.max_attempts = 5
        self.retry_delay = 5  # seconds

        # Создаем клиент
        self.create_http_client()       

    def create_http_client(self):
        self.http_client = HTTP(
            demo=self.demo,
            api_key=self.api_key,
            api_secret=self.api_secret,
            timeout=self.timeout,
            recv_window=20000,
        )

    def retry_api_call(self, func, *args, **kwargs):
        """Оборачивает вызов API в цикл с попытками (без блокировок)."""

        # Извлекаем стек вызовов
        stack = traceback.extract_stack()
        
        # stack[-1] — это сам retry_api_call
        # stack[-2] — это метод в bybit_driver (например, get_balance)
        # stack[-3] — это то, что вызвало get_balance (например, balance_mng)
        
        driver_method = stack[-2].name  # Это будет 'get_balance'
        caller_module = stack[-2].filename.split('/')[-1] # Кто попросил данные (balance_mng.py)
        caller_line = stack[-2].lineno

        for attempt in range(1, self.max_attempts + 1):
            try:
                # Прямой вызов функции
                #self.logger.info(f"🚀 API Call: {driver_method} (from {caller_module}:{caller_line})")
                result = _global_api_limiter(func, *args, **kwargs)
                
                return result

            except Exception as e:
                error_msg = f"Ошибка API (попытка {attempt}/{self.max_attempts}): {str(e)}"
                self.logger.error(error_msg)
                
                if attempt == self.max_attempts:
                    raise Exception(f"Не удалось выполнить API после {self.max_attempts} попыток: {str(e)}")
                
                # Если поймали ошибку — пересоздаем коннект
                self.logger.info("Пересоздаем клиент из-за ошибки...")
                self.create_http_client()
                
                # Ждем перед следующей попыткой
                time.sleep(self.retry_delay)

    def get_balance(self):
        def call():
            balances = self.http_client.get_wallet_balance(accountType="UNIFIED", coin="USDT",)  
            return float(balances['result']['list'][0]['coin'][0]['walletBalance']) # type: ignore
        return self.retry_api_call(call)
    
    def get_last_price(self, symbol):
        """Получает последнюю цену тикера."""
        def call():
            ticker = self.http_client.get_tickers(category="linear", symbol=symbol)
            return float(ticker['result']['list'][0]['lastPrice']) # type: ignore
        return self.retry_api_call(call)
    
    def get_bid_ask_prices(self, symbol):
        def call():
            response = self.http_client.get_tickers(
                category="linear",
                symbol=symbol,
            )
            result = response['result']['list'][0] # type: ignore
            return float(result['bid1Price']), float(result['ask1Price'])
        return self.retry_api_call(call)
    
    def get_position_data(self, symbol):
        """Получает детали позиций."""
        def call():
            # Получаем список позиций
            raw_response = self.http_client.get_positions(category="linear", symbol=symbol)

            # Принудительно говорим анализатору, что это словарь
            response = cast(Dict[str, Any], raw_response)
            print(response)

            # Проверяем наличие ошибок
            if response["retCode"] != 0:
                raise Exception(f"Ошибка получения позиций: {response['retMsg']}")
            
            # Создаем переменнные для выходных значений
            buy_size = 0.0
            buy_unpnl = 0.0
            buy_price = 0.0
            sell_unpnl = 0.0
            sell_size = 0.0
            sell_price = 0.0

            # Проходим в цикле по списку позиций
            for position in response["result"]["list"]:
                if position["symbol"] == symbol:
                    if position["side"] == '':
                        # Позиции нет
                        continue

                    if position["side"] == "Buy":
                        buy_size =  float(position["size"])
                        buy_unpnl = float(position["unrealisedPnl"])
                        buy_price = float(position["avgPrice"])
                    elif position["side"] == "Sell":
                        sell_size =  float(position["size"])
                        sell_unpnl = float(position["unrealisedPnl"])
                        sell_price = float(position["avgPrice"])

            # Возврат значений
            return buy_size, sell_size, buy_unpnl, sell_unpnl, buy_price, sell_price
        
        result = self.retry_api_call(call)
        return result 

    def get_active_orders(self, symbol):
        """Получает список активных ордеров."""
        def call():
            # Получаем открытые ордера
            response: Any = self.http_client.get_open_orders(category="linear", symbol=symbol, limit=50)

            # Проверяем наличие ошибок
            if response["retCode"] != 0:
                raise Exception(f"Ошибка получения активных ордеров: {response['retMsg']}")
            
            # Формируем список активных ордеров
            active_orders = []
            for order in response["result"]["list"]:
                active_orders.append({
                    "order_id": order["orderId"],
                    "price": float(order["price"]),
                    "side": order["side"],
                    "qty": float(order["qty"]),
                    "orderType": order["orderType"],
                    "stopOrderType": order.get("stopOrderType", None)
                })

            # Возврат значений
            return active_orders
        
        # Вызов с повторными попытками
        result = self.retry_api_call(call)

        # Возврат значений
        return result 

    def get_total_realised_pnl(self, symbol):
        """Получает общий реализованный PNL."""
        def call():
            # Получаем закрытые PNL
            response: Any = self.http_client.get_closed_pnl(category="linear", symbol=symbol, limit=50)

            # Проверяем наличие ошибок
            if response["retCode"] != 0:
                raise Exception(f"Ошибка получения закрытого PNL: {response['retMsg']}")

            # Суммируем PNL
            total_pnl = 0.0
            for trade in response["result"]["list"]:
                total_pnl += float(trade["closedPnl"])

            # Возврат значений
            return total_pnl
        
        # Вызов с повторными попытками
        result = self.retry_api_call(call)

        # Возврат значений
        return result 

    def cancel_lim_order(self, symbol, order_id):
        """Отменяет указанный ордер бота напрямую через API Bybit с повторными попытками."""
        # Проверка параметров
        if not symbol or not order_id:
            self.logger.error(f"Некорректные параметры: symbol={symbol}, orderId={order_id}")
            return -1

        def call():
            try:
                response: Any = self.http_client.cancel_order(
                    category="linear",
                    symbol=symbol,
                    orderId=order_id
                )
                if "retCode" in response and response["retCode"] in (0, 110001):
                    return response["retCode"]
                return -1
            except InvalidRequestError as e:
                if e.status_code == 110001:  # Ордер не существует или уже отменён
                    return 110001
                self.logger.error(f"Ошибка в cancel_order: {e}", exc_info=True)
                raise  # Пробрасываем другие ошибки InvalidRequestError
            except Exception as e:
                self.logger.error(f"Ошибка в cancel_order: {e}", exc_info=True)
                raise  # Пробрасываем исключение в retry_api_call

        result = self.retry_api_call(call)
        return result
    
    def place_limit_order(self, symbol, side, mode, qty, price, orderLinkId=None):
        """Выставляет лимитный ордер с поддержкой orderLinkId."""
        # Выставляем ордер
        return self._place_limit_order(symbol, side, mode, qty, price, orderLinkId)
    
    def _place_limit_order(self, symbol, side, mode, qty_rounded, price, orderLinkId=None):
        """Выставляет лимитный ордер с поддержкой orderLinkId."""
        def call():
            if side == "Buy":
                if mode == "Open":
                    position_idx = 1
                elif mode == "Close":
                    position_idx = 2
            elif side == "Sell":
                if mode == "Open":
                    position_idx = 2
                elif mode == "Close":
                    position_idx = 1

            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": "Limit",
                "qty": f"{qty_rounded:g}",
                #"qty": str(qty_rounded),
                "price": str(price),
                "positionIdx": position_idx
            }
            if orderLinkId:
                params["orderLinkId"] = orderLinkId

            response: Any = self.http_client.place_order(**params)

            if response["retCode"] == 0:
                return {
                    "orderId": response["result"]["orderId"],
                    "side": side,
                    "position_idx": position_idx,
                    "qty": qty_rounded,
                    "price": price,
                    "orderLinkId": orderLinkId
                }
            else:
                self.logger.error(f"Не удалось создать ордер: {response['retMsg']}")
                return {
                    "error": response["retMsg"],
                    "side": side,
                    "position_idx": position_idx,
                    "qty": qty_rounded,
                    "price": price,
                    "orderLinkId": orderLinkId
                }

        result = self.retry_api_call(call)
        if result is None:
            self.logger.warning(f"Прекращаем пытаться выставить ордер {side}, так как позиция для закрытия отсутствует.")
            return None
        return result

    def place_market_order(self, symbol, side, position_idx, qty):  
        """Выставляет рыночный ордер."""
        # Выставляем ордер
        return self._place_market_order(symbol, side, position_idx, qty)
    
    def _place_market_order(self, symbol, side, position_idx, qty):
        """Выставляет рыночный ордер."""
        def call():
            response: Any = self.http_client.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty),
                positionIdx=position_idx
            )

            if response["retCode"] != 0:
                raise Exception(f"Не удалось выставить рыночный ордер: {response['retMsg']}")
        
            return response

        return self.retry_api_call(call)

    def round_up_to_step(self, qty_float, qty_step_float):
        """Округляет число вверх до ближайшего кратного шага."""
        if qty_step_float <= 0:
            return qty_float
        # Используем ceil для округления вверх по сетке шага
        return round(math.ceil(qty_float / qty_step_float) * qty_step_float, 8)
   
    def calculate_last_rsi(self, symbol=None, interval="15", limit=200):
        """Рассчитывает RSI как на TradingView с использованием Wilder's RMA."""
        close_prices = self.get_close_prices(symbol=symbol, interval=interval, limit=limit)
        if len(close_prices) < 15:
            raise Exception(f"Недостаточно данных для RSI: получено {len(close_prices)} свечей, требуется минимум 15")

        rsi_indicator = RSIIndicator(close=close_prices, window=14, fillna=False)
        rsi_series = rsi_indicator.rsi()
        last_rsi = rsi_series.iloc[-1]

        if pd.isna(last_rsi):
            raise Exception("RSI не рассчитан")

        #self.logger.debug(f"Рассчитан RSI({interval}): {last_rsi:.2f}, последние 5 цен: {close_prices.tail(5).tolist()}")
        return last_rsi
    
    def calc_bb(self, symbol=None, window=20, window_dev=2, timeframe="240", limit=200):
        """Рассчитывает последние значения Bollinger Bands."""
        close_prices = self.get_close_prices(symbol=symbol, interval=timeframe, limit=limit)
        if not self._is_valid_price_data(close_prices, window):
            return None, None, None
        bb_values = self._compute_bollinger_bands(close_prices, window, window_dev)
        return self._extract_last_bb_values(bb_values)

    def _is_valid_price_data(self, close_prices, window):
        """Проверяет, достаточно ли данных для расчёта Bollinger Bands."""
        if close_prices.empty or len(close_prices) < window:
            self.logger.warning(f"Недостаточно данных для Bollinger Bands: получено {len(close_prices)}, нужно {window}")
            return False
        return True

    def _compute_bollinger_bands(self, close_prices, window, window_dev):
        """Вычисляет Bollinger Bands с заданными параметрами."""
        bb_indicator = BollingerBands(close=close_prices, window=window, window_dev=window_dev)
        bb_high = bb_indicator.bollinger_hband()
        bb_mid = bb_indicator.bollinger_mavg()
        bb_low = bb_indicator.bollinger_lband()
        return bb_high, bb_mid, bb_low

    def _extract_last_bb_values(self, bb_values):
        """Извлекает последние значения верхней, средней и нижней полос."""
        bb_high, bb_mid, bb_low = bb_values
        last_high = float(bb_high.iloc[-1]) if not pd.isna(bb_high.iloc[-1]) else None
        last_mid = float(bb_mid.iloc[-1]) if not pd.isna(bb_mid.iloc[-1]) else None
        last_low = float(bb_low.iloc[-1]) if not pd.isna(bb_low.iloc[-1]) else None
        return last_high, last_mid, last_low    
    
    def get_kline_data(self, symbol, interval, limit=100):
    # Функция для получения исторических данных (K-line)
        def call():
            # Только запрос и получение сырого списка
            response = self.http_client.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response['retCode'] != 0:
                self.logger.error(f"Ошибка Bybit: {response['retMsg']}")
                return None
            
            # Возвращаем просто список списков. Никаких DataFrame здесь!
            return response['result']['list']

        return self.retry_api_call(call)
    
    def log(self, message):
        self.logger.info(message)
        self.telegram.send_telegram_message(message)

    def get_limit_orders(self, symbol, side, category="linear"):
        """
        Получает список лимитных ордеров.
        """
        def call():
            resp  = self.http_client.get_open_orders(category=category, symbol=symbol, limit=50)

            # 1. Распаковка: если это кортеж, берем первый элемент
            if isinstance(resp, tuple):
                response = resp[0]
            else:
                response = resp

            # ЗАЩИТА: Проверяем, что response не None и это словарь
            if response is None:
                raise Exception("API вернул пустой ответ")
                   
            # 2. Проверяем наличие ошибки в ответе
            if response.get("retCode") != 0:
                raise Exception(f"Ошибка API: {response.get('retMsg')}")

            # 3. Oтфильтровываем лимитные ордера
            orders = response.get("result", {}).get("list", [])
            limit_orders = [o for o in orders if o.get("orderType") == "Limit"]

            # 4. Дополнительная фильтрация по символу и стороне, если указаны
            limit_orders = [o for o in limit_orders if o.get("side") == side]
            
            # 5. Возвращаем список лимитных ордеров
            return limit_orders
        
        # Вызов с повторными попытками
        result = self.retry_api_call(call)

        # Возврат значений
        return result 

    def _handle_110001(self, symbol, orderId, new_price, new_qty):
        """
        Обрабатывает случай, когда ордер больше недоступен (ошибка 110001).
        Пытается получить детали исполнения или создает расчетные значения.
        """
        self.logger.warning(f"⚠️ [110001] {symbol}: Ордер {orderId} недоступен. Считаем исполненным.")

        details = self.get_order_execution_details(symbol, orderId)
        if details:
            # Мы говорим боту: "Все, этот ордер закрыт, вот по какой цене мы вошли"
            self.logger.info(f"{symbol}: Ордер {orderId} полностью закрыт общим объемом {details['totalQty']}")
            return {"status": "ORDER_FILLED", "details": details}
        
        # Если деталей в истории нет, создаем их сами!
        # Берем new_price, которую мы ПЫТАЛИСЬ поставить.
        self.logger.info(f"Используем расчетную цену {new_price} для ордера {orderId}")
        return {
            "status": "ORDER_FILLED", 
            "details": {
                "avgPrice": new_price, 
                "totalQty": new_qty, 
                "execFee": 0, # Комиссию бот переживет
                "is_estimated": True # Пометка, что цена расчетная
            }
        }

    def _calc_sl(self, side, new_price, sl_ratio):
        """
        Вычисляет цену стоп-лосса на основе направления, цены и коэффициента.
        """
        if sl_ratio is not None:
            if side == "Buy":
                sl_price = new_price * (1 - sl_ratio)
            elif side == "Sell":
                sl_price = new_price * (1 + sl_ratio)
            else:
                sl_price = None
        else:
            sl_price = None
        return sl_price

    def change_order_price(self, symbol, side, orderId, new_price, new_qty=None, sl_ratio=None):
        """
        Изменяет цену существующего ордера.
        """
        def call():
            params = {
                "category": "linear",
                "symbol": symbol,
                "orderId": orderId,
                "price": str(new_price),
                "qty": str(new_qty)
            }

            # --- вычисляем стоп-лосс ---
            sl_price = self._calc_sl(side, new_price, sl_ratio)
            if sl_price:
                params["stopLoss"] = str(sl_price)
                params["slTriggerBy"] = "LastPrice"
                params["tpslMode"] = "Partial"  # 👈 стоп-лосс только для этого ордера

            try:
                # Если здесь успех, возвращаем ответ Bybit (retCode: 0)
                self.http_client.amend_order(**params)
                return {"status": "ORDER_CHANGED"}
            except Exception as e:
                err_msg = str(e)
                
                # Если "Too late to replace" (110001)
                if "110001" in err_msg:
                    return self._handle_110001(symbol, orderId, new_price, new_qty)
                
                raise e

        result = self.retry_api_call(call)
        return result
    
    def exist_order(self, symbol=None, side= None, order_id=None):
        # Получаем список лим ордеров
        existing_orders = self.get_limit_orders(symbol=symbol, side=side)

        if existing_orders is None:
            raise Exception("Не удалось получить список существующих ордеров.")

        # Ищем наш ордер по ID
        my_order = next((o for o in existing_orders if o['orderId'] == order_id), None)

        # Если ордер не найден
        if not my_order:
            self.logger.debug(f"✅ Ордер с ID {order_id} больше не активен.")
            return False
        
        return True

    def get_symbol_info(self, symbol):
        def call():
            return self.http_client.get_instruments_info(category="linear", symbol=symbol)
        
        return self.retry_api_call(call)
    
    def _place_trigger_order(self, symbol, side, trigger_dir, pos_idx, trigger_price, qty_valid):
        def call():
            response = self.http_client.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty_valid),
                triggerPrice=str(trigger_price),
                triggerDirection=trigger_dir,
                triggerBy="LastPrice",
                reduceOnly=True,
                positionIdx=pos_idx
            )

            return response
        
        return self.retry_api_call(call)

    def amend_order(self, symbol, orderId, new_price):
        """
        Изменяет цену существующего ордера.
        """
        def call():
            params = {
                "category": "linear",
                "symbol": symbol,
                "orderId": orderId,
                "triggerPrice": str(new_price),
            }

            return self.http_client.amend_order(**params)

        return self.retry_api_call(call)
    
    def get_price_step(self, symbol):
        response = self.get_symbol_info(symbol)

        if response is None:
            raise Exception(f"Не удалось получить информацию о символе: {symbol}.")
        
        instrument_info = response['result']['list'][0]
        price_step = float(instrument_info['priceFilter']['tickSize'])
        return  price_step

    def round_price_to_step(self, symbol: str, price: float) -> float:
        # Получаем price_step
        price_step = self.get_price_step(symbol)
        return round_to_step(price, price_step)

    def get_executed_order_info(self, order_id):
        """
        Получить информацию о исполненном ордере по ID.
        """
        def call():
            # ищем в истории ордеров
            params = {
                "category": "linear",
                "orderId": order_id,
            }
            response: Any = self.http_client.get_order_history(**params)

            # Проверяем успешность запроса
            if response["retCode"] != 0:
                raise Exception(f"Ошибка получения ордера: {response['retMsg']}")
            
            # Пробуем получить ордер 
            orders = response.get("result", {}).get("list", [])
            if not orders:
                self.logger.debug(f"Ордер {order_id} не найден")
                return None
            
            return orders[0]
        
        return self.retry_api_call(call)    
    
    def get_order_execution_details(self, symbol, order_id):
        """
        Получает детали реального исполнения ордера (цена, объем, комиссия).
        """
        def call():
            params = {
                "category": "linear",
                "symbol": symbol,
                "orderId": order_id,
            }
            # Обращаемся именно к истории сделок
            response: Any = self.http_client.get_executions(**params)

            # Проверяем успешность запроса
            if response["retCode"] != 0:
                raise Exception(f"Ошибка получения сделок: {response['retMsg']}")
            
            # Извлекаем список сделок по ордеру
            executions = response.get("result", {}).get("list", [])
            if not executions:
                return None
            
            # Если ордер исполнился частями, суммируем объем и считаем среднюю цену
            total_qty = sum(float(exec['execQty']) for exec in executions)

            # Средневзвешенная цена исполнения
            avg_price = sum(float(exec['execPrice']) * float(exec['execQty']) for exec in executions) / total_qty
            
            # Возвращаем детали исполнения
            return {
                "avgPrice": avg_price,
                "totalQty": total_qty,
                "execFee": sum(float(exec['execFee']) for exec in executions),
                "lastExecTime": executions[0]['execTime']
            }
        
        # Вызов с повторными попытками
        return self.retry_api_call(call)
    
    def get_order_status(self, symbol, order_id):
        """
        Получает текущее состояние ордера от Bybit.
        """
        def call():
            params = {
                "category": "linear",
                "symbol": symbol,
                "orderId": order_id,
            }

            response: Any = self.http_client.get_open_orders(**params)

            if response["retCode"] != 0:
                raise Exception(
                    f"Ошибка получения статуса ордера: {response['retMsg']}"
                )

            orders = response.get("result", {}).get("list", [])

            if not orders:
                return None

            return orders[0]

        return self.retry_api_call(call)    

    def get_total_equity(self):
        """Возвращает общую стоимость аккаунта (Equity) в USDT."""
        def call():
            # Запрашиваем баланс без фильтра по конкретной монете, 
            # чтобы получить общую оценку аккаунта (Equity)
            balances: Any = self.http_client.get_wallet_balance(accountType="UNIFIED")

            # Возвращаем общую стоимость аккаунта
            return float(balances['result']['list'][0]['totalEquity'])
        
        # Вызов с повторными попытками
        return self.retry_api_call(call)

    def get_kline_data_old(self, symbol, interval, limit=100):
     # Функция для получения исторических данных (K-line)
        def call():
            response = self.http_client.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,  # Интервал в минутах (15 минут в данном случае)
                limit=limit        # Количество свечей
            )
            
            # Проверяем успешность запроса
            if response['retCode'] != 0:
                self.logger.error(f"Ошибка API: {response['retMsg']}")
                return None
            
            # Извлекаем данные
            klines = response['result']['list']
            
            # Форматируем в DataFrame
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df = df.astype(float)
            df['start_ms'] = df['timestamp'].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['start_str'] = df['timestamp']
            df = df[::-1]  # Переворачиваем, чтобы данные шли от старых к новым
            return df
    
        return self.retry_api_call(call)
    
    def get_close_prices(self, symbol=None, interval="15", limit=100):
        """Получает цены закрытия для расчёта индикаторов."""
        # Получаем данные K-line
        df = self.get_kline_data_old(symbol=symbol, interval=interval, limit=limit)

        # Проверяем, что данные получены
        if df is None:
            raise Exception("Не удалось получить данные K-line для расчёта цен закрытия.")  
        
        # Возвращаем серию цен закрытия
        return df["close"]

    def get_all_active_positions(self):
        """Получает список всех открытых позиций (размер > 0) по всем символам."""
        def call():
            # Запрашиваем все позиции по линейным контрактам (USDT)
            response = self.http_client.get_positions(
                category="linear",
                settleCoin="USDT"
            )
            
            if response.get("retCode") != 0:
                raise Exception(f"Ошибка получения всех позиций: {response.get('retMsg')}")
            
            raw_list = response.get('result', {}).get('list', [])
            active_positions = []

            for p in raw_list:
                qty = float(p.get('size', 0))
                # Нам нужны только реально открытые позиции
                if qty > 0:
                    active_positions.append({
                        "symbol": p['symbol'],
                        "size": qty,
                        "entry_price": float(p['avgPrice']),
                        "side": p['side'],
                        "unrealisedPnl": float(p['unrealisedPnl']),
                        "positionIdx": p['positionIdx']
                    })
            
            return active_positions

        return self.retry_api_call(call)

    def get_all_active_orders(self):
        """
        Получает абсолютно ВСЕ активные ордера (USDT) по всем символам.
        Использует пагинацию через nextPageCursor.
        """
        def call():
            all_orders = []
            cursor = None
            
            while True:
                # Для получения всех ордеров в linear нужно указать settleCoin
                params = {
                    "category": "linear",
                    "settleCoin": "USDT",
                    "limit": 50,
                    "openOnly": 0  # Только открытые ордера
                }
                if cursor:
                    params["cursor"] = cursor
                
                response = self.http_client.get_open_orders(**params)
                
                if response.get("retCode") != 0:
                    raise Exception(f"Ошибка API при получении всех ордеров: {response.get('retMsg')}")
                
                result = response.get("result", {})
                orders_list = result.get("list", [])
                
                for o in orders_list:
                    all_orders.append({
                        "order_id": o["orderId"],
                        "symbol": o["symbol"],
                        "price": float(o["price"]) if o["price"] else 0.0,
                        "side": o["side"],
                        "qty": float(o["qty"]),
                        "orderType": o["orderType"],
                        "orderStatus": o["orderStatus"],
                        "stopOrderType": o.get("stopOrderType")
                    })
                
                # Переход к следующей странице
                cursor = result.get("nextPageCursor")
                if not cursor or cursor == "":
                    break
            
            return all_orders
        
        return self.retry_api_call(call)

    def fetch_order_history_page(self, start_time, end_time, cursor=None, limit=50):
        """Низкоуровневый запрос одной страницы истории."""
        return self.http_client.get_order_history(
            category="linear",
            startTime=start_time,
            endTime=end_time,
            limit=limit,
            cursor=cursor,
            settleCoin="USDT",
        )

    def _get_order_history(self, days_back=2):
        """Внутренний сборщик всей истории за период (с окнами и курсором)."""
        all_orders = []
        ms_in_day = 86400000
        window_size = 1 * ms_in_day
        now = int(time.time() * 1000)
        current_start = now - (days_back * ms_in_day)
        print(f"current_start={current_start}")

        while current_start < now:
            current_end = min(current_start + window_size, now)
            print(f"current_end={current_end}")
            cursor = None
            
            while True:
                print("Читаем страницу...")
                response = self.fetch_order_history_page(current_start, current_end, cursor)
                print(f"Длина страницы={len(response["result"]["list"])}")
                
                # Если Bybit вернул ошибку, кидаем исключение для срабатывания retry
                if not response or response.get('retCode') != 0:
                    err_msg = response.get('retMsg') if response else "Empty response"
                    raise Exception(f"Bybit API Error in get_order_history: {err_msg}")
                
                result = response.get('result', {})
                orders = result.get('list', [])
                all_orders.extend(orders)
                
                cursor = result.get('nextPageCursor')
                print(f"cursor={cursor}")
                if not cursor:
                    break
            
            current_start = current_end + 1
        
        return all_orders

    def get_order_history(self, days_back=2):
        """Получает историю ордеров за указанный период (по умолчанию 2 дня)."""
        def call():
            return self._get_order_history(days_back=days_back)
        
        return self.retry_api_call(call)
    
    def fetch_trade_history_page(self, start_time, end_time, cursor=None, limit=100):
        """Низкоуровневый запрос одной страницы истории сделок (Executions)."""
        return self.http_client.get_executions(
            category="linear",
            startTime=start_time,
            endTime=end_time,
            limit=limit,
            cursor=cursor
        )

    def _get_trade_history(self, days_back=2):
        """Внутренний сборщик всей истории сделок за период (аналог для Trade History)."""
        all_trades = []
        ms_in_day = 86400000
        window_size = 1 * ms_in_day # Окна по 1 дню для стабильности
        now = int(time.time() * 1000)
        current_start = now - (days_back * ms_in_day)

        print(f"--- Сбор Trade History (Executions) за {days_back} дн. ---")
        
        while current_start < now:
            current_end = min(current_start + window_size, now)
            cursor = None
            
            while True:
                response = self.fetch_trade_history_page(current_start, current_end, cursor)
                
                if not response or response.get('retCode') != 0:
                    err_msg = response.get('retMsg') if response else "Empty response"
                    raise Exception(f"Bybit API Error in get_trade_history: {err_msg}")
                
                result = response.get('result', {})
                trades = result.get('list', [])
                all_trades.extend(trades)
                
                print(f"Загружено сделок: {len(trades)} | Окно: {current_start} -> {current_end}")
                
                cursor = result.get('nextPageCursor')
                if not cursor:
                    break
            
            current_start = current_end + 1
        
        return all_trades

    def get_trade_history(self, days_back=2):
        """Публичный метод для получения истории сделок с ретраями."""
        def call():
            return self._get_trade_history(days_back=days_back)
        
        return self.retry_api_call(call)
    
    def get_lot_size_params(self, symbol):
        response = self.get_symbol_info(symbol)

        if response is None or response.get("retCode") != 0:
            raise Exception(f"Ошибка получения symbol info для {symbol}")

        filters = response['result']['list'][0]['lotSizeFilter']

        return {
            "min_qty": float(filters['minOrderQty']),
            "step_size": float(filters['qtyStep'])
        }    
    
    def get_fee_rates(self, symbol):
        def call():
            if self.demo:
                return {
                    "taker": 0.00055,
                    "maker": 0.00020,
                }

            response = self.http_client.get_fee_rates(
                category="linear",
                symbol=symbol
            )

            if response["retCode"] != 0:
                raise Exception(f"Fee API error: {response['retMsg']}")

            data = response["result"]["list"]

            if not data:
                raise Exception("Fee rate not returned")

            return {
                "taker": float(data[0]["takerFeeRate"]),
                "maker": float(data[0]["makerFeeRate"])
            }

        return self.retry_api_call(call)