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
        Вход при развороте: откат и пробой границы последней закрытой HA свечи.
        Buy: HA_high prev1 ниже HA_high prev2 (откат)
             и цена выше HA_high prev1 (пробой).
        Sell: HA_low prev1 выше HA_low prev2 (откат)
              и цена ниже HA_low prev1 (пробой).
        В устойчивом движении сигнала нет. Пока цена за границей prev1,
        сигнал сохраняется.
        """
        prev1, prev2 = self._get_last_closed(tf)

        if side == "Sell":
            level = float(prev1["HA_low"])
            pullback = level > float(prev2["HA_low"])
            signal = pullback and price < level
        elif side == "Buy":
            level = float(prev1["HA_high"])
            pullback = level < float(prev2["HA_high"])
            signal = pullback and price > level
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

    def _get_last_closed(self, tf: str) -> tuple[dict, dict]:
        """Две последние закрытые HA свечи: (prev1, prev2)."""
        ha = self.proxy_driver.get_ha(
            symbol=self.symbol,
            tf=tf,
        )

        if not ha or "prev1" not in ha or "prev2" not in ha:
            raise RuntimeError("Invalid HA data")

        return ha["prev1"], ha["prev2"]