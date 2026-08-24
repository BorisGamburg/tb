import time
from proxy_server.proxy_driver import ProxyDriver
from managers.chase_pool_mng import ChasePoolMng
from action_processor.execution.execution_waiter import ExecutionWaiter


class ChaseMng:
    def __init__(self, proxy_driver: ProxyDriver, price_service, logger):
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger
        self.execution_waiter = ExecutionWaiter(proxy_driver)
        self.chase_pool_mng = ChasePoolMng(
            proxy_driver=proxy_driver,
            price_service=price_service,
            logger=logger,
        )

    def wait_chase_order(
        self,
        symbol,
        side,
        qty,
        sl_ratio=None,
        poll_interval=1,
    ):
        my_order_id: str | None = None
        my_order_price: float | None = None

        # Основной цикл, который работает, пока ордер активен
        while True:
            if my_order_id is not None:
                # Ордер выставлен. Проверяем исполнен ли он
                res = self.check_chase_order(
                    symbol=symbol,
                    side=side,
                    orderId=my_order_id,
                    qty=qty,
                    old_price=my_order_price
                )
                if res.get("retCode") == "ORDER_NOT_EXIST":
                    return self.get_order_details(symbol, my_order_id)

                elif res.get("retCode") == "ORDER_MOVED":
                    my_order_price = res.get("newPrice")
                    # Идем на ожидание
                    pass

                elif res.get("retCode") == "ORDER_NOT_MOVED":
                    # Идем на ожидание
                    pass

            else:
                # Ордер еще не выставлен. Выставляем ордер из пула
                res = self.chase_pool_mng.move_lim_order_from_pool(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    sl_ratio=sl_ratio,
                )
                my_order_id = res.get("orderId")
                my_order_price = res.get("newPrice")

                self.logger.info(
                    f"[CHASE] order placed | side={side} | qty={qty} | price={my_order_price}"
                )

            # Ожидание перед следующей проверкой
            time.sleep(poll_interval)

    def get_order_details(self, symbol, my_order_id):
        details = self.execution_waiter.wait(
            symbol=symbol,
            order_id=my_order_id,
            retries=30,
            delay=1,
        )

        self.logger.info(
            f"[CHASE] filled | symbol={symbol} | order_id={my_order_id} "
        f"| qty={details.qty} | price={details.avg_price}"
        )

        return "OK", my_order_id, details.avg_price, details.qty, details.fee

    def check_chase_order(
        self,
        symbol,
        side,
        qty,
        orderId,
        old_price,
    ):
        chase_price = self.price_service.get_chase_price(
            symbol=symbol,
            side=side,
        )

        # Сместилась ли цена?
        if old_price != chase_price:
            # Цена сместилась, перемещаем my_order_id на новую цену
            res = self.proxy_driver.execute("change_order_price",
                symbol=symbol,
                side=side,
                orderId=orderId,
                new_price=chase_price,
                new_qty=qty
            )

            if res is None:
                raise Exception(f"API вернул None")

            if res.get("status") == "ORDER_FILLED":
                return {"retCode": "ORDER_NOT_EXIST"}
            elif res.get("status") == "ORDER_CHANGED":
                return {"retCode": "ORDER_MOVED", "newPrice": chase_price}
            else:
                raise Exception(f"❌ Странная ошибка при перемещении ордера {orderId}. Ответ: {res}")
        else:
            # Цена не сместилась, ордер не двигаем
            return {"retCode": "ORDER_NOT_MOVED"}
        
