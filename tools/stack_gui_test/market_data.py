from pybit.unified_trading import HTTP


def get_candles(symbol: str, interval: str, limit: int = 100):
    client = HTTP()

    response = client.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit,
    )

    if response["retCode"] != 0:
        raise RuntimeError(response["retMsg"])

    return [
        (
            int(candle[0]),      # timestamp, ms
            float(candle[1]),    # open
            float(candle[2]),    # high
            float(candle[3]),    # low
            float(candle[4]),    # close
        )
        for candle in reversed(response["result"]["list"])
    ]