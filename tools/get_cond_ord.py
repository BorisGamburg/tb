from pybit.unified_trading import HTTP
import json
from ks.keys import AP, DB_PASSWORD

# Ваши данные (лучше подтянуть из вашего config-файла)
api_key = AP
api_secret = DB_PASSWORD

session = HTTP(
    testnet=False,
    api_key=api_key,
    api_secret=api_secret,
)

def get_conditional_order_ids(symbol="DUSKUSDT"):
    try:
        # Получаем только условные (Trigger) ордера
        response = session.get_order_history(
            category="linear",
            symbol=symbol,
            openOnly=1, # Только открытые (активные)
            limit=50
        )
        
        orders = response.get('result', {}).get('list', [])
        
        if not orders:
            print(f"--- Активных условных ордеров по {symbol} не найдено ---")
            return

        print(f"{'Order ID':<40} | {'Qty':<10} | {'Trigger Price':<15} | {'Side':<10}")
        print("-" * 80)
        
        for o in orders:
            # На Bybit v5 условные ордера могут иметь triggerPrice
            t_price = o.get('triggerPrice', 'N/A')
            print(f"{o['orderId']:<40} | {o['qty']:<10} | {t_price:<15} | {o['side']:<10}")
            
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")

if __name__ == "__main__":
    get_conditional_order_ids("DUSKUSDT")