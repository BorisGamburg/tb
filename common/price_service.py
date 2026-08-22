class PriceService:
    def __init__(self, proxy_driver):
        self.proxy_driver = proxy_driver

    def _get_execution_price(
        self,
        symbol: str,
        side: str,
    ) -> float:
        ticker = self.proxy_driver.get_ticker(symbol)

        return (
            ticker["bid"]
            if side == "Buy"
            else ticker["ask"]
        )

    def get_market_close_price(
        self,
        symbol: str,
        side: str,
    ) -> float:
        return self._get_execution_price(symbol, side)

    def get_chase_price(
        self,
        symbol: str,
        side: str,
    ) -> float:
        return self._get_execution_price(symbol, side)