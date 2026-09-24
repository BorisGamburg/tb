from pybit.unified_trading import HTTP
from prog.drivers.bybit_driver import BybitDriver
from prog.utils.telegram import Telegram
import pandas as pd
import logging
from pathlib import Path
from time import sleep
from prog.managers.account_loader import load_account

# Logging Setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# Account
ACCOUNT_NAME = "bybit_live"
account = load_account(ACCOUNT_NAME)

# Telegram Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "data" / "config"
TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram_config.txt"
telegram = Telegram(logger=logger, config_file=TELEGRAM_CONFIG_PATH)

# Create an instance of the BybitDriver
bybit_driver = BybitDriver(
    demo=account.demo,
    api_key=account.api_key,
    api_secret=account.api_secret,
    logger=logger,
    telegram=telegram,
)

# Инициализация клиента Bybit
session = HTTP(
    testnet=False,  # Укажите True для тестовой сети
    api_key="ВАШ_API_КЛЮЧ",  # Замените на ваш API ключ (опционально)
    api_secret="ВАШ_API_СЕКРЕТ"  # Замените на ваш API секрет (опционально)
)

turnover_24h=None

def get_atr_m1_percent(symbol, window=14):
    """
    ATR(14) M1 в процентах от цены.
    Реализация Wilder (как у Bybit / TradingView)
    """
    try:
        klines = bybit_driver.get_kline_data(symbol, interval="1", limit=100)

        if not klines:
            return None

        df = pd.DataFrame(klines, columns=['ts','o','h','l','c','v','t'])
        df[['h','l','c']] = df[['h','l','c']].astype(float)

        # порядок: старые → новые
        df = df.iloc[::-1]

        # удаляем текущую незакрытую свечу
        df = df.iloc[:-1]

        high = df['h']
        low = df['l']
        close_prev = df['c'].shift(1)

        tr = pd.concat([
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs()
        ], axis=1).max(axis=1)

        # Wilder ATR (RMA)
        atr = tr.ewm(alpha=1/window, adjust=False).mean()

        atr_value = atr.iloc[-1]
        last_price = df['c'].iloc[-1]

        if last_price == 0:
            return None

        return (atr_value / last_price) * 100

    except Exception:
        return None

# Функция для получения всех бессрочных USDT-перпетуалов
def get_perpetual_tokens():
    try:
        # Запрос списка торговых пар для категории linear (USDT-перпетуалы)
        response = session.get_instruments_info(category="linear")
        
        
        # Проверка успешности запроса
        if response['retCode'] == 0:
            symbols = response['result']['list']
            # Извлекаем только символы (торговые пары)
            token_list = [symbol['symbol'] for symbol in symbols]
            return token_list
        else:
            print(f"Ошибка API: {response['retMsg']}")
            return []
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return []
    
def get_min_size_in_usdt(symbol, category="linear"):
    """
    Получает текущую цену, минимальный размер контракта и вычисляет мин. размер в USDT.
    
    :param symbol: Символ, например "BTCUSDT"
    :param category: Тип продукта, "linear" для USDT-контрактов
    :return: Минимальный размер в USDT или None, если ошибка
    """

    global turnover_24h

    try:
        # 1. Запрос текущей цены (lastPrice)
        ticker_response = session.get_tickers(
            category=category,
            symbol=symbol
        )
        
        if ticker_response['retCode'] != 0:
            print(f"Ошибка при получении цены: {ticker_response['retMsg']}")
            return None
        
        ticker = ticker_response['result']['list'][0]
        last_price = float(ticker['lastPrice'])
        turnover_24h = float(ticker['turnover24h'])
        
        # 2. Запрос информации об инструменте (minOrderQty)
        instrument_response = session.get_instruments_info(
            category=category,
            symbol=symbol
        )
        
        if instrument_response['retCode'] != 0:
            print(f"Ошибка при получении инструмента: {instrument_response['retMsg']}")
            return None
        
        instrument = instrument_response['result']['list'][0]
        lot_size_filter = instrument['lotSizeFilter']
        min_order_qty = float(lot_size_filter['minOrderQty'])
        
        # 3. Вычисление минимального размера в USDT
        min_size_usdt = min_order_qty * last_price
        
        # Вывод результатов
        # print(f"Символ: {symbol}")
        # print(f"Текущая цена (lastPrice): {last_price}")
        # print(f"Минимальный размер контракта (minOrderQty): {min_order_qty}")
        # print(f"Минимальный размер в USDT (minOrderQty * price): {min_size_usdt}")
        
        return min_size_usdt
        
    except Exception as e:
        print(f"Исключение: {e}")
        return None


# Получение списка токенов
tokens = get_perpetual_tokens()

# Вывод списка токенов
if tokens:
    rsi_interval = "D"
    rsi_threshold = 60
    mах_size_threshold = 0.1
    min_turnover_threshold = 1000000
    side = "Sell"

    print("side=", side)
    print(f"rsi_interval={rsi_interval}")
    print(f"rsi_threshold={rsi_threshold}")
    print(f"min_size_threshold={mах_size_threshold}")
    print(f"min_turnover_threshold={min_turnover_threshold:,} USDT")

    i = 0
    for token in tokens:
        i += 1
        if i % 10 == 0:
            print(f"\r{i}", end="")        
        try:
            last_rsi = bybit_driver.calculate_last_rsi(token, interval=rsi_interval)
            sleep(0.3)
            condition = (
                last_rsi < rsi_threshold if side == "Buy" else last_rsi > rsi_threshold
            )
            if condition:
                min_size = get_min_size_in_usdt(token, category="linear")
                if min_size is not None and min_size < mах_size_threshold and turnover_24h >= min_turnover_threshold:
                    cur_price = bybit_driver.get_last_price(token)
                    atr_pct = get_atr_m1_percent(token)
                    atr_display = f"{atr_pct:.3f}%" if atr_pct is not None else "N/A"                    
                    print(f"\r{token} - RSI: {last_rsi}, Price={cur_price}, Turnover 24h USDT: {int(turnover_24h):,}")
                    print(f"ATR(M1)%: {atr_display} | Мин. контракт: {min_size:.4f} USDT\n")
        except KeyboardInterrupt:
            print("Прервано пользователем")
            break
        except Exception as e:
            pass
        

