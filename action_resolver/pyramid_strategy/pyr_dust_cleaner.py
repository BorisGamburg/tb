class PyrDustCleaner:

    DUST_RATIO = 0.6
    PROFIT_BUFFER_PCT = 0.001

    def __init__(
        self,
        symbol: str,
        side: str,
        price_service,
        trading_info,
        logger,
    ):
        self.symbol = symbol
        self.side = side
        self.price_service = price_service
        self.trading_info = trading_info
        self.fee_taker = trading_info.fee_taker
        self.logger = logger

    def find_closeable_level(self, entries):
        # Стек пустой -> выходим
        if not entries:
            return None, 0.0

        # Получаем текущую цену
        close_price = float(
            self.price_service.get_market_close_price(
                symbol=self.symbol,
                side=self.side,
            )
        )

        # Проверяем каждый уровень на dust
        for level in entries:

            if level.initial_qty <= 0 or level.qty <= 0:
                continue

            # Проверяем остаток относительно исходного размера уровня
            if level.qty >= level.initial_qty * self.DUST_RATIO:
                continue

            # Проверяем минимальное количество ордера
            close_qty = self.trading_info.get_valid_order_qty(
                level.qty
            )

            if close_qty <= 0:
                continue

            if not self._is_profitable(level, close_price):
                continue

            self.logger.info(
                f"[PYRAMID DUST] Closeable level found | "
                f"price={level.price} | "
                f"qty={level.qty} | "
                f"initial_qty={level.initial_qty} | "
                f"close_price={close_price}"
            )

            return level, close_qty

        return None, 0.0

    def _is_profitable(self, level, close_price):

        # Комиссия открытия на единицу исходного количества
        entry_fee_per_unit = (
            level.fee / level.initial_qty
        )

        if self.side == "Buy":

            breakeven_price = (
                level.price + entry_fee_per_unit
            ) / (1 - self.fee_taker)

            min_close_price = (
                breakeven_price *
                (1 + self.PROFIT_BUFFER_PCT)
            )

            return close_price >= min_close_price

        if self.side == "Sell":

            breakeven_price = (
                level.price - entry_fee_per_unit
            ) / (1 + self.fee_taker)

            max_close_price = (
                breakeven_price *
                (1 - self.PROFIT_BUFFER_PCT)
            )

            return close_price <= max_close_price

        raise ValueError(
            f"Unsupported side: {self.side}"
        )