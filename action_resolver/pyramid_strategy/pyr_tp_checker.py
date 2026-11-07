from signals.ha_reversal_signal import HAReversalSignal


class PyrTPChecker:

    PROFIT_BUFFER_PCT = 0.001

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

    def check(self, entries, entry_tf: str) -> list:
        if not entries:
            return []

        close_price = float(
            self.price_service.get_market_close_price(
                symbol=self.symbol,
                side=self.side,
            )
        )

        if not self.ha_signal.is_exit_by_price(
            tf=entry_tf,
            side=self.side,
            price=close_price,
        ):
            return []

        profitable_levels = []

        for entry in entries:
            if entry.qty <= 0:
                continue

            if self.side == "Buy":
                breakeven_price = (
                    entry.price * (1 + self.fee_taker)
                    / (1 - self.fee_taker)
                )
                min_close_price = (
                    breakeven_price * (1 + self.PROFIT_BUFFER_PCT)
                )

                if close_price < min_close_price:
                    continue

                gross_pnl = (close_price - entry.price) * entry.qty

            elif self.side == "Sell":
                breakeven_price = (
                    entry.price * (1 - self.fee_taker)
                    / (1 + self.fee_taker)
                )
                max_close_price = (
                    breakeven_price * (1 - self.PROFIT_BUFFER_PCT)
                )

                if close_price > max_close_price:
                    continue

                gross_pnl = (entry.price - close_price) * entry.qty

            else:
                raise ValueError(f"Unsupported side: {self.side}")

            entry_fee = entry.price * entry.qty * self.fee_taker
            close_fee = close_price * entry.qty * self.fee_taker

            net_pnl = gross_pnl - entry_fee - close_fee

            if net_pnl > 0:
                profitable_levels.append(entry)

        if profitable_levels:
            if self.side == "Buy":
                protected_level = min(
                    profitable_levels,
                    key=lambda level: level.price,
                )
            else:
                protected_level = max(
                    profitable_levels,
                    key=lambda level: level.price,
                )

            profitable_levels.remove(protected_level)
            
        return profitable_levels