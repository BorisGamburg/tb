import time


class ChaseOrderMng:
    def __init__(self, proxy_driver, price_service, logger):
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger

    def chase(self, symbol, side, order_id, poll_interval=1):
        while True:
            # Получаем данные ордера
            order_data = self.get_order_status(
                symbol=symbol,
                order_id=order_id,
            )
            if not order_data:
                raise RuntimeError(
                    f"Order not found | symbol={symbol} | order_id={order_id}"
                )

            # Если ордер исполнен, выходим 
            if order_data["orderStatus"] == "Filled":
                return order_data

            # Получаем цену куда перемещать ордер 
            chase_price = self.price_service.get_orderbook_side_price(
                symbol=symbol,
                side=side,
            )

            # Получаем текущую цену ордера
            cur_order_price = float(order_data["price"])

            # Сравниваем текущую цену ордера с ценой для перемещения
            # Если они отличаются, перемещаем ордер на новую цену
            if cur_order_price != chase_price:
                self.proxy_driver.execute(
                    "change_order_price",
                    symbol=symbol,
                    side=side,
                    orderId=order_id,
                    new_price=chase_price,
                )

                self.logger.info(
                    f"[CHASE] order moved | side={side} "
                    f"| order_id={order_id} | price={chase_price}"
                )

            time.sleep(poll_interval)

    def get_order_status(self, symbol, order_id):
        return self.proxy_driver.execute(
            "get_order_status",
            symbol=symbol,
            order_id=order_id,
        )