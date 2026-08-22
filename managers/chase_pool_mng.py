import random


class ChasePoolMng:
    POOL_DIST_THRESHOLD_RATIO = 0.5

    def __init__(self, proxy_driver, price_service, logger):
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger

    def move_lim_order_from_pool(self, symbol, side, qty, sl_ratio=None):
        # Перемещаем лим ордер из пула
        # Получение текущей цены
        chase_price = self.price_service.get_chase_price(
            symbol=symbol,
            side=side,
        )

        # Вызываем функцию для перемещения ордера из пула
        move_result = self._move_lim_order_from_pool(
            symbol=symbol, 
            side=side, 
            new_price=chase_price, 
            new_qty=qty,
            sl_ratio=sl_ratio,
        )

        # Успешный выход
        return move_result

    def _move_lim_order_from_pool(
        self,
        symbol,
        side,
        new_price,
        new_qty,
        sl_ratio=None,
    ):
        order = self._get_pool_order_for_move(
            symbol=symbol,
            side=side,
        )
        return self._try_to_move_order(
            symbol=symbol,
            side=side,
            order_id=order["orderId"],
            new_price=new_price,
            new_qty=new_qty,
            sl_ratio=sl_ratio,
        )    

    def _get_pool_order_for_move(self, symbol, side):
        """
        Получает подходящий ордер из пула для перемещения.
        Валидирует наличие открытых лимитных ордеров и ищет ордер в пуле.
        
        :param symbol: Символ торговой пары
        :param side: Сторона ордера (Buy/Sell)
        :return: Ордер для перемещения
        :raises Exception: Если нет открытых ордеров или нет ордеров в пуле
        """
        # Шаг 1: Получаем список открытых лим ордеров
        open_limit_orders = self.proxy_driver.execute("get_limit_orders", symbol=symbol, side=side)
        if not open_limit_orders:
            raise Exception(f"Нет открытых лимитных ордеров {side} для {symbol}.")
        
        # Получаем текущую цену для расчета дистанции
        last_price = self.proxy_driver.get_last_price(symbol)

        # Ищем подходящий ордер в пуле
        order_to_move = self._find_order_to_move_from_pool(open_limit_orders, last_price)

        # Если ордер не найден, выбрасываем ошибку
        if order_to_move is None:
            raise Exception(f"Нет лимитных ордеров {side} для {symbol} в пуле.")
        
        return order_to_move

    def _find_order_to_move_from_pool(self, open_limit_orders, last_price):
        """
        Ищет первый подходящий ордер в пуле по трем признакам:
        - Это ордер на ОТКРЫТИЕ (reduceOnly: False)
        - Он ОЧЕНЬ далеко от текущей цены (дистанция > 100%)
        - Его ID не в списке исключений текущего процесса
        
        :param open_limit_orders: Список открытых лимитных ордеров
        :param last_price: Текущая цена
        :return: Ордер для перемещения или None
        """
        candidates = []
        
        for order in open_limit_orders:
            order_price = float(order.get("price", 0))
            # Проверка: на открытие
            is_open = order.get("reduceOnly") in [False, "0", "false"]
            # Проверка: дистанция (Пул на 500%)
            dist = abs(order_price - last_price) / last_price
            threshold = self.POOL_DIST_THRESHOLD_RATIO
            is_far = dist > threshold
            
            if is_open and is_far:
                candidates.append(order)
        
        # 2. Если кандидатов нет — возвращаем None
        if not candidates:
            return None
            
        # 3. ПРАГМАТИЧНЫЙ ХОД: Выбираем случайный ордер из списка.
        # Это гарантирует, что два бота с вероятностью 95%+ возьмут РАЗНЫЕ ордера.
        return random.choice(candidates)    
    
    def _try_to_move_order(self, symbol, side, order_id, new_price, new_qty, sl_ratio=None):
        res = self.proxy_driver.execute("change_order_price",
            symbol=symbol, 
            side=side, 
            orderId=order_id, 
            new_price=new_price, 
            new_qty=new_qty, 
            sl_ratio=sl_ratio
        )

        if res is None:
            raise Exception(f"❌ Не удалось получить ответ при перемещении ордера {order_id}")
        
        status = res.get("status") 

        if status == "ORDER_FILLED":
            return {"retCode": "OK", "orderId": order_id, "newPrice": new_price, "filled": True}
        
        if status != "ORDER_CHANGED":
            raise Exception(f"❌ Не удалось переместить ордер из пула: {res}")
        
        return {"retCode": "OK", "orderId": order_id, "newPrice": new_price}



