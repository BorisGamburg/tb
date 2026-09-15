class CloseResultCalculator:
    def __init__(
        self,
        current_price: float,
        side: str,
        fee_taker: float,
    ):
        self.current_price = current_price
        self.side = side
        self.fee_taker = fee_taker

    def calculate(
        self,
        losing_level,
        profitable_level,
    ):
        total_qty = losing_level.qty + profitable_level.qty

        losing_pnl, profitable_pnl = self._get_pnl(
            losing_level,
            profitable_level,
        )

        losing_open_fee, profitable_open_fee, close_fee = self._get_fees(
            losing_level,
            profitable_level,
            total_qty,
        )

        slippage_cost = self._get_profit_buffer(total_qty)

        total_cost = (
            losing_open_fee
            + profitable_open_fee
            + close_fee
            + slippage_cost
        )

        gross_pnl = losing_pnl + profitable_pnl
        return gross_pnl - total_cost

    def _get_fees(self, losing_level, profitable_level, total_qty):
        losing_open_fee = self._get_losing_level_fee(losing_level)
        profitable_open_fee = self._get_profit_level_fee(profitable_level)
        close_fee = self._get_close_fee(total_qty)

        return losing_open_fee, profitable_open_fee, close_fee

    def _get_profit_buffer(self, total_qty):
        min_profit_buffer = 0.001
        close_value = self.current_price * total_qty
        return close_value * min_profit_buffer

    def _get_close_fee(self, total_qty):
        return (
            self.current_price
            * total_qty
            * self.fee_taker
        )

    def _get_profit_level_fee(self, profitable_level):
        return (
            profitable_level.price
            * profitable_level.qty
            * self.fee_taker
        )

    def _get_losing_level_fee(self, losing_level):
        return (
            losing_level.price
            * losing_level.qty
            * self.fee_taker
        )

    def _get_pnl(self, losing_level, profitable_level):
        if self.side == "Sell":
            losing_pnl = (
                self.current_price - losing_level.price
            ) * losing_level.qty

            profitable_pnl = (
                self.current_price - profitable_level.price
            ) * profitable_level.qty

        elif self.side == "Buy":
            losing_pnl = (
                losing_level.price - self.current_price
            ) * losing_level.qty

            profitable_pnl = (
                profitable_level.price - self.current_price
            ) * profitable_level.qty

        else:
            raise ValueError(f"Unsupported side: {self.side}")

        return losing_pnl, profitable_pnl