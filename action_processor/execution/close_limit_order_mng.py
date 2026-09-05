import time

from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver
from action_processor.execution.limit_order_result import (
    LimitOrderResult,
    LimitOrderStatus,
)


class CloseLimitOrderMng:
    def __init__(
        self,
        proxy_driver: ProxyDriver,
        market_service: MarketService,
        logger,
    ):
        self.proxy_driver = proxy_driver
        self.market_service = market_service
        self.logger = logger

    def get_order_status(self, symbol: str, order_id: str):
        return self.proxy_driver.execute(
            "get_order_status",
            symbol=symbol,
            order_id=order_id,
        )

    def _place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
    ):
        return self.proxy_driver.execute(
            "place_limit_order",
            symbol=symbol,
            side=side,
            mode="Close",
            qty=qty,
            price=price,
        )

    def _cancel_order(
        self,
        symbol: str,
        order_id: str,
    ):
        return self.proxy_driver.execute(
            "cancel_lim_order",
            symbol=symbol,
            order_id=order_id,
        )

    def _wait_limit_order(
        self,
        symbol: str,
        order_id: str,
        timeout: float,
        poll_interval: float,
    ):
        start_time = time.monotonic()

        while True:
            order_data = self.get_order_status(
                symbol=symbol,
                order_id=order_id,
            )

            if not order_data:
                raise RuntimeError(
                    f"Order not found | "
                    f"symbol={symbol} | "
                    f"order_id={order_id}"
                )

            status = order_data["orderStatus"]

            if status == "Filled":
                return order_data

            if time.monotonic() - start_time >= timeout:
                return order_data

            time.sleep(poll_interval)

    def wait_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        timeout: float = 10,
        poll_interval: float = 1,
    ) -> LimitOrderResult:
        # Размещаем ордер на закрытие позиции
        order_id = self._place_close_order(
            symbol=symbol,
            side=side,
            qty=qty,
        )

        # Ждем исполнения ордера или таймаута
        order_data = self._wait_limit_order(
            symbol=symbol,
            order_id=order_id,
            timeout=timeout,
            poll_interval=poll_interval,
        )

        # Обрабатываем результат 
        return self._process_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_id=order_id,
            order_data=order_data,
        )    

    def _place_close_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> str:
        # Получаем цену для пассивного исполнения лимитного ордера 
        price = self.market_service.get_limit_price(
            symbol=symbol,
            side=side,
        )

        # Размещаем лимитный ордер на закрытие позиции
        res = self._place_limit_order(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
        )

        # Проверяем результат размещения ордера
        if not res or "orderId" not in res:
            raise RuntimeError(
                f"Close limit order failed | "
                f"symbol={symbol} | "
                f"side={side} | "
                f"qty={qty} | "
                f"price={price} | "
                f"response={res}"
            )

        # Получаем ID размещенного ордера
        order_id = res["orderId"]

        # Лог
        self.logger.info(
            f"[CLOSE LIMIT] order placed | "
            f"side={side} | "
            f"qty={qty} | "
            f"price={price} | "
            f"order_id={order_id}"
        )

        # Возвращаем ID размещенного ордера
        return order_id    

    def _process_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_id: str,
        order_data,
    ) -> LimitOrderResult:

        status = order_data["orderStatus"]

        # Ордер исполнен?
        if status == "Filled":
            return self._handle_filled_order(
                side=side,
                order_id=order_id,
                order_data=order_data,
            )

        # Ордер частично исполнен?
        if status == "PartiallyFilled":
            return self._handle_partial_order(
                symbol=symbol,
                side=side,
                order_id=order_id,
                order_data=order_data,
            )

        # Ордер не исполнен?
        if status == "New":
            return self._handle_unfilled_order(
                symbol=symbol,
                side=side,
                order_id=order_id,
                order_data=order_data,
            )

        # Неожиданный статус ордера -> выбрасываем исключение
        raise RuntimeError(
            f"Unexpected close limit order status | "
            f"symbol={symbol} | "
            f"side={side} | "
            f"qty={qty} | "
            f"order_id={order_id} | "
            f"status={status}"
        )


    def _handle_filled_order(
        self,
        side: str,
        order_id: str,
        order_data,
    ) -> LimitOrderResult:
        # Получаем данные ордера
        filled_qty, avg_price, fee = self._get_execution_data(
            order_data
        )

        # Лог
        self.logger.info(
            f"[CLOSE LIMIT] order filled | "
            f"side={side} | "
            f"qty={filled_qty} | "
            f"avg_price={avg_price} | "
            f"fee={fee} | "
            f"order_id={order_id}"
        )

        # Возвращаем результат
        return LimitOrderResult(
            order_id=order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            fee=fee,
            status=LimitOrderStatus.FILLED,
            filled=True,
        )


    def _handle_partial_order(
        self,
        symbol: str,
        side: str,
        order_id: str,
        order_data,
    ) -> LimitOrderResult:
        # Получаем данные ордера
        filled_qty, avg_price, fee = self._get_execution_data(
            order_data
        )

        # Отменяем оставшуюся часть ордера
        self._cancel_order_checked(
            symbol=symbol,
            order_id=order_id,
        )

        # Лог
        self.logger.info(
            f"[CLOSE LIMIT] order partially filled | "
            f"side={side} | "
            f"filled_qty={filled_qty} | "
            f"avg_price={avg_price} | "
            f"fee={fee} | "
            f"order_id={order_id}"
        )

        # Возвращаем результат
        return LimitOrderResult(
            order_id=order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            fee=fee,
            status=LimitOrderStatus.PARTIALLY_FILLED,
            filled=False,
        )


    def _handle_unfilled_order(
        self,
        symbol: str,
        side: str,
        order_id: str,
        order_data,
    ) -> LimitOrderResult:
        # Получаем данные ордера
        filled_qty, avg_price, fee = self._get_execution_data(
            order_data
        )

        # Отменяем ордер
        self._cancel_order_checked(
            symbol=symbol,
            order_id=order_id,
        )

        # Лог
        self.logger.info(
            f"[CLOSE LIMIT] order not filled | "
            f"side={side} | "
            f"filled_qty={filled_qty} | "
            f"avg_price={avg_price} | "
            f"fee={fee} | "
            f"order_id={order_id}"
        )

        # Возвращаем результат
        return LimitOrderResult(
            order_id=order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            fee=fee,
            status=LimitOrderStatus.NOT_FILLED,
            filled=False,
        )


    def _get_execution_data(self, order_data):

        filled_qty = float(
            order_data.get("cumExecQty", 0) or 0
        )

        avg_price_raw = order_data.get("avgPrice")

        avg_price = (
            float(avg_price_raw)
            if avg_price_raw
            else None
        )

        fee_detail = order_data.get("cumFeeDetail") or {}

        fee = float(
            fee_detail.get("USDT", 0) or 0
        )

        return filled_qty, avg_price, fee


    def _cancel_order_checked(
        self,
        symbol: str,
        order_id: str,
    ):
        # Отменяем ордер 
        cancel_result = self._cancel_order(
            symbol=symbol,
            order_id=order_id,
        )

        # Проверяем результат отмены
        if cancel_result not in (0, 110001):
            raise RuntimeError(
                f"Failed to cancel close limit order | "
                f"symbol={symbol} | "
                f"order_id={order_id} | "
                f"cancel_result={cancel_result}"
            )    