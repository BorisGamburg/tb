from pybit.unified_trading import HTTP
from pprint import pprint
from collections import defaultdict
from accounts.bybit_live import ACCOUNT

# Авторизация
session = HTTP(
    api_key=ACCOUNT.api_key,
    api_secret=ACCOUNT.api_secret,
    testnet=ACCOUNT.demo,
)

def get_all_open_orders(session, symbol, limit=50):
    all_orders = []
    cursor = None
    while True:
        response = session.get_open_orders(
            category="linear",
            settleCoin=symbol,
            openOnly=0,
            limit=limit,
            cursor=cursor
        )
        if response['retCode'] == 0:
            orders = response['result'].get('list', [])
            if orders:
                all_orders.extend(orders)
            cursor = response['result'].get('nextPageCursor', None)
            if not cursor:
                break
        else:
            print(f"Ошибка при запросе: {response['retMsg']}") # Исправлено ret_msg на retMsg
            break
    return all_orders

# НОВАЯ ФУНКЦИЯ: Считает и Buy, и Sell
def count_orders_by_side(all_orders):
    # Структура: counts['BTCUSDT']['Buy'] = 5
    counts = defaultdict(lambda: {'Buy': 0, 'Sell': 0})
    for order in all_orders:
        symbol = order.get('symbol', 'UNKNOWN')
        side = order.get('side') # 'Buy' или 'Sell'
        if side in ['Buy', 'Sell']:
            counts[symbol][side] += 1
    return counts

def main():
    symbol = "USDT"
    all_orders = get_all_open_orders(session, symbol, limit=50)

    # Оставляем только те, где orderType равен 'Limit'
    limit_orders = [o for o in all_orders if o.get('orderType') == 'Limit']

    order_stats = count_orders_by_side(limit_orders)

    print("\nСтатистика ордеров по символам:")
    print(f"{'#':>3} | {'Символ':<12} | {'Buy':>5} | {'Sell':>5}")
    print("-" * 35)
    
    # Сортируем по названию символа
    for i, (symbol, sides) in enumerate(sorted(order_stats.items()), start=1):
        buy_count = sides['Buy']
        sell_count = sides['Sell']
        print(f"{i:>3}. {symbol:<12} | {buy_count:>5} | {sell_count:>5}")

    print(f"\nВсего найдено ордеров: {len(limit_orders)}")

if __name__ == "__main__":
    main()