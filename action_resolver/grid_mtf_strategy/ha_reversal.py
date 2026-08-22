from rich.text import Text


class HAReversalSignal:
    def __init__(self, proxy_driver, symbol: str):
        self.proxy_driver = proxy_driver
        self.symbol = symbol

    def is_entry(self, tf: str, side: str) -> tuple[bool, Text]:
        prev, curr, live = self._get_prev_curr_live(tf)

        if side == "Sell":
            signal = (
                prev == "green"
                and curr == "red"
                and live == "red"
            )
        elif side == "Buy":
            signal = (
                prev == "red"
                and curr == "green"
                and live == "green"
            )
        else:
            raise RuntimeError(f"Invalid side: {side}")

        return signal, self._build_message(
            signal,
            tf,
            prev,
            curr,
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