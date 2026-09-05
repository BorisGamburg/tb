class MarketService:
    def __init__(self, proxy_driver):
        self.proxy_driver = proxy_driver

    def calc_position_market_close_pnl(
        self,
        symbol: str,
        position_entry_price: float,
        position_qty: float,
        position_side: str,
    ) -> float:
        """
        Рассчитывает PnL позиции при её немедленном
        закрытии рыночным ордером.

        Для LONG используется текущий bid,
        для SHORT — текущий ask.
        """
        close_price = self.get_market_close_price(
            symbol=symbol,
            side=position_side,
        )

        if position_side == "Buy":
            return (
                close_price - position_entry_price
            ) * position_qty

        if position_side == "Sell":
            return (
                position_entry_price - close_price
            ) * position_qty

        raise ValueError(
            f"Unknown position side: {position_side}"
        )    

    def calc_position_market_close_fee(
        self,
        symbol: str,
        position_qty: float,
        position_side: str,
        fee_taker: float,
    ) -> float:
        """
        Рассчитывает комиссию, которую заплатим
        при немедленном закрытии позиции рыночным ордером.
        """
        close_price = self.get_market_close_price(
            symbol=symbol,
            side=position_side,
        )

        return close_price * position_qty * fee_taker    

    def get_market_close_price(
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

    def get_limit_price(
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

    def get_market_price(
        self,
        symbol: str,
        side: str,
    ) -> float:
        ticker = self.proxy_driver.get_ticker(symbol)

        return (
            ticker["ask"]
            if side == "Buy"
            else ticker["bid"]
        )    
