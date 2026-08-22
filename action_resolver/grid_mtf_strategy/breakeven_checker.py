class BreakevenChecker:

    def __init__(
        self,
        fee_taker: float,
        side: str,
    ):
        self.fee_taker = fee_taker
        self.side = side

    def is_ok(
        self,
        entry,
        price: float,
    ) -> bool:

        shift = 4 * self.fee_taker

        if self.side == "Buy":
            breakeven = entry.price * (1 + shift)
            return price >= breakeven

        breakeven = entry.price * (1 - shift)
        return price <= breakeven