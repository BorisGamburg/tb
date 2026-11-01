import logging

from managers.scale_pool_mng import ScalePoolMng
from action_processor.execution.limit_order_base import LimitOrderBase
from action_processor.execution.limit_order_result import LimitOrderResult, LimitOrderStatus
from common.market_service import MarketService
from proxy_server.proxy_driver import ProxyDriver
from action_processor.bootstrap import AppContext
from common.trading_info import TradingInfo


class OpenActiveLimitMng(LimitOrderBase):
    order_label = "open limit"

    proxy_driver: ProxyDriver
    price_service: MarketService
    logger: logging.Logger

    def __init__(
        self,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ):
        super().__init__(
            proxy_driver=app_ctx.proxy_driver,
            logger=app_ctx.logger,
        )
        self.app_ctx = app_ctx
        self.price_service = app_ctx.price_service
        self.trading_info = trading_info

        self.scale_pool_mng = ScalePoolMng(
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            logger=self.logger,
        )

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

        # Ордер исполнен полностью: ничего делать не нужно
        if status == "Filled":
            return self._handle_filled_order(
                side=side,
                order_id=order_id,
                order_price=order_price,
                order_data=order_data,
            )

        # Ордер исполнен частично: отменяем остаток
        if status == "PartiallyFilled":
            return self._cancel_and_handle_order(
                symbol=symbol,
                side=side,
                order_id=order_id,
                order_price=order_price,
            )

        # Ордер не исполнен: возвращаем его в пул
        if status == "New":
            return self._handle_new_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_id=order_id,
                order_price=order_price,
            )

        # Неожиданный статус ордера -> выбрасываем исключение
        raise RuntimeError(
            f"Unexpected order status | symbol={symbol} "
            f"| qty={qty} | order_id={order_id} | status={status}"
        )

    def _handle_new_order(
        self,
        symbol,
        side,
        qty,
        order_id,
        order_price,
    ):
        # Пробуем вернуть ордер в пул
        move_result = self.scale_pool_mng.move_order_to_pool(
            symbol=symbol,
            side=side,
            order_id=order_id,
            new_qty=self.trading_info.min_qty,
        )

        # Ордер вернулся в пул
        if move_result["changed"]:
            return self._handle_unfilled_order(
                side=side,
                order_id=order_id,
                order_price=order_price,
            )

        # Биржа отказала в перемещении: смотрим, что с ордером
        order_data = self.get_order_status(
            symbol=symbol,
            order_id=order_id,
        )

        if not order_data:
            raise RuntimeError(
                f"Order not found after failed move to pool | "
                f"symbol={symbol} | order_id={order_id}"
            )

        # Ордер всё ещё не исполнен, но переместить его не удалось -> исключение
        if order_data["orderStatus"] == "New":
            raise RuntimeError(
                f"Failed to move unfilled order to pool | "
                f"symbol={symbol} | order_id={order_id} | "
                f"retCode={move_result.get('retCode')} | "
                f"retMsg={move_result.get('retMsg')}"
            )

        # Ордер исполнен или исполнен частично: обрабатываем по статусу.
        # Повторного входа сюда не будет: статус New исключён выше.
        return self._process_limit_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_id=order_id,
            order_price=order_price,
            order_data=order_data,
        )

    def _cancel_and_handle_order(
        self,
        symbol,
        side,
        order_id,
        order_price,
    ):
        # Отменяем ордер и получаем его исход
        outcome, final_data = self._cancel_and_get_outcome(
            symbol=symbol,
            order_id=order_id,
        )

        # Ордер успел исполниться полностью до отмены
        if outcome == LimitOrderStatus.FILLED:
            return self._handle_filled_order(
                side=side,
                order_id=order_id,
                order_price=order_price,
                order_data=final_data,
            )

        # Ордер отменён, но часть успела исполниться
        if outcome == LimitOrderStatus.PARTIALLY_FILLED:
            return self._handle_partial_order(
                side=side,
                order_id=order_id,
                order_price=order_price,
                order_data=final_data,
            )

        # Ордер был частично исполнен, а отменён с нулевым исполнением:
        # так быть не может, ордер потерян -> исключение
        raise RuntimeError(
            f"Partially filled order cancelled with zero fill | "
            f"order_id={order_id} | "
            f"status={final_data.get('orderStatus')}"
        )

    def _handle_unfilled_order(
        self,
        side,
        order_id,
        order_price,
    ):
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
        side,
        order_id,
        order_price,
        order_data,
    ):
        # Данные окончательные: ордер уже отменён
        filled_qty, avg_price, fee = self._get_execution_data(order_data)

        self._check_execution_price(
            side=side,
            order_price=order_price,
            avg_price=avg_price,
        )

        self.logger.info(
            f"[LIMIT] order partially filled | order_id={order_id} "
            f"| filled_qty={filled_qty}"
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
        filled_qty, avg_price, fee = self._get_execution_data(order_data)

        self._check_execution_price(
            side=side,
            order_price=order_price,
            avg_price=avg_price,
        )

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