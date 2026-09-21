import requests
from statistics import mean
from datetime import datetime, UTC  # Добавили для вывода времени при проверке
import numpy as np


def get_klines(
    symbol,
    interval,
    limit,
    end=None,
):
    url = "https://api.bybit.com/v5/market/kline"

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    if end is not None:
        params["end"] = end

    r = requests.get(url, params=params)
    r.raise_for_status()

    data = r.json()

    if data["retCode"] != 0:
        raise RuntimeError(data)

    return data["result"]["list"]


def percentile(values, p):
    if not values:
        return 0.0

    values = sorted(values)

    idx = (len(values) - 1) * p / 100.0

    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)

    frac = idx - lo

    return (
        values[lo] * (1.0 - frac)
        + values[hi] * frac
    )

def percentile_np(values, p):
    if not values:
        return 0.0
    return float(np.percentile(values, p))


def load_candles(
    symbol,
    days,
):
    target_candles = days * 24 * 60

    candles = []
    end = None
    
    # ----------------------------

    while len(candles) < target_candles:

        # запрашиваем по 1000 свечей
        part = get_klines(
            symbol=symbol,
            interval="1",
            limit=1000, 
            end=end,
        )

        if not part:
            break

        candles.extend(part)
        
        print(
            f"\rLoaded {len(candles):6d} / {target_candles}",
            end="",
            flush=True,
        )
        if len(part) < 1000:
            break

        end = int(part[-1][0]) - 1

    print()

    # Возвращаем все накопленные свечи (ровно 15 штук) без срезов
    return candles[:target_candles]  # Вернули срез до целевого количества

def analyze(
    symbol,
    days,
):
    candles = load_candles(
        symbol=symbol,
        days=days,
    )

    if not candles:
        print("No candles loaded.")
        return

    ranges = []

    max_range = -1
    max_candle = None

    for c in candles:

        open_price = float(c[1])
        high = float(c[2])
        low = float(c[3])

        if open_price <= 0:
            continue

        range_pct = (
            (high - low)
            / open_price
            * 100.0
        )

        if range_pct > max_range:
            max_range = range_pct
            max_candle = c

        ranges.append(range_pct)

    print()
    print("=" * 50)
    print(f"SYMBOL : {symbol}")
    print(f"PERIOD : {days} days")
    print(f"CANDLES: {len(ranges)}")
    print("=" * 50)
    print()

    print(f"Maximum range      : {max(ranges):8.3f}%")
    print(f"99.99 percentile   : {percentile(ranges, 99.99):8.3f}%")
    #print(f"99.99 numpy        : {percentile_np(ranges, 99.99):8.3f}%")
    print(f"99.90 percentile   : {percentile(ranges, 99.90):8.3f}%")
    print(f"99.00 percentile   : {percentile(ranges, 99.00):8.3f}%")
    print(f"97.50 percentile   : {percentile(ranges, 97.50):8.3f}%")
    print(f"95.00 percentile   : {percentile(ranges, 95.00):8.3f}%")
    print(f"Average range      : {mean(ranges):8.3f}%")

    print()


    bins = [
        (0, 3),
        (3, 8),
        (8, 15),
        (15, 25),
        (25, 50),
        (50, float("inf")),
    ]

    print("Range distribution")
    print("-" * 40)

    total = len(ranges)

    for lo, hi in bins:

        if hi == float("inf"):
            count = sum(r >= lo for r in ranges)
            label = f">{lo}%"
        else:
            count = sum(lo <= r < hi for r in ranges)
            label = f"{lo}-{hi}%"

        percent = count / total * 100

        print(f"{label:8} : {count:7d} ({percent:6.3f}%)")

    print()


    print("\n--- MAX RANGE CANDLE ---")

    ts = int(max_candle[0])
    dt = datetime.fromtimestamp(ts / 1000, UTC)

    print(f"Time : {dt:%Y-%m-%d %H:%M:%S} UTC")
    print(f"Open : {float(max_candle[1])}")
    print(f"High : {float(max_candle[2])}")
    print(f"Low  : {float(max_candle[3])}")
    print(f"Close: {float(max_candle[4])}")
    print(f"Range: {max_range:.3f}%")    


if __name__ == "__main__":

    analyze(
        symbol="DYDXUSDT",
        days=400,
    )