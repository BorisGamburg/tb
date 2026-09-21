import requests
from datetime import datetime, UTC

url = "https://api.bybit.com/v5/market/kline"

# ==========================================
# ЗАПРОС 1: Последние 5 свечей на данный момент
# ==========================================
params_1 = {
    "category": "linear",
    "symbol": "BTCUSDT",
    "interval": "1",
    "limit": 5,
}

r1 = requests.get(url, params=params_1)
r1.raise_for_status()
data_1 = r1.json()

print("--- ПЕРВЫЙ ЗАПРОС (Последние 5 свечей) ---")
candles_1 = data_1["result"]["list"]

for candle in candles_1:
    ts = int(candle[0])
    dt = datetime.fromtimestamp(ts / 1000, UTC)
    print(f"{dt:%Y-%m-%d %H:%M:%S} UTC")

# Находим таймстамп самой старой свечи из первой пачки
# Это последний элемент в списке candles_1
oldest_candle_ts = int(candles_1[-1][0])

# ==========================================
# ЗАПРОС 2: 5 свечей, которые были ДО первой пачки
# ==========================================
# Передаем этот таймстамп в параметр "end". 
# Чтобы не продублировать самую старую свечу, вычитаем 1 миллисекунду (или 60000 мс для 1-минутного интервала)
params_2 = {
    "category": "linear",
    "symbol": "BTCUSDT",
    "interval": "1",
    "limit": 5,
    "end": oldest_candle_ts - 1, 
}

r2 = requests.get(url, params=params_2)
r2.raise_for_status()
data_2 = r2.json()

print("\n--- ВТОРОЙ ЗАПРОС (5 свечей перед ними) ---")
for candle in data_2["result"]["list"]:
    ts = int(candle[0])
    dt = datetime.fromtimestamp(ts / 1000, UTC)
    print(f"{dt:%Y-%m-%d %H:%M:%S} UTC")