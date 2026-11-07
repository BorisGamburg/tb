from dataclasses import dataclass

from services.bb_service import BBService


@dataclass
class SpikeSignalDetails:
    tf: str
    side: str
    price: float
    target: float
    bb_mid: float
    bb_width: float


@dataclass
class SpikeSignalResult:
    ok: bool
    details: SpikeSignalDetails


class SpikeSignal:

    MULTIPLIER = 0.8

    def __init__(self, proxy_driver, symbol: str):
        self.bb_service = BBService(
            proxy_driver=proxy_driver,
            symbol=symbol,
        )

    def check(
        self,
        tf: str,
        side: str,
        price: float,
    ) -> SpikeSignalResult:

        bb = self.bb_service.get_live(tf)

        bb_mid = bb["mid"]
        bb_width = bb["width_abs"]

        offset = bb_width * self.MULTIPLIER

        if side == "Sell":
            target = bb_mid + offset
            signal = price > target

        elif side == "Buy":
            target = bb_mid - offset
            signal = price < target

        else:
            raise RuntimeError(f"Invalid side: {side}")

        details = SpikeSignalDetails(
            tf=tf,
            side=side,
            price=price,
            target=target,
            bb_mid=bb_mid,
            bb_width=bb_width,
        )

        return SpikeSignalResult(
            ok=signal,
            details=details,
        )
