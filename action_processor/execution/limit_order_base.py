import time

from action_processor.execution.limit_order_result import LimitOrderStatus


class LimitOrderBase:
    """
    Общая основа менеджеров лимитных ордеров (открытие и закрытие):
    чтение ордера, отмена и определение исхода ордера после отмены.
    """

    # Метка для сообщений об ошибках, например "open limit" / "close limit"
    order_label = "limit"

    def __init__(
        self,
        proxy_driver,
        logger,
    ):
        self.proxy_driver = proxy_driver
        self.logger = logger

    def get_order_status(self, symbol: str, order_id: str):
        return self.proxy_driver.execute(
            "get_order_status",
            symbol=symbol,
            order_id=order_id,
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

    def _cancel_and_get_outcome(
        self,
        symbol: str,
        order_id: str,
    ):
        """
        Отменяет активный ордер и возвращает пару (исход, данные ордера).
        Исход (LimitOrderStatus):
          - FILLED: ордер уже исполнился полностью (отмена вернула 110001);
          - PARTIALLY_FILLED: ордер отменён, часть успела исполниться;
          - NOT_FILLED: ордер отменён целиком, ничего не исполнено.
        Всё остальное - исключение.
        """
        # Отменяем ордер
        cancel_result = self._cancel_order_checked(
            symbol=symbol,
            order_id=order_id,
        )

        # Получаем данные ордера
        order_data = self.get_order_status(
            symbol=symbol,
            order_id=order_id,
        )

        # Исключение если нет данных
        if not order_data:
            raise RuntimeError(
                f"Order not found after cancel | "
                f"symbol={symbol} | "
                f"order_id={order_id} | "
                f"cancel_result={cancel_result}"
            )

        # Получаен статус ордера
        status = order_data.get("orderStatus")

        # Обрабатываем разные статусы
        if cancel_result == 110001:
            # Ордер не был отменен
            if status != "Filled":
                # Если статус не Filled, то это странно -> исключение
                raise RuntimeError(
                    f"Unexpected order status after cancel result 110001 | "
                    f"symbol={symbol} | "
                    f"order_id={order_id} | "
                    f"status={status} | "
                    f"cumExecQty={order_data.get('cumExecQty')}"
                )
        elif status not in ("Cancelled", "PartiallyFilledCanceled"):
            # Странные статусы -> исключение
            raise RuntimeError(
                f"Unexpected order status after successful cancel | "
                f"symbol={symbol} | "
                f"order_id={order_id} | "
                f"status={status} | "
                f"cumExecQty={order_data.get('cumExecQty')}"
            )

        # Ордер исполнен полностью
        if status == "Filled":
            return LimitOrderStatus.FILLED, order_data

        # Ордер отменён, но часть успела исполниться
        filled_qty, _, _ = self._get_execution_data(order_data)
        if filled_qty > 0:
            return LimitOrderStatus.PARTIALLY_FILLED, order_data

        # Ордер отменён целиком
        return LimitOrderStatus.NOT_FILLED, order_data



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
    ) -> int:
        # Отменяем ордер
        cancel_result = self._cancel_order(
            symbol=symbol,
            order_id=order_id,
        )

        # 110001: ордер уже не активен (мог исполниться до отмены),
        # разбор делает вызывающий код. Любой другой код, кроме 0, - сбой.
        if cancel_result not in (0, 110001):
            raise RuntimeError(
                f"Failed to cancel {self.order_label} order | "
                f"symbol={symbol} | "
                f"order_id={order_id} | "
                f"cancel_result={cancel_result}"
            )

        return cancel_result