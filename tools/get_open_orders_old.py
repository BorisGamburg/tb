from pybit.unified_trading import HTTP
from pprint import pprint
from collections import defaultdict

from ks.keys import AP, DB_PASSWORD

# Авторизация
session = HTTP(
    api_key=AP,
    api_secret=DB_PASSWORD,
)


# Функция для получения всех открытых ордеров с пагинацией
def get_all_open_orders(session, symbol, limit=50):
    all_orders = []
    cursor = None  # Начинаем с первой страницы

    while True:
        response = session.get_open_orders(
            category="linear",
            settleCoin=symbol,
            openOnly=0,  # Получаем все ордера, включая открытые и исполненные
            limit=limit,
            cursor=cursor  # Пагинация
        )

        # Проверяем успешность запроса
        if response['retCode'] == 0:
            orders = response['result'].get('list', [])
            #print(len(orders))
            if orders:
                all_orders.extend(orders)
            else:
                pass
                #print(f"На текущей странице нет ордеров.")
            
            # Если в ответе есть курсор для следующей страницы, продолжаем
            cursor = response['result'].get('nextPageCursor', None)
            #print(cursor)
            if not cursor:
                break
        else:
            print(f"Ошибка при запросе: {response['ret_msg']}")
            break

    return all_orders# Основная функция


# Подсчёт количества Sell-ордеров по каждому символу
def count_sell_orders_by_symbol(all_orders):
    counts = defaultdict(int)
    for order in all_orders:
        if order.get('side') == 'Sell':
            symbol = order.get('symbol', 'UNKNOWN')
            counts[symbol] += 1
    return counts



def main():
    symbol = "USDT"  # Пример: символ ETH/USDT
    all_orders = get_all_open_orders(session, symbol, limit=50)
    
    sell_counts = count_sell_orders_by_symbol(all_orders)

    print("\nКоличество SELL-ордеров по символам:")
    # Определяем ширину для выравнивания
    max_symbol_len = max((len(s) for s in sell_counts.keys()), default=0)
    
    for i, (symbol, count) in enumerate(sorted(sell_counts.items()), start=1):
        print(f"{i:>2}. {symbol:<{max_symbol_len}} : {count:>3}")

    print(f"\nНайдено {len(all_orders)} ордеров")

if __name__ == "__main__":
    main()
