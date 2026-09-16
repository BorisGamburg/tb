import time
import logging

from managers.scale_pool_mng import ScalePoolMng
from action_processor.execution.limit_order_result import LimitOrderResult, LimitOrderStatus
from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver
from action_processor.bootstrap import AppContext


class OpenActiveLimitMng:
    proxy_driver: ProxyDriver
    price_service: MarketService
    logger: logging.Logger

    def __init__(
        self,
        app_ctx: AppContext,
    ):
        self.app_ctx = app_ctx
        self.proxy_driver = app_ctx.proxy_driver
        self.price_service = app_ctx.price_service
        self.logger = app_ctx.logger

        self.scale_pool_mng = ScalePoolMng(
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            logger=self.logger,
        )

    def get_order_status(self, symbol: str, order_id: str):
        """
        Получение текущего состояния ордера.
        """
        return self.proxy_driver.execute(
            "get_order_status",
            symbol=symbol,
            order_id=order_id,
        )

    def _wait_limit_order(
        self,
        symbol,
        timeout,
        poll_interval,
        order_id,
    ):
        start_time = time.monotonic()

        while True:
            order_data = self.get_order_status(
                symbol=symbol,
                order_id=order_id,
            )

            if not order_data:
                raise RuntimeError(
                    f"Order not found | symbol={symbol} | order_id={order_id}"
                )

            if order_data["orderStatus"] == "Filled":
                return order_data

            if time.monotonic() - start_time >= timeout:
                return order_data

            time.sleep(poll_interval)    

    def move_order_from_pool(self, symbol, side, qty, sl_ratio=None):
        # Получаем цену для быстрого исполнения лимитного ордера 
        fast_execution_limit_price = self.price_service.get_active_price(
            symbol=symbol,
            side=side,
        )

        # Перемещаем ордер из пула на новую цену и количество
        return self.scale_pool_mng.move_order_from_pool(
            symbol=symbol,
            side=side,
            new_price=fast_execution_limit_price,
            new_qty=qty,
            sl_ratio=sl_ratio,
        )          

    def wait_limit_order(
        self,
        symbol,
        side,
        qty,
        timeout=10,
        poll_interval=1,
    ):
        # Перемещаем ордер из пула на текущую цену и меняем количество
        move_result = self.move_order_from_pool(
            symbol=symbol,
            side=side,
            qty=qty,
        )

        # Получаем ID и цену перемещенного ордера
        order_id = move_result["orderId"]
        order_price = move_result["newPrice"]

        # Лог
        self.logger.info(
            f"[LIMIT] order placed | side={side} | qty={qty} | price={order_price}"
        )

        # Ждем исполнения ордера или таймаута
        order_data = self._wait_limit_order(
            symbol=symbol,
            timeout=timeout,
            poll_interval=poll_interval,
            order_id=order_id,
        )

        # Проверяем статус ордера и обрабатываем его
        return self._process_limit_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_id=order_id,
            order_price=order_price,
            order_data=order_data,
        )

    def _process_limit_order(
        self,
        symbol,
        side,
        qty,
        order_id,
        order_price,
        order_data,
    ):
        status = order_data["orderStatus"]

        if status == "New":
            return self._handle_unfilled_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_id=order_id,
                order_price=order_price,
            )

        if status == "PartiallyFilled":
            return self._handle_partial_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_id=order_id,
                order_price=order_price,
                order_data=order_data,
            )

        if status == "Filled":
            return self._handle_filled_order(
                side=side,
                order_id=order_id,
                order_price=order_price,
                order_data=order_data,
            )

        raise RuntimeError(
            f"Unexpected order status | symbol={symbol} "
            f"| order_id={order_id} | status={status}"
        )

    def _handle_unfilled_order(
        self,
        symbol,
        side,
        qty,
        order_id,
        order_price,
    ):
        self.scale_pool_mng.move_order_to_pool(
            symbol=symbol,
            side=side,
            order_id=order_id,
            new_qty=qty,
        )

        self.logger.info(
            f"[LIMIT] order not filled, returned to pool | side={side} "
            f"| order_id={order_id} | price={order_price}"
        )
        
        return LimitOrderResult(
            order_id=order_id,
            avg_price=0.0,
            filled_qty=0.0,
            fee=0.0,
            filled=False,
            status=LimitOrderStatus.NOT_FILLED,
        )

    def _handle_partial_order(
        self,
        symbol,
        side,
        qty,
        order_id,
        order_price,
        order_data,
    ):
        filled_qty = float(order_data["cumExecQty"])
        avg_price = float(order_data["avgPrice"])
        self._check_execution_price(
            side=side,
            order_price=order_price,
            avg_price=avg_price,
        )        
        fee = float(order_data["cumFeeDetail"]["USDT"])
        remaining_qty = qty - filled_qty

        self.scale_pool_mng.move_order_to_pool(
            symbol=symbol,
            side=side,
            order_id=order_id,
            new_qty=remaining_qty,
        )

        self.logger.info(
            f"[LIMIT] order partially filled | order_id={order_id} "
            f"| filled_qty={filled_qty} | remaining_qty={remaining_qty}"
        )

        return LimitOrderResult(
            order_id=order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            fee=fee,
            filled=True,
            status=LimitOrderStatus.PARTIALLY_FILLED,
        )


    def _handle_filled_order(
        self,
        side,
        order_id,
        order_price,
        order_data,
    ):
        filled_qty = float(order_data["cumExecQty"])
        avg_price = float(order_data["avgPrice"])
        self._check_execution_price(
            side=side,
            order_price=order_price,
            avg_price=avg_price,
        )        
        fee = float(order_data["cumFeeDetail"]["USDT"])

        return LimitOrderResult(
            order_id=order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            fee=fee,
            filled=True,
            status=LimitOrderStatus.FILLED,
        )    

    def _check_execution_price(
        self,
        side,
        order_price,
        avg_price,
    ):
        if side == "Buy" and avg_price > order_price:
            message = (
                f"[LIMIT] anomalous execution price | side={side} "
                f"| order_price={order_price} | avg_price={avg_price}"
            )
            self.logger.error(message)
            self.app_ctx.telegram.send_telegram_message(message)

        if side == "Sell" and avg_price < order_price:
            message = (
                f"[LIMIT] anomalous execution price | side={side} "
                f"| order_price={order_price} | avg_price={avg_price}"
            )
            self.logger.error(message)
            self.app_ctx.telegram.send_telegram_message(message)    