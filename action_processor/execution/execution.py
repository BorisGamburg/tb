from action_processor.action import Action, ActionCommand
from proxy_server.proxy_driver import ProxyDriver
from action_processor.execution.execution_waiter import ExecutionWaiter
import logging
from action_processor.execution.execution_result import ExecutionResult
from utils.utils import get_inverse_side
from action_processor.execution.open_limit_order_mng import OpenLimitOrderMng
from action_processor.execution.close_limit_order_mng import CloseLimitOrderMng
from action_processor.execution.limit_order_result import LimitOrderStatus


class Execution:
    def __init__(self, proxy_driver: ProxyDriver, price_service, logger: logging.Logger):
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger

        self.execution_waiter = ExecutionWaiter(proxy_driver)

        self.limit_order_mng = OpenLimitOrderMng(
            proxy_driver=proxy_driver,
            price_service=price_service,
            logger=logger,
        )

        self.close_limit_order_mng = CloseLimitOrderMng(
            proxy_driver=proxy_driver,
            market_service=price_service,
            logger=logger,
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
            price, qty, fee, executed = self._exec_open(act_cmd)

        elif action == Action.CLOSE:
            price, qty, fee, executed = self._exec_close(act_cmd)

        elif action == Action.CLOSE_POSITION:
            price, qty, fee = self._exec_close_position(act_cmd)            
            executed = True

        else:
            raise ValueError(f"Unknown Action: {action}")

        return ExecutionResult(
            action_command=act_cmd,
            price=price,
            qty=qty,
            fee=fee,
            executed=executed,
        )    

    def _exec_close_position(self, result):
        position = self.proxy_driver.get_position(
            symbol=result.symbol,
            side=result.side,
        )

        position_qty = float(position["size"])

        if position_qty <= 0:
            return None, 0.0, 0.0

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

        return avg_price, real_qty, fee

    def _exec_open(self, result):
        order_result = self.limit_order_mng.wait_limit_order(
            symbol=result.symbol,
            side=result.side,
            qty=result.qty,
        )

        if order_result.filled and abs(
            order_result.filled_qty - result.qty
        ) > 1e-8:
            raise RuntimeError(
                f"Open order partially filled "
                f"| symbol={result.symbol} "
                f"| requested_qty={result.qty} "
                f"| executed_qty={order_result.filled_qty}"
            )

        return (
            order_result.avg_price,
            order_result.filled_qty,
            order_result.fee,
            order_result.filled,
        )    

    def _exec_close(self, result):
        order_result = self.close_limit_order_mng.wait_limit_order(
            symbol=result.symbol,
            side=result.side,
            qty=result.qty,
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
        )