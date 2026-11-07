from dataclasses import dataclass


@dataclass
class HAReversDetails:
    tf: str
    side: str
    price: float
    level: float


@dataclass
class HAReversResult:
    ok: bool
    details: HAReversDetails


class HAReversalSignal:

    def __init__(self, proxy_driver, symbol: str):
        self.proxy_driver = proxy_driver
        self.symbol = symbol

    def is_entry(self, tf: str, side: str, price: float) -> HAReversResult:
        """
        Вход по пробою границы последней закрытой HA свечи.
        Sell: цена ниже HA_low последней закрытой свечи.
        Buy: цена выше HA_high последней закрытой свечи.
        """
        last_closed = self._get_last_closed(tf)

        if side == "Sell":
            level = float(last_closed["HA_low"])
            signal = price < level
        elif side == "Buy":
            level = float(last_closed["HA_high"])
            signal = price > level
        else:
            raise RuntimeError(f"Invalid side: {side}")

        details = HAReversDetails(
            tf=tf,
            side=side,
            price=price,
            level=level,
        )

        return HAReversResult(
            ok=signal,
            details=details,
        )

    def _get_last_closed(self, tf: str) -> dict:
        ha = self.proxy_driver.get_ha(
            symbol=self.symbol,
            tf=tf,
        )

        if not ha or "prev1" not in ha:
            raise RuntimeError("Invalid HA data")

        return ha["prev1"]
