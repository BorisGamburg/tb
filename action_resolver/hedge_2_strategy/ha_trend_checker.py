class HATrendChecker:

    def __init__(
        self,
        proxy_driver,
        symbol: str,
        side: str,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side

    def _get_closed_ha_color(self, tf: str) -> str:

        ha = self.proxy_driver.get_ha(
            symbol=self.symbol,
            tf=tf
        )

        if not ha or "prev1" not in ha:
            raise RuntimeError(
                f"Invalid HA data | symbol={self.symbol} tf={tf}"
            )

        color = ha["prev1"]["color"]

        VALID = ("green", "red", "doji")

        if color not in VALID:
            raise RuntimeError(
                f"Invalid HA color: {color}"
            )

        return color
    
    def is_active(self, tf: str) -> bool:
        color = self._get_closed_ha_color(tf)

        if self.side == "Buy":
            return color == "green"

        return color == "red"    