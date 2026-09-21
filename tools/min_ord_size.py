import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_rsi(data, periods=14):
    """Ручной расчёт RSI на основе pandas и numpy"""
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_bybit_perpetual_min_order_sizes_with_rsi():
    try:
        # Initialize Bybit exchange
        exchange = ccxt.bybit({
            'enableRateLimit': True,
        })

        # Load markets
        markets = exchange.load_markets()

        print("Bybit Perpetual Futures with Min Order Size < 0.3 USDT and RSI(H4) > 70 or < 30:")
        print("-" * 80)

        # Filter for USDT-based perpetual futures markets
        for symbol, market in markets.items():
            if (market.get('swap', False) and 
                market.get('linear', False) and 
                'USDT' in symbol and 
                'USDC' not in symbol):  # Only USDT pairs, exclude USDC
                if ('limits' in market and 
                    'amount' in market['limits'] and 
                    market['limits']['amount']['min'] is not None):
                    min_order_size = market['limits']['amount']['min']
                    base_currency = market['base']
                    
                    # Fetch current price for the symbol
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        price = ticker['last']  # Last price in USDT

                        # Convert min order size to USDT
                        min_order_size_usdt = min_order_size * price

                        # Check if min order size is less than 0.3 USDT
                        if min_order_size_usdt < 0.3:
                            # Fetch H4 OHLCV data (4-hour candles, last 100 candles)
                            timeframe = '4h'
                            since = int((datetime.now() - timedelta(days=14)).timestamp() * 1000)  # 14 days ago
                            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=100)
                            
                            # Create DataFrame
                            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                            # Calculate RSI
                            df['rsi'] = calculate_rsi(df, periods=14)

                            # Get the latest RSI value
                            latest_rsi = df['rsi'].iloc[-1]

                            # Check if RSI > 70 or RSI < 30
                            if not np.isnan(latest_rsi) and (latest_rsi > 70 or latest_rsi < 30):
                                rsi_status = "Overbought" if latest_rsi > 70 else "Oversold"
                                print(f"Symbol: {symbol:<15} | Min Order Size: {min_order_size:<10} {base_currency} | "
                                      f"~{min_order_size_usdt:.4f} USDT | RSI(H4): {latest_rsi:.2f} ({rsi_status})")
                    
                    except Exception as e:
                        print(f"Failed to process {symbol}: {str(e)}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    get_bybit_perpetual_min_order_sizes_with_rsi()