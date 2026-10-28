from action_processor.action import Action, ActionCommand
from action_processor.execution.execution_waiter import ExecutionWaiter
from action_processor.execution.execution_result import ExecutionResult
from utils.utils import get_inverse_side
from action_processor.execution.open_active_limit_mng import OpenActiveLimitMng
from action_processor.execution.limit_order_result import LimitOrderStatus
from action_processor.execution.close_limit_mng import CloseLimitMng, ExitType
from action_processor.bootstrap import AppContext
from common.trading_info import TradingInfo


class Execution:
    def __init__(
        self,
        app_ctx: AppContext,
        trading_info: TradingInfo,
        order_notifications_enabled: bool = False,
    ):
        self.app_ctx = app_ctx
        self.order_notifications_enabled = order_notifications_enabled
        self.proxy_driver = app_ctx.proxy_driver
        self.price_service = app_ctx.price_service
        self.logger = app_ctx.logger
        self.telegram = app_ctx.telegram

        self.execution_waiter = ExecutionWaiter(self.proxy_driver)
        self.open_active_limit_mng = OpenActiveLimitMng(
            app_ctx=app_ctx,
            trading_info=trading_info,
        )

        self.close_limit_mng = CloseLimitMng(
            proxy_driver=self.proxy_driver,
            market_service=self.price_service,
            logger=self.logger,
        )

    def _get_order_details(self, res, symbol):
        order_id = res["result"]["orderId"]

        details = self.execution_waiter.wait(
            symbol=symbol,
            order_id=order_id,
            retries=150,
            delay=0.2,
        )

        return details.qty, details.avg_price, details.fee

    def _place_market_order(self, symbol, side, qty):

        pos_idx = 2 if side == "Buy" else 1

        res = self.proxy_driver.execute(
            "place_market_order",
            symbol=symbol,
            side=side,
            position_idx=pos_idx,
            qty=qty
        )

        if not res or res.get("retCode") != 0:
            raise RuntimeError(f"Market order failed: {res}")

        return res

    def execute(self, act_cmd: ActionCommand) -> ExecutionResult:
        action = act_cmd.action

        if action == Action.OPEN:
            price, qty, fee, executed, status, order_id = self._exec_open(
                act_cmd,
            )

        elif action == Action.CLOSE:
            price, qty, fee, executed, status, order_id = self._exec_close(
                act_cmd,
            )

        elif action == Action.CLOSE_POSITION:
            price, qty, fee, executed, status = self._exec_close_position(
                act_cmd,
            )
            order_id = None

        else:
            raise ValueError(f"Unknown Action: {action}")

        exec_result = ExecutionResult(
            action_command=act_cmd,
            price=price,
            qty=qty,
            fee=fee,
            executed=executed,
            status=status,
            order_id=order_id,
        )

        if exec_result.executed:
            self.logger.info(
                f"[EXECUTION] action={exec_result.action_command.action.value} "
                f"| side={exec_result.action_command.side} "
                f"| qty={exec_result.qty} "
                f"| price={exec_result.price}"
            )

            order_storage = self.app_ctx.order_storage

            if (
                order_storage is not None
                and exec_result.order_id is not None
                and exec_result.status is not None
            ):
                try:
                    order_storage.save_order(
                        order_id=exec_result.order_id,
                        symbol=act_cmd.symbol,
                        side=act_cmd.side,
                        status=exec_result.status.value,
                        filled_qty=exec_result.qty,
                        avg_price=exec_result.price,
                        fee=exec_result.fee,
                    )
                except Exception:
                    self.logger.exception(
                        "Failed to save order to PostgreSQL "
                        f"| symbol={act_cmd.symbol} "
                        f"| order_id={exec_result.order_id}"
                    )

            self.notify_telegram(exec_result)

        return exec_result

    def _exec_close_position(self, result):
        # Получаем размер позиции
        position = self.proxy_driver.get_position(
            symbol=result.symbol,
            side=result.side,
        )
        position_qty = float(position["size"])

        # Размер позиции < 0? Нонсенс -> исключение
        if position_qty < 0:
            raise RuntimeError(
                f"Invalid position quantity "
                f"| symbol={result.symbol} "
                f"| side={result.side} "
                f"| qty={position_qty}"
            )

        # Размер позиции = 0 -> позиции нет.
        # Выходим, executed=False
        if position_qty == 0:
            return 0.0, 0.0, 0.0, False, None

        order_side = get_inverse_side(result.side)

        res = self._place_market_order(
            symbol=result.symbol,
            side=order_side,
            qty=position_qty,
        )

        real_qty, avg_price, fee = self._get_order_details(
            res=res,
            symbol=result.symbol,
        )

        if abs(real_qty - position_qty) > 1e-8:
            raise RuntimeError(
                f"Close position partially filled "
                f"| symbol={result.symbol} "
                f"| side={result.side} "
                f"| requested_qty={position_qty} "
                f"| executed_qty={real_qty}"
            )

        return avg_price, real_qty, fee, True, None

    def _exec_open(self, result):
        order_result = self.open_active_limit_mng.wait_limit_order(
            symbol=result.symbol,
            side=result.side,
            qty=result.qty,

        )

        return (
            order_result.avg_price,
            order_result.filled_qty,
            order_result.fee,
            order_result.filled,
            order_result.status,
            order_result.order_id,
        )

    def _exec_close(self, result):
        order_result = self.close_limit_mng.wait_limit_order(
            symbol=result.symbol,
            side=result.side,
            qty=result.qty,
            exit_type=ExitType.ACTIVE,
        )

        if order_result.status == LimitOrderStatus.PARTIALLY_FILLED:
            result.action = Action.CLOSE_PARTIAL

        executed = (
            order_result.status != LimitOrderStatus.NOT_FILLED
        )

        return (
            order_result.avg_price,
            order_result.filled_qty,
            order_result.fee,
            executed,
            order_result.status,
            order_result.order_id,
        )

    def notify_telegram(self, exec_result: ExecutionResult) -> None:
        # Уведомления об открытии/закрытии ордеров включаются в конфиге
        if not self.order_notifications_enabled:
            return

        tg_msg = self._build_message(exec_result)
        if tg_msg and self.telegram:
            self.telegram.send_telegram_message(tg_msg)

    def _build_message(
        self,
        result: ExecutionResult,
    ) -> str | None:
        symbol = result.action_command.symbol
        side = result.action_command.side

        if result.action_command.action == Action.OPEN:
            if result.action_command.reason == "REARM":
                opening_context = "Reason: REARM\n"
            else:
                details = result.action_command.details
                ha_reversal_tf = None

                if details and details.entry_check:
                    ha_reversal_tf = details.entry_check.ha_revers_result.details.tf

                opening_context = f"HA reversal TF: {ha_reversal_tf}\n"

            if result.status == LimitOrderStatus.PARTIALLY_FILLED:
                return (
                    "💎 LEVEL PARTIALLY OPENED\n"
                    f"Symbol: {symbol}\n"
                    f"Side: {side}\n"
                    f"Qty: {result.qty}\n"
                    f"Price: {result.price}\n"
                    f"{opening_context}"
                    "Status: PARTIALLY_FILLED\n"
                )

            return (
                "💎 LEVEL OPENED\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}\n"
                f"{opening_context}"
            )

        if result.action_command.action in (Action.CLOSE, Action.CLOSE_PARTIAL):
            details = result.action_command.details

            if details and details.bbw_exit:
                return (
                    "📉 LEVELS CLOSED\n"
                    f"Symbol: {symbol}\n"
                    f"Qty: {result.qty}\n"
                    f"Price: {result.price}\n"
                    f"BB TF: {details.bbw_exit.tf}\n"
                    f"Exit: {details.bbw_exit.exit_type}\n"
                )

            reason = result.action_command.reason

            return (
                "📉 LEVELS CLOSED\n"
                f"Symbol: {symbol}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}\n"
                f"Reason: {reason}\n"
            )

        if result.action_command.action == Action.CLOSE_POSITION:
            return (
                "📉 POSITION CLOSED\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}\n"
            )

        return None