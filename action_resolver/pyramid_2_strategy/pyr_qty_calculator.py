class PyrQtyCalculator:

    def __init__(
        self,
        proxy_driver,
        symbol: str,
        qty_pct: float,
        trading_info,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.qty_ratio = qty_pct / 100
        self.trading_info = trading_info

    def calculate(self) -> tuple[float, float]:
        balance = self.proxy_driver.get_balance()
        price = float(self.proxy_driver.get_last_price(self.symbol))

        raw_qty = balance * self.qty_ratio / price
        qty = self.trading_info.get_valid_order_qty(raw_qty)

        return raw_qty, qty