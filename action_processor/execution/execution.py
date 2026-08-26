from action_processor.action import Action, ActionCommand
from proxy_server.proxy_driver import ProxyDriver
from action_processor.execution.chase_mng import ChaseMng
from action_processor.execution.execution_waiter import ExecutionWaiter
import logging
from action_processor.execution.execution_result import ExecutionResult


class Execution:
    def __init__(self, proxy_driver: ProxyDriver, price_service, logger: logging.Logger):
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.logger = logger
        self.chase_mng = ChaseMng(proxy_driver, price_service, logger)
        self.execution_waiter = ExecutionWaiter(proxy_driver)

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
    
    def _place_chase_order(self, symbol, side, qty):
        status, order_id, order_price, filled_qty, fee = (
            self.chase_mng.wait_chase_order(
                symbol=symbol,
                side=side,
                qty=qty,
                sl_ratio=None,
            )
        )

        if status == "SKIPPED":
            raise RuntimeError(
                f"Chase skipped "
                f"| symbol={symbol} "
                f"| side={side} "
                f"| qty={qty}"
            )

        return order_id, order_price, filled_qty, fee    

    def execute(self, act_cmd: ActionCommand) -> ExecutionResult:
        action = act_cmd.action

        if action == Action.OPEN:
            price, qty, fee = self._exec_open(act_cmd)

        elif action == Action.CLOSE:
            price, qty, fee = self._exec_close(act_cmd)

        else:
            raise ValueError(f"Unknown Action: {action}")

        return ExecutionResult(
            action_command=act_cmd,
            price=price,
            qty=qty,
            fee=fee,
        )    

    def _exec_close(self, result):
        res = self._place_market_order(
            symbol=result.symbol,
            qty=result.qty,
            side=result.side,
        )

        real_qty, avg_price, fee = self._get_order_details(
            res=res,
            symbol=result.symbol,
        )

        if abs(real_qty - result.qty) > 1e-8:
            raise RuntimeError(
                f"Close order partially filled "
                f"| symbol={result.symbol} "
                f"| requested_qty={result.qty} "
                f"| executed_qty={real_qty}"
            )

        return avg_price, real_qty, fee    

    def _exec_open(self, result):
        order_id, order_price, filled_qty, fee = self._place_chase_order(
            symbol=result.symbol,
            side=result.side,
            qty=result.qty,
        )

        if abs(filled_qty - result.qty) > 1e-8:
            raise RuntimeError(
                f"Open order partially filled "
                f"| symbol={result.symbol} "
                f"| requested_qty={result.qty} "
                f"| executed_qty={filled_qty}"
            )

        return order_price, filled_qty, fee