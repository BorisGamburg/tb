class CloseResultCalculator:
    def __init__(
        self,
        hedge_side: str,
        fee_taker: float,
    ):
        self.hedge_side = hedge_side
        self.fee_taker = fee_taker

    def calc_netto_pnl(
        self,
        loss_level,
        profit_level,
        cur_price: float
    ):
        # Вычисляем суммарный размер уровней
        total_qty = loss_level.qty + profit_level.qty

        # Вычисляем pnl при закрытии уровней по тек цене
        loss_pnl, profit_pnl = self._get_pnl(
            loss_level,
            profit_level,
            cur_price
        )

        # Вычисляем комиссии для убыточного, прибыльного уровней и для закрытия
        loss_level_fee, profit_level_fee, close_fee = self._get_fees(
            loss_level,
            profit_level,
            total_qty,
            cur_price
        )

        # Рассчитываем profit_buffer затраты
        profit_buffer_cost = self._get_profit_buffer(total_qty, cur_price)

        # Вычисляем полные затраты
        total_cost = (
            loss_level_fee
            + profit_level_fee
            + close_fee
            + profit_buffer_cost
        )

        # Вычисляем netto_pnl
        netto_pnl = loss_pnl + profit_pnl - total_cost

        # Возвращаем netto_pnl
        return netto_pnl

    def _get_fees(self, loss_level, profit_level, total_qty, cur_price):
        loss_level_fee = self._get_loss_level_fee(loss_level)
        profit_level_fee = self._get_profit_level_fee(profit_level)
        close_fee = self._get_close_fee(total_qty, cur_price)

        return loss_level_fee, profit_level_fee, close_fee

    def _get_profit_buffer(self, total_qty, cur_price):
        min_profit_buffer = 0.001
        close_value = cur_price * total_qty
        return close_value * min_profit_buffer

    def _get_close_fee(self, total_qty, cur_price):
        return (
            cur_price
            * total_qty
            * self.fee_taker
        )

    def _get_profit_level_fee(self, profit_level):
        return (
            profit_level.price
            * profit_level.qty
            * self.fee_taker
        )

    def _get_loss_level_fee(self, loss_level):
        return (
            loss_level.price
            * loss_level.qty
            * self.fee_taker
        )

    def _get_pnl(self, losing_level, profitable_level, cur_price):
        if self.hedge_side == "Buy":
            losing_pnl = (
                cur_price - losing_level.price
            ) * losing_level.qty

            profitable_pnl = (
                cur_price - profitable_level.price
            ) * profitable_level.qty

        elif self.hedge_side == "Sell":
            losing_pnl = (
                losing_level.price - cur_price
            ) * losing_level.qty

            profitable_pnl = (
                profitable_level.price - cur_price
            ) * profitable_level.qty

        else:
            raise ValueError(f"Unsupported side: {self.hedge_side}")

        return losing_pnl, profitable_pnl