from pybit.unified_trading import HTTP
import time

from KS.keys import API_KEY, DB_PASSWORD

# Авторизация
session = HTTP(
    api_key=API_KEY,
    api_secret=DB_PASSWORD,
)

category = "linear"  # можно "spot" или "inverse"
symbol_counts = {}

# 1️⃣ Получаем список активных инструментов (чтобы знать символы)
instruments = session.get_instruments_info(category=category)["result"]["list"]
symbols = [x["symbol"] for x in instruments]

# 2️⃣ Проходим по каждому символу
for symbol in symbols:
    try:
        result = session.get_open_orders(category=category, symbol=symbol)
        orders = result.get("result", {}).get("list", [])
        for order in orders:
            if order["orderType"] == "Limit":
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        print(f"Обработан символ: {symbol}")
        #time.sleep(0.1)  # чтобы не спамить API
    except Exception as e:
        print(f"Ошибка по {symbol}: {e}")

# 3️⃣ Вывод
for symbol, count in symbol_counts.items():
    print(f"{symbol}: {count} лимитных ордеров")

total = sum(symbol_counts.values())
print(f"\nИтого лимитных ордеров: {total}")
