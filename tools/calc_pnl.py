import pandas as pd
import sys

from common.bybit_executions import (
    get_full_history_by_weeks,
    get_ticker_price,
)

def calc_true_pnl(df, current_price):
    """
    Рассчитывает чистый PnL без учета комиссий и funding
    
    Args:
        df: DataFrame с историей из get_executions
        current_price: текущая цена инструмента
        
    Returns:
        dict с детализацией PnL
    """
    if df.empty:
        return {
            "symbol": "N/A",
            "gross_pnl": 0.0,
            "realized_cash": 0.0,
            "net_inventory_qty": 0.0,
            "debt_value": 0.0,
            "current_price": current_price
        }
    
    df = df.copy()
    
    # Фильтруем только торговые операции
    trade_df = df[df['execType'].isin(['Trade', 'AdlTrade', 'BustTrade'])].copy()
    
    if trade_df.empty:
        return {
            "symbol": "N/A",
            "gross_pnl": 0.0,
            "realized_cash": 0.0,
            "net_inventory_qty": 0.0,
            "debt_value": 0.0,
            "current_price": current_price
        }
    
    # Конвертация типов
    trade_df['execQty'] = pd.to_numeric(trade_df['execQty'])
    trade_df['execPrice'] = pd.to_numeric(trade_df['execPrice'])
    
    # 1. Считаем денежный поток (Cash Flow) от сделок
    # Sell = получили деньги (+), Buy = отдали деньги (-)
    trade_df['trade_cash_flow'] = trade_df.apply(
        lambda x: (x['execQty'] * x['execPrice']) if x['side'] == 'Sell' 
        else -(x['execQty'] * x['execPrice']), 
        axis=1
    )
    
    # 2. Считаем чистый остаток монет (Inventory)
    # Sell = продали монеты (+qty в долг), Buy = купили монеты (-qty у нас есть)
    trade_df['qty_delta'] = trade_df.apply(
        lambda x: x['execQty'] if x['side'] == 'Sell' else -x['execQty'], 
        axis=1
    )
    
    net_qty = trade_df['qty_delta'].sum()
    realized_cash = trade_df['trade_cash_flow'].sum()
    market_value_of_inventory = net_qty * current_price
    
    # Gross PnL = Наличка - Стоимость долга (без комиссий и funding)
    gross_pnl = realized_cash - market_value_of_inventory
    
    symbol = trade_df.iloc[0]['symbol'] if not trade_df.empty else "N/A"
    
    return {
        "symbol": symbol,
        "gross_pnl": round(gross_pnl, 4),
        "realized_cash": round(realized_cash, 4),
        "net_inventory_qty": round(net_qty, 6),
        "debt_value": round(market_value_of_inventory, 4),
        "current_price": current_price
    }

def calc_fees(df):
    """
    Рассчитывает торговые комиссии (maker/taker fees)
    
    Args:
        df: DataFrame с историей из get_executions
        
    Returns:
        dict с детализацией торговых комиссий
    """
    if df.empty:
        return {
            "total_trading_fees": 0.0,
            "maker_fees": 0.0,
            "taker_fees": 0.0,
            "trade_count": 0
        }
    
    df = df.copy()
    
    # Фильтруем только торговые операции
    trade_df = df[df['execType'].isin(['Trade', 'AdlTrade', 'BustTrade'])].copy()
    
    if trade_df.empty:
        return {
            "total_trading_fees": 0.0,
            "maker_fees": 0.0,
            "taker_fees": 0.0,
            "trade_count": 0
        }
    
    # Конвертируем в числа
    trade_df['execFee'] = pd.to_numeric(trade_df['execFee'])
    
    # Разделяем maker и taker комиссии
    if 'isMaker' in trade_df.columns:
        maker_fees = trade_df[trade_df['isMaker'] == True]['execFee'].sum()
        taker_fees = trade_df[trade_df['isMaker'] == False]['execFee'].sum()
    else:
        maker_fees = 0.0
        taker_fees = trade_df['execFee'].sum()
    
    total_fees = trade_df['execFee'].sum()
    
    return {
        "total_trading_fees": round(total_fees, 6),
        "maker_fees": round(maker_fees, 6),
        "taker_fees": round(taker_fees, 6),
        "trade_count": len(trade_df)
    }

def calc_funding(df):
    """
    Рассчитывает общую сумму funding fees из истории сделок
    
    Args:
        df: DataFrame с историей из get_executions
        
    Returns:
        dict с детализацией funding fees
    """
    if df.empty:
        return {
            "total_funding": 0.0,
            "funding_paid": 0.0,
            "funding_received": 0.0,
            "funding_count": 0
        }
    
    df = df.copy()
    
    # Фильтруем только funding записи
    funding_df = df[df['execType'] == 'Funding'].copy()
    
    if funding_df.empty:
        return {
            "total_funding": 0.0,
            "funding_paid": 0.0,
            "funding_received": 0.0,
            "funding_count": 0
        }
    
    # Конвертируем execFee в числовой формат
    funding_df['execFee'] = pd.to_numeric(funding_df['execFee'])
    
    # execFee для funding:
    # Положительное значение = мы заплатили (расход)
    # Отрицательное значение = мы получили (доход)
    # Поэтому меняем знак, чтобы получить чистый результат
    funding_df['funding_amount'] = -funding_df['execFee']
    
    total_funding = funding_df['funding_amount'].sum()
    funding_received = funding_df[funding_df['funding_amount'] > 0]['funding_amount'].sum()
    funding_paid = abs(funding_df[funding_df['funding_amount'] < 0]['funding_amount'].sum())
    
    return {
        "total_funding": round(total_funding, 4),
        "funding_received": round(funding_received, 4),
        "funding_paid": round(funding_paid, 4),
        "funding_count": len(funding_df)
    }

def print_trades_table(history_df, num_trades=30):
    """Выводит последние сделки в удобоваримом табличном виде"""
    if history_df.empty:
        print("\nИстория сделок пуста.")
        return

    # Настройки отображения Pandas
    pd.set_option('display.max_columns', None)
    pd.set_option('display.expand_frame_repr', False)
    
    # 1. Выбираем только важные колонки
    view_cols = [
        'execTime', 'symbol', 'side', 'execPrice', 
        'execQty', 'execValue', 'execFee', 'execType', 'feeRate'
    ]
    
    # Проверяем, есть ли нужные колонки в df (на случай пустых ответов API)
    existing_cols = [c for c in view_cols if c in history_df.columns]
    
    # 2. Берем последние N сделок
    recent_trades = history_df[existing_cols].tail(num_trades).copy()
    
    # 3. Приводим время в читаемый вид (ЧЧ:ММ:СС)
    if 'execTime' in recent_trades.columns:
        recent_trades['execTime'] = pd.to_datetime(
            pd.to_numeric(recent_trades['execTime']), unit='ms'
        ).dt.strftime('%H:%M:%S')

    print(f"\n--- ПОСЛЕДНИЕ {len(recent_trades)} СДЕЛОК ({history_df.iloc[0]['symbol']}) ---")
    print(recent_trades.to_string(index=False))
    print("-" * 80)

def print_funding_details(df, num_records=20):
    """Выводит детали последних funding выплат"""
    if df.empty:
        print("\nИстория funding пуста.")
        return
    
    funding_df = df[df['execType'] == 'Funding'].copy()
    
    if funding_df.empty:
        print("\nFunding записи не найдены.")
        return
    
    # Выбираем важные колонки
    view_cols = ['execTime', 'symbol', 'execQty', 'feeRate', 'execFee']
    existing_cols = [c for c in view_cols if c in funding_df.columns]
    
    recent_funding = funding_df[existing_cols].tail(num_records).copy()
    
    # Конвертируем время
    if 'execTime' in recent_funding.columns:
        recent_funding['execTime'] = pd.to_datetime(
            pd.to_numeric(recent_funding['execTime']), unit='ms'
        ).dt.strftime('%Y-%m-%d %H:%M')
    
    # Добавляем колонку с чистым результатом (инвертируем execFee)
    if 'execFee' in recent_funding.columns:
        recent_funding['net_amount'] = -pd.to_numeric(recent_funding['execFee'])
    
    print(f"\n--- ПОСЛЕДНИЕ {len(recent_funding)} FUNDING ВЫПЛАТ ---")
    print(recent_funding.to_string(index=False))
    print("-" * 80)    

# Запуск
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python script.py SYMBOL PERIOD_DAYS")
        print("Пример: python script.py BTCUSDT 90")
        sys.exit(1)
    
    symbol = sys.argv[1]
    period_days = float(sys.argv[2])
    
    # Получаем полную историю
    print(f"\n=== Загрузка истории для {symbol} ===")
    history = get_full_history_by_weeks(symbol, period_days)
    
    if history.empty:
        print("История пуста!")
        sys.exit(0)
    
    # Получаем текущую цену
    cur_price = get_ticker_price(symbol)
    #print(f"\nТекущая цена {symbol}: {cur_price}")
    
    # Рассчитываем 3 величины
    pnl_dict = calc_true_pnl(history, cur_price)
    pnl = pnl_dict['gross_pnl']

    fees_dict = calc_fees(history)
    fees = fees_dict['total_trading_fees']

    funding_dict = calc_funding(history)
    funding = funding_dict['total_funding']
    
    # Выводим детали funding
    #print_funding_details(history, 20)
    
    # Выводим последние сделки
    #print_trades_table(history, 100)

    # Вывод
    print("\n" + "=" * 40)
    print(f"Символ: {symbol}")
    print(f"Цена: {cur_price}")
    print("=" * 40)
    print(f"PnL:     {pnl:>12.4f}")
    print(f"Fees:    {-fees:>12.6f}")
    print(f"Funding: {funding:>12.4f}")
    print("-" * 40)
    print(f"NET:     {(pnl - fees + funding):>12.4f}")
    print("=" * 40)    
    




