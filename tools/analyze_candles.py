import csv
import sys
from statistics import mean
from datetime import datetime, UTC


def load_csv(
    filename,
):
    candles = []

    with open(
        filename,
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            candles.append(
                [
                    row["timestamp"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["turnover"],
                ]
            )

    return candles

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

def calc_statistics(
    candles,
):
    ranges = []

    extreme = []

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

        if range_pct >= 8.0:

            body_pct = (
                (float(c[4]) - open_price)
                / open_price
                * 100.0
            )

            if body_pct > 0:
                direction = "UP"
            elif body_pct < 0:
                direction = "DOWN"
            else:
                direction = "DOJI"

            extreme.append(
                (
                    range_pct,
                    body_pct,
                    direction,
                    c,
                )
            )

        if range_pct > max_range:
            max_range = range_pct
            max_candle = c

        ranges.append(range_pct)

    return {
        "ranges": ranges,
        "extreme": extreme,
        "max_range": max_range,
        "max_candle": max_candle,
    }

def print_statistics(
    filename,
    ranges,
):
    print()
    print("=" * 50)
    print(f"FILE    : {filename}")
    print(f"CANDLES : {len(ranges)}")
    print("=" * 50)
    print()

    print(f"Maximum range      : {max(ranges):8.3f}%")
    print(f"99.99 percentile   : {percentile(ranges, 99.99):8.3f}%")
    print(f"99.90 percentile   : {percentile(ranges, 99.90):8.3f}%")
    print(f"99.00 percentile   : {percentile(ranges, 99.00):8.3f}%")
    print(f"97.50 percentile   : {percentile(ranges, 97.50):8.3f}%")
    print(f"95.00 percentile   : {percentile(ranges, 95.00):8.3f}%")
    print(f"Average range      : {mean(ranges):8.3f}%")

    print()


def print_max_candle(max_range, max_candle):
    print("\n--- MAX RANGE CANDLE ---")

    ts = int(max_candle[0])
    dt = datetime.fromtimestamp(ts / 1000, UTC)

    print(f"Time : {dt:%Y-%m-%d %H:%M:%S} UTC")
    print(f"Open : {float(max_candle[1])}")
    print(f"High : {float(max_candle[2])}")
    print(f"Low  : {float(max_candle[3])}")
    print(f"Close: {float(max_candle[4])}")
    print(f"Range: {max_range:.3f}%")

def print_distribution(ranges):
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

def print_extreme_candles(
    extreme,
):
    print("\nExtreme candles (>= 8%)")
    print("-" * 110)

    print(
        f"{'Time':19}"
        f"{'Range':>10}"
        f"{'Body':>10}"
        f"{'Dir':>8}"
        f"{'Open':>12}"
        f"{'High':>12}"
        f"{'Low':>12}"
        f"{'Close':>12}"
    )

    for range_pct, body_pct, direction, c in sorted(
        extreme,
        reverse=True,
    ):

        ts = int(c[0])
        dt = datetime.fromtimestamp(ts / 1000, UTC)

        print(
            f"{dt:%Y-%m-%d %H:%M} "
            f"{range_pct:9.2f}% "
            f"{body_pct:9.2f}% "
            f"{direction:>6} "
            f"{float(c[1]):12.6f}"
            f"{float(c[2]):12.6f}"
            f"{float(c[3]):12.6f}"
            f"{float(c[4]):12.6f}"
        )

    print()

def analyze(
    filename,
):
    candles = load_csv(
        filename,
    )

    if not candles:
        print("No candles loaded.")
        return

    stats = calc_statistics(
        candles,
    )

    ranges = stats["ranges"]
    extreme = stats["extreme"]
    max_range = stats["max_range"]
    max_candle = stats["max_candle"]

    print_statistics(
        filename,
        ranges,
    )

    print_distribution(ranges)

    print_max_candle(max_range, max_candle)

    print_extreme_candles(extreme)

    
def main():

    if len(sys.argv) != 2:
        print(
            "Usage:\n"
            "    python analyze_candles.py FILE"
        )
        return

    filename = sys.argv[1]

    analyze(filename)    


if __name__ == "__main__":
    main()