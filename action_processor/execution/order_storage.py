class OrderStorage:
    def __init__(
        self,
        dsn: str,
        bot: str,
    ):
        self.dsn = dsn
        self.bot = bot

    def save_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        status: str,
        filled_qty: float,
        avg_price: float,
        fee: float,
    ) -> None:
        import psycopg2

        conn = psycopg2.connect(self.dsn)

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bot_orders (
                        order_id,
                        bot,
                        symbol,
                        side,
                        status,
                        filled_qty,
                        avg_price,
                        fee
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (order_id) DO UPDATE SET
                        bot = EXCLUDED.bot,
                        symbol = EXCLUDED.symbol,
                        side = EXCLUDED.side,
                        status = EXCLUDED.status,
                        filled_qty = EXCLUDED.filled_qty,
                        avg_price = EXCLUDED.avg_price,
                        fee = EXCLUDED.fee,
                        saved_at = now()
                    """,
                    (
                        order_id,
                        self.bot,
                        symbol,
                        side,
                        status,
                        filled_qty,
                        avg_price,
                        fee,
                    ),
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()