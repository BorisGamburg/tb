from pybit.unified_trading import HTTP
from ks.keys import API_KEY, DB_PASSWORD

# Авторизация
session = HTTP(
    api_key=API_KEY,
    api_secret=DB_PASSWORD,
)

def get_active_positions(session, settle_coin="USDT"):
    """Получает все открытые позиции (размер > 0)"""
    try:
        response = session.get_positions(
            category="linear",
            settleCoin=settle_coin
        )
        
        if response['retCode'] == 0:
            positions = [
                p for p in response['result'].get('list', []) 
                if float(p.get('size', 0)) > 0
            ]
            return positions
        else:
            print(f"Ошибка API: {response['retMsg']}")
            return []
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return []

def main():
    positions = get_active_positions(session, "USDT")
    
    if not positions:
        print("\nНет открытых позиций.")
        return

    # Сортировка по символу (алфавит) и стороне (Buy/Sell)
    positions = sorted(positions, key=lambda x: (x.get('symbol', ''), x.get('side', '')))

    header = f"\n{'#':>2} | {'Символ':<12} | {'Сторона':<5} | {'Размер':>10} | {'Стоимость $':>12} | {'Вход':>10} | {'PnL (USDT)':>10}"
    print(header)
    print("-" * len(header))

    total_pnl = 0.0
    total_value = 0.0
    last_symbol = None  # Переменная для отслеживания предыдущего символа
    
    for i, pos in enumerate(positions, start=1):
        symbol = pos.get('symbol')
        
        # Если это не первая итерация и символ изменился — рисуем черту
        if last_symbol is not None and symbol != last_symbol:
            print("-" * len(header))
        
        last_symbol = symbol

        side = pos.get('side')
        size = float(pos.get('size', 0))
        entry = round(float(pos.get('avgPrice', 0)), 4)
        mark_price = float(pos.get('markPrice', 0))
        pnl = round(float(pos.get('unrealisedPnl', 0)), 2)
        
        value_usdt = round(size * mark_price, 2)
        
        total_pnl += pnl
        total_value += value_usdt

        side_display = "BUY" if side == "Buy" else "SELL"
        
        print(f"{i:>2}.| {symbol:<12} | {side_display:<7} | {size:>10} | {value_usdt:>12.2f} | {entry:>10} | {pnl:>10}")

    print("=" * len(header)) # Итоговая черта жирнее
    print(f"Общая стоимость всех позиций: {total_value:.2f} USDT")
    print(f"Итого нереализованный PnL:    {total_pnl:.2f} USDT")
    print(f"Всего активных позиций:       {len(positions)}")

if __name__ == "__main__":
    main()