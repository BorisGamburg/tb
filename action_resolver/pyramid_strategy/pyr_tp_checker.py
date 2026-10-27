from signals.ha_reversal_signal import HAReversalSignal


class PyrTPChecker:

    def __init__(
        self,
        proxy_driver,
        symbol: str,
        side: str,
        price_service,
        fee_taker: float,
    ):
        self.symbol = symbol
        self.side = side
        self.price_service = price_service
        self.fee_taker = fee_taker

        self.ha_signal = HAReversalSignal(
            proxy_driver=proxy_driver,
            symbol=symbol,
        )

    def check(self, entries, entry_tf: str) -> bool:
        # Проверяем HA-разворот
        if not self.ha_signal.is_exit(tf=entry_tf, side=self.side):
            return False

        # Уровней нет — закрывать нечего
        if not entries:
            return False

        return self.calc_total_pnl(entries) > self.calc_min_profit(entries)

    def calc_total_pnl(self, entries) -> float:
        close_price = self.price_service.get_market_close_price(
            symbol=self.symbol,
            side=self.side,
        )
        total_pnl = 0.0

        for entry in entries:
            if entry.qty <= 0:
                continue

            if self.side == "Buy":
                gross_pnl = (close_price - entry.price) * entry.qty
            elif self.side == "Sell":
                gross_pnl = (entry.price - close_price) * entry.qty
            else:
                raise ValueError(f"Unsupported side: {self.side}")

            entry_fee = entry.price * entry.qty * self.fee_taker
            close_fee = close_price * entry.qty * self.fee_taker

            total_pnl += gross_pnl - entry_fee - close_fee

        return total_pnl

    def calc_min_profit(self, entries) -> float:
        MIN_PROFIT_PCT = 0.1
        entries_value = sum(entry.price * entry.qty for entry in entries)
        return entries_value * MIN_PROFIT_PCT / 100