import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os
from config import TRADING_PAIRS

def download_historical_data(symbol='BTC/USDT', timeframe='1m', days=30):
    """
    Download historical OHLCV data from Binance and save to CSV.
    """
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    
    print(f"--- Starting Download: {symbol} ({timeframe}) for last {days} days ---")
    
    since = exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
    all_ohlcv = []
    
    while since < exchange.milliseconds():
        try:
            print(f"Fetching from: {datetime.fromtimestamp(since/1000)}")
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            
            all_ohlcv.extend(ohlcv)
            # Update 'since' to the last timestamp + 1ms to avoid overlap
            since = ohlcv[-1][0] + 1
            
            # Respect rate limits
            time.sleep(exchange.rateLimit / 1000)
            
            if len(ohlcv) < 1000: # We reached the end
                break
                
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
            continue

    # Convert to DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Save to CSV in the integration folder
    filename = f"tests/nautilus_integration/data_{symbol.replace('/', '')}_{timeframe}_{days}d.csv"

    df.to_csv(filename, index=False)
    
    print(f"--- Download Complete! ---")
    print(f"Total Rows: {len(df)}")
    print(f"Saved to: {filename}")
    return filename

if __name__ == "__main__":
    folder = 'tests/nautilus_integration'
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    for pair in TRADING_PAIRS:
        # pair is BTCUSDT, needs to be BTC/USDT
        symbol = f"{pair[:-4]}/{pair[-4:]}"
        download_historical_data(symbol=symbol, timeframe='1m', days=180)
