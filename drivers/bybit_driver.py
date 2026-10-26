from pybit.unified_trading import HTTP
from pybit.exceptions import InvalidRequestError
import time
from typing import Any
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

        for attempt in range(1, self.max_attempts + 1):
            try:
                # Прямой вызов функции
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
            params["tpslMode"] = "Partial"

        self.http_client.amend_order(**params)
        return {"status": "ORDER_CHANGED"}

    def get_symbol_info(self, symbol):
        def call():
            return self.http_client.get_instruments_info(category="linear", symbol=symbol)
        
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
                "limit": 100,
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
                "lastExecTime": max(
                    int(exec["execTime"])
                    for exec in executions
                ),
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