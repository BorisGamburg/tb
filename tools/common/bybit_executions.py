import time

import pandas as pd
from pybit.unified_trading import HTTP

from common.account_loader import load_account


ACCOUNT_NAME = "bybit_live"

account = load_account(ACCOUNT_NAME)

session = HTTP(
    testnet=account.demo,
    api_key=account.api_key,
    api_secret=account.api_secret,
)


def get_full_history_by_weeks(symbol, period_days):
    all_trades = []

    MS_IN_DAY = 24 * 60 * 60 * 1000
    WINDOW_SIZE = 7 * MS_IN_DAY

    start_search = int(
        (time.time() - period_days * 24 * 60 * 60) * 1000
    )
    now = int(time.time() * 1000)

    current_start = start_search

    print("Начинаю сканирование истории по 7 дней...")

    while current_start < now:
        date_str = time.strftime(
            "%Y-%m-%d",
            time.localtime(current_start / 1000),
        )
        print(f"date: {date_str}")

        current_end = min(current_start + WINDOW_SIZE, now)
        cursor = None

        while True:
            response = session.get_executions(
                category="linear",
                symbol=symbol,
                startTime=current_start,
                endTime=current_end,
                limit=100,
                cursor=cursor,
            )

            if response["retCode"] == 0:
                trades = response["result"]["list"]

                if trades:
                    print(f"  Получено сделок: {len(trades)}")
                    all_trades.extend(trades)

                cursor = response["result"].get("nextPageCursor")
                if not cursor:
                    break
            else:
                print(f"Ошибка API: {response['retMsg']}")
                break

        current_start = current_end + 1

    return pd.DataFrame(all_trades)


def get_ticker_price(symbol):
    response = session.get_tickers(
        category="linear",
        symbol=symbol,
    )
    return float(response["result"]["list"][0]["lastPrice"])