import requests
import time
import json
import collections

# --- НАСТРОЙКИ ХИЩНИКА ---
WINDOW_SIZE = 10         # Размер окна в минутах (анализируем последние 10 минут)
VOL_MULTIPLIER = 4       # Во сколько раз объем за окно должен превышать норму
PRICE_DEVIATION = 0.15    # Макс. отклонение цены за все время окна (в процентах)
MIN_24H_VOLUME = 5000000 # Игнорируем монеты с суточным объемом ниже 5 млн $
FILE_NAME = "priority_coins.json"

# Хранилище для истории: { "BTCUSDT": deque([price1, price2, ...], maxlen=10) }
history = collections.defaultdict(lambda: collections.deque(maxlen=WINDOW_SIZE))
vol_history = collections.defaultdict(lambda: collections.deque(maxlen=WINDOW_SIZE))

def get_market_data():
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        resp = requests.get(url, timeout=10).json()
        return resp['result']['list']
    except Exception as e:
        print(f"Ошибка связи: {e}")
        return []

def scout():
    print(f"\n[{time.strftime('%H:%M:%S')}] Сканирую рынок Bybit...")
    tickers = get_market_data()
    detected_targets = []

    for t in tickers:
        symbol = t['symbol']
        if not symbol.endswith('USDT'): continue
        
        last_price = float(t['lastPrice'])
        turnover_24h = float(t['turnover24h']) # Объем в USDT за 24ч
        
        if turnover_24h < MIN_24H_VOLUME: continue

        # Сохраняем текущую цену и текущий суточный оборот
        history[symbol].append(last_price)
        vol_history[symbol].append(turnover_24h)

        # Ждем, пока накопится история для анализа окна
        if len(history[symbol]) < WINDOW_SIZE:
            continue

        # --- АНАЛИЗ ОКНА ---
        prices = list(history[symbol])
        vols = list(vol_history[symbol])

        # 1. Считаем реальный объем, зашедший за WINDOW_SIZE минут
        # (Разница между текущим оборотом и тем, что был 10 минут назад)
        volume_in_window = vols[-1] - vols[0]
        
        # 2. Считаем "норму" объема для этого отрезка времени
        avg_window_vol = (turnover_24h / 1440) * WINDOW_SIZE
        
        # 3. Считаем разброс цены в окне (High - Low)
        p_max, p_min = max(prices), min(prices)
        price_range_pct = ((p_max - p_min) / p_min) * 100

        # --- КРИТЕРИЙ ОГРАБЛЕНИЯ ---
        # Объем за 10 минут в N раз выше нормы И цена почти не шелохнулась
        if volume_in_window > (avg_window_vol * VOL_MULTIPLIER) and price_range_pct < PRICE_DEVIATION:
            detected_targets.append({
                "symbol": symbol,
                "vol_boost": round(volume_in_window / avg_window_vol, 1),
                "range": round(price_range_pct, 3)
            })
            print(f"!!! КИТ В СЕТИ: {symbol} | Объем: x{round(volume_in_window / avg_window_vol, 1)} | Диапазон: {round(price_range_pct, 3)}%")

    # Сохраняем результаты для основного бота
    if detected_targets:
        with open(FILE_NAME, 'w') as f:
            json.dump({
                "updated_at": time.time(),
                "targets": [t['symbol'] for t in detected_targets]
            }, f)
    else:
        # Если аномалий нет, очищаем файл или пишем пустой список
        with open(FILE_NAME, 'w') as f:
            json.dump({"updated_at": time.time(), "targets": []}, f)

if __name__ == "__main__":
    print("Bloodhound запущен. Ищу следы китов по всей крипте...")
    while True:
        try:
            scout()
        except Exception as e:
            print(f"Критическая ошибка: {e}")
        time.sleep(60) # Частота сканирования - раз в минуту