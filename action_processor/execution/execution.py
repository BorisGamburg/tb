from action_processor.action import Action, ActionCommand
from proxy_server.proxy_driver import ProxyDriver
from action_processor.execution.execution_waiter import ExecutionWaiter
import logging
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
    ):
        self.app_ctx = app_ctx
        self.proxy_driver = app_ctx.proxy_driver
        self.price_service = app_ctx.price_service
        self.logger = app_ctx.logger

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
            price, qty, fee, executed, status = self._exec_open(act_cmd)

        elif action == Action.CLOSE:
            price, qty, fee, executed, status = self._exec_close(act_cmd)

        elif action == Action.CLOSE_POSITION:
            price, qty, fee, executed, status = self._exec_close_position(
                act_cmd,
            )
            
        else:
            raise ValueError(f"Unknown Action: {action}")

        exec_result = ExecutionResult(
            action_command=act_cmd,
            price=price,
            qty=qty,
            fee=fee,
            executed=executed,
            status=status,
        )

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
        )