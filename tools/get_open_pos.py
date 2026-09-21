from pybit.unified_trading import HTTP
# Не забудь импортировать свои ключи!
from ks.keys import API_KEY, DB_PASSWORD 
from pprint import pprint

# 1. Сначала создаем объект сессии
session = HTTP(
    api_key=API_KEY,
    api_secret=DB_PASSWORD,
)

def check_truth():
    # 2. Теперь 'session' доступна внутри функции
    res = session.get_positions(category="linear", symbol="OPUSDT")
    pprint(res)
    return

    
    if res['retCode'] == 0:
        positions = res['result'].get('list', [])
        if not positions or float(positions[0].get('size', 0)) == 0:
            print("Открытых позиций по OPUSDT не найдено.")
            return

        for p in positions:
            size = float(p.get('size', 0))
            if size > 0:
                side = p.get('side')
                mark_price = float(p.get('markPrice', 0))
                entry_price = float(p.get('avgPrice', 0))
                
                # ЧЕСТНЫЙ РАСЧЕТ (математика, которой можно верить)
                real_value = size * mark_price
                
                # Расчет PnL в зависимости от стороны
                if side == 'Buy':
                    real_pnl = (mark_price - entry_price) * size
                else:
                    real_pnl = (entry_price - mark_price) * size
                
                print(f"\n=== {side} {p['symbol']} (РЕАЛЬНЫЕ ДАННЫЕ) ===")
                print(f"Количество:  {size} DUSK")
                print(f"Цена входа:  {entry_price}")
                print(f"Маркировка:  {mark_price}")
                print("-" * 30)
                print(f"ЧЕСТНАЯ СТОИМОСТЬ: {real_value:.2f} USDT")
                print(f"ЧЕСТНЫЙ PnL:       {real_pnl:.2f} USDT")
    else:
        print(f"Ошибка API: {res['retMsg']}")

if __name__ == "__main__":
    check_truth()