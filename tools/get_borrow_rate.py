from pybit.unified_trading import HTTP
import time
import pandas as pd
from datetime import datetime   

# API ключи обязательны для работы с аккаунтом UTA
session = HTTP(
    testnet=False,
)

def export_borrow_rates_to_excel():
    session = HTTP(
        testnet=False,
        api_key="eKebFkgYrFpailSz8u",
        api_secret="K6vxywIZ9dwf9mNiTpXwJWMO2GZVX4vFFDPq"
    )

    try:
        print("Получение данных от Bybit...")
        response = session.get_collateral_info()
        
        if response['retCode'] != 0:
            print(f"Ошибка API: {response['retMsg']}")
            return

        raw_data = response['result']['list']
        processed_data = []

        for item in raw_data:
            hourly_rate = float(item['hourlyBorrowRate'])
            
            # Пропускаем монеты, которые нельзя занять (ставка 0)
            if hourly_rate <= 0:
                continue
                
            daily_rate = hourly_rate * 24
            yearly_rate = daily_rate * 365
            
            processed_data.append({
                "Ticker": item['currency'],
                "Hourly Rate": hourly_rate,
                "Daily Rate (%)": round(daily_rate * 100, 4),
                "Yearly APR (%)": round(yearly_rate * 100, 2),
                "Max Borrow Amount": item['maxBorrowingAmount'],
                "Available to Borrow": item['availableToBorrow'],
                "Collateral Ratio": item['collateralRatio']
            })

        # Создаем DataFrame
        df = pd.DataFrame(processed_data)

        # Сортируем по годовой ставке (от дешевых к дорогим)
        df = df.sort_values(by="Yearly APR (%)")

        # Имя файла с датой
        filename = f"bybit_borrow_rates_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        
        # Сохранение
        df.to_excel(filename, index=False, engine='openpyxl')
        
        print(f"Успешно! Файл сохранен: {filename}")
        print(f"Всего обработано монет: {len(df)}")

    except Exception as e:
        print(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    export_borrow_rates_to_excel()