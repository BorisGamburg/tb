import os
import argparse
from pybit.unified_trading import HTTP
from pprint import pprint
from dotenv import load_dotenv
from ks.keys import API_KEY, DB_PASSWORD

# Загружаем переменные окружения (где лежат ключи)
load_dotenv()

def get_direct_client():
    # Берем ключи напрямую из окружения
    api_key = API_KEY
    api_secret = DB_PASSWORD
    
    if not api_key or not api_secret:
        raise ValueError("❌ Ошибка: API_KEY или API_SECRET не найдены в .env файле")
    
    return HTTP(
        testnet=False,
        api_key=api_key,
        api_secret=api_secret,
    )

def main():
    parser = argparse.ArgumentParser(description="Прямой запрос к Bybit API V5")
    parser.add_argument("--symbol", default="APRUSDT", help="Символ (например, APRUSDT)")
    parser.add_argument("--id", required=True, help="Order ID для поиска")
    args = parser.parse_args()

    client = get_direct_client()

    print(f"🚀 Направляем прямой запрос к Bybit V5 для ордера {args.id}...")

    try:
        # Прямой запрос истории исполненных сделок (Trade History)
        response = client.get_executions(
            category="linear",
            symbol=args.symbol,
            orderId=args.id
        )

        pprint(response)

        if response.get("retCode") == 0:
            trades = response.get("result", {}).get("list", [])
            if trades:
                print(f"✅ Найдено сделок: {len(trades)}")
                print("=" * 60)
                pprint(trades)
                print("=" * 60)
            else:
                print(f"❓ В истории сделок (Executions) ничего не найдено для ID: {args.id}")
                print("Проверьте, не является ли этот ID обычным лимитным ордером, который еще не исполнился.")
        else:
            print(f"❌ Ошибка биржи: {response.get('retMsg')}")

    except Exception as e:
        print(f"💥 Критическая ошибка при запросе: {e}")

if __name__ == "__main__":
    main()