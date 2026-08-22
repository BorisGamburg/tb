import time

from pybit.unified_trading import WebSocket


class BybitWS:
    def __init__(self, testnet: bool = False):
        self._callback = None

        self._ws = WebSocket(
            channel_type="linear",
            testnet=testnet,
        )

    def subscribe_ticker(self, symbol):
        print(f"subscribe: BybitWS id={id(self)}")

        self._ws.ticker_stream(
            symbol=symbol,
            callback=self._on_ticker,
        )

    def unsubscribe_ticker(self, symbol: str, timeout: float = 5.0) -> bool:
        topic = f"tickers.{symbol}"

        self._ws.unsubscribe(topic)

        deadline = time.time() + timeout

        while time.time() < deadline:
            if topic not in self._ws.get_subscription_topics():
                return True

            time.sleep(0.5)

        return False

    def set_callback(self, callback):
        self._callback = callback

    def _on_ticker(self, message):
        data = message["data"]

        self._callback(
            symbol=data["symbol"],
            bid=float(data["bid1Price"]),
            ask=float(data["ask1Price"]),
            last=float(data["lastPrice"]),
        )