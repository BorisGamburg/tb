import time
from dataclasses import dataclass


@dataclass
class ExecutionDetails:
    qty: float
    avg_price: float
    fee: float
    timestamp: int


class ExecutionWaiter:
    def __init__(self, proxy_driver):
        self.proxy_driver = proxy_driver

    def wait(
        self,
        symbol: str,
        order_id: str,
        retries: int,
        delay: float,
    ) -> ExecutionDetails:
        for _ in range(retries):
            details = self.proxy_driver.execute(
                "get_order_execution_details",
                symbol=symbol,
                order_id=order_id,
            )

            if details:
                return ExecutionDetails(
                    qty=float(details["totalQty"]),
                    avg_price=float(details["avgPrice"]),
                    fee=float(details["execFee"]),
                    timestamp=int(details["lastExecTime"]),
                )

            time.sleep(delay)

        raise RuntimeError(
            f"No execution details for order {order_id}"
        )
