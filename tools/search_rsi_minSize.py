import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import sleep

import pandas as pd
from pybit.unified_trading import HTTP

from prog.drivers.bybit_driver import BybitDriver
from prog.managers.account_loader import load_account
from prog.utils.telegram import Telegram

# ---------------- Logging ----------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# ---------------- Account / Telegram ----------------
ACCOUNT_NAME = "bybit_live"
account = load_account(ACCOUNT_NAME)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "data" / "config"
TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram_config.txt"
telegram = Telegram(logger=logger, config_file=TELEGRAM_CONFIG_PATH)

bybit_driver = BybitDriver(
    demo=account.demo,
    api_key=account.api_key,
    api_secret=account.api_secret,
    logger=logger,
    telegram=telegram,
)

# Публичные эндпоинты — ключи не нужны
session = HTTP(testnet=False)

# ---------------- Параметры ----------------
RSI_INTERVAL = "D"
RSI_THRESHOLD = 67
MAX_SIZE_THRESHOLD = 0.3          # макс. мин. размер контракта в USDT
MIN_TURNOVER_THRESHOLD = 1_000_000
SIDE = "Sell"
MAX_WORKERS = 8                   # при ошибках rate limit (10006 / 403) уменьшить


# ---------------- ATR ----------------
def get_atr_m1_percent(symbol, window=14):
    """ATR(14) M1 в % от цены (Wilder/RMA)."""
    try:
        klines = bybit_driver.get_kline_data(symbol, interval="1", limit=100)
        if not klines:
            return None

        df = pd.DataFrame(klines, columns=['ts', 'o', 'h', 'l', 'c', 'v', 't'])
        df[['h', 'l', 'c']] = df[['h', 'l', 'c']].astype(float)
        df = df.iloc[::-1].iloc[:-1]  # старые → новые, без незакрытой свечи

        close_prev = df['c'].shift(1)
        tr = pd.concat([
            df['h'] - df['l'],
            (df['h'] - close_prev).abs(),
            (df['l'] - close_prev).abs(),
        ], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1 / window, adjust=False).mean()
        last_price = df['c'].iloc[-1]
        if last_price == 0:
            return None
        return atr.iloc[-1] / last_price * 100
    except Exception:
        return None


# ---------------- Универсум: 2 запроса вместо ~1200 ----------------
def load_universe():
    """
    Возвращает {symbol: {"min_size_usdt", "turnover", "price"}}
    для всех USDT-перпетуалов в статусе Trading.
    Всё берём пакетно: инструменты (minOrderQty) + тикеры (цена, оборот).
    """
    min_qty = {}
    cursor = None
    while True:
        params = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        resp = session.get_instruments_info(**params)
        if resp["retCode"] != 0:
            raise RuntimeError(f"instruments: {resp['retMsg']}")
        for s in resp["result"]["list"]:
            if (s["contractType"] == "LinearPerpetual"
                    and s["quoteCoin"] == "USDT"
                    and s["status"] == "Trading"):
                min_qty[s["symbol"]] = float(s["lotSizeFilter"]["minOrderQty"])
        cursor = resp["result"].get("nextPageCursor")
        if not cursor:
            break

    resp = session.get_tickers(category="linear")  # без symbol → все тикеры сразу
    if resp["retCode"] != 0:
        raise RuntimeError(f"tickers: {resp['retMsg']}")

    universe = {}
    for t in resp["result"]["list"]:
        sym = t["symbol"]
        if sym not in min_qty:
            continue
        try:
            price = float(t["lastPrice"])
            turnover = float(t["turnover24h"])
        except (TypeError, ValueError):
            continue
        universe[sym] = {
            "min_size_usdt": min_qty[sym] * price,
            "turnover": turnover,
            "price": price,
        }
    return universe


# ---------------- RSI с ретраями ----------------
def fetch_rsi(symbol):
    for attempt in range(3):
        try:
            return symbol, bybit_driver.calculate_last_rsi(symbol, interval=RSI_INTERVAL)
        except Exception as e:
            logger.debug(f"{symbol}: RSI error {e}")
            sleep(0.5 * (attempt + 1))
    return symbol, None


def rsi_ok(rsi):
    return rsi < RSI_THRESHOLD if SIDE == "Buy" else rsi > RSI_THRESHOLD


def main():
    universe = load_universe()
    total = len(universe)

    # Дешёвые фильтры — ДО дорогого запроса RSI
    candidates = [
        s for s, d in universe.items()
        if d["min_size_usdt"] < MAX_SIZE_THRESHOLD and d["turnover"] >= MIN_TURNOVER_THRESHOLD
    ]

    print("side=", SIDE)
    print(f"rsi_interval={RSI_INTERVAL}")
    print(f"rsi_threshold={RSI_THRESHOLD}")
    print(f"max_size_threshold={MAX_SIZE_THRESHOLD}")
    print(f"min_turnover_threshold={MIN_TURNOVER_THRESHOLD:,} USDT")
    print(f"Инструментов: {total}, после фильтров размера/оборота: {len(candidates)}\n")

    results = []
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(fetch_rsi, s) for s in candidates]
            for fut in as_completed(futures):
                done += 1
                if done % 10 == 0:
                    print(f"\r{done}/{len(candidates)}", end="")
                symbol, rsi = fut.result()
                if rsi is not None and rsi_ok(rsi):
                    results.append((symbol, rsi))
    except KeyboardInterrupt:
        print("\nПрервано пользователем")

    print()
    # ATR — только для финалистов (их немного)
    for symbol, rsi in sorted(results, key=lambda x: x[1], reverse=(SIDE == "Sell")):
        d = universe[symbol]
        atr_pct = get_atr_m1_percent(symbol)
        atr_display = f"{atr_pct:.3f}%" if atr_pct is not None else "N/A"
        print(f"{symbol} - RSI: {rsi}, Price={d['price']}, Turnover 24h USDT: {int(d['turnover']):,}")
        print(f"ATR(M1)%: {atr_display} | Мин. контракт: {d['min_size_usdt']:.4f} USDT\n")


if __name__ == "__main__":
    main()