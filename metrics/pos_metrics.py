from prog.proxy_server.proxy_driver import ProxyDriver

class PositionMetrics:
    def __init__(self, proxy_driver: ProxyDriver, side_main: str):
        self.proxy_driver = proxy_driver
        self.side_main = side_main

    def net_pos_pct(self, symbol: str) -> float:
        balance = self.proxy_driver.get_balance()
        if balance <= 0:
            return 0.0

        pos_buy = self.proxy_driver.get_position(symbol, "Buy")
        pos_sell = self.proxy_driver.get_position(symbol, "Sell")

        buy_size = float(pos_buy.get("size", 0.0))
        sell_size = float(pos_sell.get("size", 0.0))

        if self.side_main == "Buy":
            net_size = buy_size - sell_size
        else:  # Sell
            net_size = sell_size - buy_size

        if net_size <= 0:
            return 0.0

        last_price = self.proxy_driver.get_last_price(symbol)

        notional = net_size * last_price

        return (notional / balance) * 100.0