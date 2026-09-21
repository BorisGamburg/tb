from pybit.unified_trading import HTTP
import json
from ks.keys import API_KEY, DB_PASSWORD

# --- ВВЕДИ ДАННЫЕ ТУТ ---
AP = API_KEY
AS = DB_PASSWORD

SYMBOL = "DUSKUSDT"
SIDE = "Buy"    # 'Buy' или 'Sell'
QTY = 37.0       # Объем
PRICE = 0.19035   # Цена исполнения
# ------------------------

session = HTTP(testnet=False, api_key=AP, api_secret=AS)

def get_my_order_id():
    print(f"--- Ищу {SIDE} {QTY} {SYMBOL} по цене {PRICE} ---")
    
    try:
        resp = session.get_executions(category="linear", symbol=SYMBOL, limit=50)
        
        if resp['retCode'] != 0:
            return f"Ошибка API: {resp['retMsg']}"

        for exe in resp['result']['list']:
            # Сравниваем параметры (float с небольшим допуском)
            if exe['side'].lower() == SIDE.lower() and \
               abs(float(exe['execQty']) - QTY) < 1e-6 and \
               abs(float(exe['execPrice']) - PRICE) < 1e-6:
                
                return {
                    "FOUND_ORDER_ID": exe['orderId'],
                    "execTime": exe['execTime'],
                    "execPrice": exe['execPrice'],
                    "full_info": exe
                }
                
        return "Ордер не найден в последних 50 сделках."

    except Exception as e:
        return f"Ошибка: {e}"

result = get_my_order_id()
print(json.dumps(result, indent=4))