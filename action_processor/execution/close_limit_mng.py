import time

from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver
from action_processor.execution.limit_order_result import (
    LimitOrderResult,
    LimitOrderStatus,
)

from enum import Enum


class ExitType(Enum):
    ACTIVE = "active"
    PASSIVE = "passive"


class CloseLimitMng:
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
    ):
        time.sleep(0.2)

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

        return order_data

    def wait_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        exit_type: ExitType,
    ) -> LimitOrderResult:
        # Размещаем ордер на закрытие позиции
        order_id = self._place_close_order(
            symbol=symbol,
            side=side,
            qty=qty,
            exit_type=exit_type
        )

        # Проверяем исполнение ордера после короткой задержки
        order_data = self._wait_limit_order(
            symbol=symbol,
            order_id=order_id,
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
        exit_type: ExitType
    ) -> str:
        # Получаем цену для активного/пассивного исполнения лимитного ордера
        if exit_type == ExitType.ACTIVE:
            price = self.market_service.get_active_price(
                symbol=symbol,
                side=side,
            )
        elif exit_type == ExitType.PASSIVE:
            price = self.market_service.get_limit_price(
                symbol=symbol,
                side=side,
            )
        else:
            raise RuntimeError(
                f"Unexpected exit type | "
                f"symbol={symbol} | "
                f"side={side} | "
                f"exit_type={exit_type}"
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
        self.logger.debug(
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
            result = self._handle_unfilled_order(
                symbol=symbol,
                side=side,
                order_id=order_id,
                order_data=order_data,
            )

            if isinstance(result, dict):
                return self._handle_filled_order(
                    side=side,
                    order_id=order_id,
                    order_data=result,
                )

            return result

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
        self.logger.debug(
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
    ) -> LimitOrderResult | dict:
        # Получаем данные ордера
        filled_qty, avg_price, fee = self._get_execution_data(
            order_data
        )

        # Отменяем ордер
        cancel_result = self._cancel_order_checked(
            symbol=symbol,
            order_id=order_id,
            allow_110001=True,
        )

        # Ордер уже мог исполниться до отмены
        if cancel_result == 110001:
            return self._get_filled_order_after_cancel_error(
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
            else 0.0
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
        allow_110001: bool = False,
    ) -> int:
        # Отменяем ордер
        cancel_result = self._cancel_order(
            symbol=symbol,
            order_id=order_id,
        )

        # Ордер мог исполниться до попытки отмены
        if allow_110001 and cancel_result == 110001:
            return cancel_result

        # Проверяем результат отмены
        if cancel_result != 0:
            raise RuntimeError(
                f"Failed to cancel close limit order | "
                f"symbol={symbol} | "
                f"order_id={order_id} | "
                f"cancel_result={cancel_result}"
            )

        return cancel_result

    def _get_filled_order_after_cancel_error(
        self,
        symbol: str,
        order_id: str,
    ) -> dict:
        updated_order_data = self.get_order_status(
            symbol=symbol,
            order_id=order_id,
        )

        if not updated_order_data:
            raise RuntimeError(
                f"Order not found after cancel result 110001 | "
                f"symbol={symbol} | "
                f"order_id={order_id}"
            )

        updated_status = updated_order_data.get("orderStatus")

        if updated_status != "Filled":
            raise RuntimeError(
                f"Unexpected order status after cancel result 110001 | "
                f"symbol={symbol} | "
                f"order_id={order_id} | "
                f"status={updated_status}"
            )

        return updated_order_data