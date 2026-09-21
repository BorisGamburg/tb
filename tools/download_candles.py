import os
import sys
import requests
import csv


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


def save_csv(
    filename,
    candles,
):
    with open(
        filename,
        "w",
        newline="",
    ) as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ]
        )

        writer.writerows(candles)


def main():

    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "    python download_candles.py SYMBOL DAYS"
        )
        return

    symbol = sys.argv[1].upper()
    days = int(sys.argv[2])

    os.makedirs(
        "data",
        exist_ok=True,
    )

    filename = (
        f"data/{symbol}_1m_{days}d.csv"
    )

    print(f"Symbol   : {symbol}")
    print(f"Days     : {days}")
    print(f"Output   : {filename}")

    candles = load_candles(
        symbol=symbol,
        days=days,
    )

    candles = list(reversed(candles))

    save_csv(
        filename,
        candles,
    )

    print()
    print(f"Downloaded candles: {len(candles)}")
    print(f"Saved to           : {filename}")


if __name__ == "__main__":
    main()