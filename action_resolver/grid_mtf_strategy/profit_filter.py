class ProfitFilter:

    def __init__(
        self,
        price_service,
        symbol,
        side,
        fee_taker
    ):
        self.price_service = price_service
        self.symbol = symbol
        self.side = side
        self.fee_taker = fee_taker

    def get_most_profitable_level(self, entries):
        if not entries:
            return None

        price = self.price_service.get_market_close_price(
            symbol=self.symbol,
            side=self.side,
        )

        min_profit = price * 7 * self.fee_taker

        if self.side == "Sell":
            profitable = [
                entry
                for entry in entries
                if entry.price > price + min_profit
            ]

            if not profitable:
                return None

            return max(
                profitable,
                key=lambda entry: entry.price,
            )

        profitable = [
            entry
            for entry in entries
            if entry.price < price - min_profit
        ]

        if not profitable:
            return None

        return min(
            profitable,
            key=lambda entry: entry.price,
        )        