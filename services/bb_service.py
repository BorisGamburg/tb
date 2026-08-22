class BBService:

    def __init__(
        self,
        proxy_driver,
        symbol,
    ):
        self.proxy_driver = proxy_driver
        self.symbol = symbol

    def get_last_closed(
        self,
        tf: str,
    ):

        data = self.proxy_driver.get_bb_ohlc(
            self.symbol,
            tf,
        )
        bb = data.get("bb")

        if not bb:
            raise RuntimeError(
                f"BB data empty tf={tf}"
            )

        if len(bb) < 2:
            raise RuntimeError(
                f"Not enough BB history tf={tf}"
            )

        # closed candle
        last = bb[-2]

        upper = last.get("high")
        lower = last.get("low")
        mid = last.get("mid")

        if (
            upper is None
            or lower is None
            or mid is None
        ):
            raise RuntimeError(
                f"Invalid BB values tf={tf}"
            )

        width_abs = upper - lower

        if width_abs <= 0:
            raise RuntimeError(
                f"Invalid BB width tf={tf} "
                f"width={width_abs}"
            )

        if mid <= 0:
            raise RuntimeError(
                f"Invalid BB mid tf={tf} "
                f"mid={mid}"
            )

        width_ratio = width_abs / mid

        return {
            "upper": upper,
            "lower": lower,
            "mid": mid,
            "width_abs": width_abs,
            "width_ratio": width_ratio,
        }