import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic, sleep

import pandas as pd
from pybit.unified_trading import HTTP
from ta.momentum import RSIIndicator

# ---------------- Logging ----------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# Публичные эндпоинты — ключи не нужны
session = HTTP(testnet=False)

# ---------------- Параметры ----------------
RSI_INTERVAL = "D"
RSI_THRESHOLD = 67
MAX_SIZE_THRESHOLD = 0.1          # макс. мин. размер контракта в USDT
MIN_TURNOVER_THRESHOLD = 1_000_000
SIDE = "Sell"
MAX_WORKERS = 8                   # при ошибках rate limit (10006 / 403) уменьшить
MAX_REQUESTS_PER_SEC = 5          # общий лимит запросов свечей на все потоки


# ---------------- Свечи: лимит запросов + повторы ----------------
_rate_lock = threading.Lock()
_next_call_at = 0.0


def _throttle():
    """Не чаще MAX_REQUESTS_PER_SEC запросов в секунду суммарно по всем потокам."""
    global _next_call_at
    interval = 1.0 / MAX_REQUESTS_PER_SEC
    with _rate_lock:
        now = monotonic()
        wait = _next_call_at - now
        _next_call_at = max(now, _next_call_at) + interval
    if wait > 0:
        sleep(wait)


def get_kline_data(symbol, interval, limit=100, attempts=3):
    """Свечи Bybit списком списков (новые → старые); None, если API вернул ошибку."""
    for attempt in range(1, attempts + 1):
        try:
            _throttle()
            response = session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            if response["retCode"] != 0:
                logger.error(f"{symbol}: Bybit kline: {response['retMsg']}")
                return None
            return response["result"]["list"]
        except Exception as e:
            if attempt == attempts:
                raise
            logger.debug(f"{symbol}: kline error {e} (попытка {attempt}/{attempts})")
            sleep(attempt)


# ---------------- ATR ----------------
def get_atr_m1_percent(symbol, window=14):
    """ATR(14) M1 в % от цены (Wilder/RMA)."""
    try:
        klines = get_kline_data(symbol, interval="1", limit=100)
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


# ---------------- RSI ----------------
def get_close_prices(symbol, interval="15", limit=100):
    """Цены закрытия (старые → новые) для расчёта индикаторов."""
    klines = get_kline_data(symbol, interval=interval, limit=limit)
    if klines is None:
        raise Exception("Не удалось получить данные K-line для расчёта цен закрытия.")

    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
    df = df.astype(float)
    df = df[::-1]  # Bybit отдаёт от новых к старым
    return df["close"]


def calculate_last_rsi(symbol, interval="15", limit=200):
    """Рассчитывает RSI как на TradingView с использованием Wilder's RMA."""
    close_prices = get_close_prices(symbol, interval=interval, limit=limit)
    if len(close_prices) < 15:
        raise Exception(f"Недостаточно данных для RSI: получено {len(close_prices)} свечей, требуется минимум 15")

    rsi_indicator = RSIIndicator(close=close_prices, window=14, fillna=False)
    rsi_series = rsi_indicator.rsi()
    last_rsi = rsi_series.iloc[-1]

    if pd.isna(last_rsi):
        raise Exception("RSI не рассчитан")

    return last_rsi


# ---------------- RSI с ретраями ----------------
def fetch_rsi(symbol):
    for attempt in range(3):
        try:
            return symbol, calculate_last_rsi(symbol, interval=RSI_INTERVAL)
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