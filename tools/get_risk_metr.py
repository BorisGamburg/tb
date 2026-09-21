from pybit.unified_trading import HTTP
from ks.keys import API_KEY, DB_PASSWORD

# Авторизация
session = HTTP(
    api_key=API_KEY,
    api_secret=DB_PASSWORD,
)

def calc_total_pnl(positions):
    return sum(
        float(p['unrealisedPnl'])
        for p in positions
    )

def calc_gross_exposure(positions):
    return sum(
        float(p['size']) * float(p['markPrice'])
        for p in positions
    )

def calc_capital_at_risk(total_pnl, equity):
    if equity <= 0:
        return 0.0
    return abs(total_pnl) / equity

def calc_net_by_symbol(positions):
    net = {}
    for p in positions:
        symbol = p['symbol']
        side = p['side']
        size = float(p['size'])
        price = float(p['markPrice'])
        pnl = float(p.get('unrealisedPnl', 0))

        sign = 1 if side == "Buy" else -1
        
        if symbol not in net:
            net[symbol] = {'exposure': 0.0, 'pnl': 0.0}
            
        net[symbol]['exposure'] += sign * size * price
        net[symbol]['pnl'] += pnl
    return net

def count_positions_over_limit(net_by_symbol, per_symbol_limit):
    return sum(
        abs(data['exposure']) > per_symbol_limit
        for data in net_by_symbol.values()
    )

def calc_directional_exposure(net_by_symbol, gross_exposure):
    if gross_exposure == 0:
        return 0.0
    # Суммируем все чистые экспозиции (exposure) из словарей
    total_net = sum(data['exposure'] for data in net_by_symbol.values())
    return abs(total_net) / gross_exposure

def collect_risk_metrics(positions, equity, per_symbol_limit):
    gross = calc_gross_exposure(positions)
    pnl = calc_total_pnl(positions)
    car = calc_capital_at_risk(pnl, equity)
    net = calc_net_by_symbol(positions)
    over = count_positions_over_limit(net, per_symbol_limit)
    directional = calc_directional_exposure(net, gross)

    return {
        "gross_exposure": gross,
        "total_pnl": pnl,
        "capital_at_risk": car,
        "net_by_symbol": net,
        "positions_over_limit": over,
        "directional_exposure": directional,
    }


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

        # === RISK OBSERVER ===
    EQUITY = 200.0               # твой депозит
    PER_SYMBOL_LIMIT = 10.0      # USDT, пока консервативно

    risk = collect_risk_metrics(
        positions,
        equity=EQUITY,
        per_symbol_limit=PER_SYMBOL_LIMIT
    )

    print("\nRISK OBSERVER")
    print("-" * 40)
    print(f"Gross exposure:              {risk['gross_exposure']:.2f} USDT")
    print(f"Capital at risk:             {risk['capital_at_risk']*100:.2f} %")
    print(f"Positions over threshold:    {risk['positions_over_limit']}")
    print(f"Directional exposure:        {risk['directional_exposure']:.2f}")

    print("\nNet exposure & PnL by symbol:")
    print(f"{'Символ':<12} | {'Net Exp $':>10} | {'Net Exp %':>10} | {'PnL $':>8} | {'% of Depo'}")
    print("-" * 65)    
    for sym, data in risk['net_by_symbol'].items():
        net_val = data['exposure']
        pnl_val = data['pnl']
        pnl_pct = (pnl_val / EQUITY) * 100 if EQUITY > 0 else 0
        net_pct_of_depo = (net_val / EQUITY) * 100 if EQUITY > 0 else 0
        
        # Подкрасим вывод: + для лонгов/профита, - для шортов/убытка (опционально)
        print(f"{sym:<12} | {net_val:>10.2f} | {net_pct_of_depo:>9.2f}% | {pnl_val:>8.2f} | {pnl_pct:>+8.2f}%")
        
if __name__ == "__main__":
    main()