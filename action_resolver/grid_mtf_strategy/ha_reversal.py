from rich.text import Text
from dataclasses import dataclass


@dataclass
class HAReversDetails:
    tf: str
    side: str
    price: float       # текущая цена
    level: float       # граница последней закрытой HA свечи (HA_low / HA_high)

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
        Buy:  цена выше HA_high последней закрытой свечи.

        Состояния нет: от повторных входов защищает проверка дистанции
        от последнего открытого уровня.
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

        ha_revers_details = HAReversDetails(
            tf=tf,
            side=side,
            price=price,
            level=level,
        )

        return HAReversResult(
            ok=signal,
            details=ha_revers_details,
        )

    def is_exit(self, tf: str, side: str) -> tuple[bool, Text]:
        prev, curr, live = self._get_prev_curr_live(tf)

        if side == "Sell":
            signal = (
                prev == "red"
                and curr == "green"
                and live == "green"
            )
        elif side == "Buy":
            signal = (
                prev == "green"
                and curr == "red"
                and live == "red"
            )
        else:
            raise RuntimeError(f"Invalid side: {side}")  
        
        return signal, self._build_message(
            signal,
            tf,
            prev,
            curr,
        )

    def _build_message(
        self,
        signal: bool,
        tf: str,
        prev: str,
        curr: str,
    ) -> Text:
        state = "PASS" if signal else "BLOCK"

        message = Text()
        message.append(
            state,
            style="black on green" if signal else "white on red",
        )
        message.append(f"({tf}m) [{prev}→{curr}]")

        return message      

    def _get_prev_curr_live(self, tf: str):

        ha = self.proxy_driver.get_ha(
            symbol=self.symbol,
            tf=tf
        )

        if (
            not ha
            or "prev2" not in ha
            or "prev1" not in ha
            or "curr" not in ha
        ):
            raise RuntimeError("Invalid HA data")

        prev = ha["prev2"]["color"]
        curr = ha["prev1"]["color"]
        live = ha["curr"]["color"]

        return prev, curr, live

    def _get_last_closed(self, tf: str) -> dict:

        ha = self.proxy_driver.get_ha(
            symbol=self.symbol,
            tf=tf
        )

        if not ha or "prev1" not in ha:
            raise RuntimeError("Invalid HA data")

        return ha["prev1"]