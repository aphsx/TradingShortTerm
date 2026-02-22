import os
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# Import our adapter
try:
    from nautilus_integration.strat_adapter import VortexNautilusAdapter
except ImportError:
    from tests.nautilus_integration.strat_adapter import VortexNautilusAdapter

from config import TRADING_PAIRS, BASE_BALANCE

class VortexConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId

def run_vortex_backtest(csv_path=None):
    # 1. Setup Engine
    engine_config = BacktestEngineConfig(trader_id="VORTEX-BACKTESTER")
    engine = BacktestEngine(config=engine_config)
    
    # 2. Setup Venue
    from nautilus_trader.model.identifiers import Venue
    from nautilus_trader.model.enums import OmsType, AccountType
    from nautilus_trader.model.objects import Money
    from nautilus_trader.model.currencies import USDT
    
    engine.add_venue(
        Venue("BINANCE"),
        OmsType.NETTING,
        AccountType.MARGIN,
        [Money(BASE_BALANCE, USDT)] # Starting Balance from Config
    )
    
    # 3. Add Instruments and Strategies for each pair in config
    instruments = []
    for pair_name in TRADING_PAIRS:
        nautilus_symbol = f"{pair_name}-PERP.BINANCE"
        
        try:
            if pair_name == "BTCUSDT":
                instrument = TestInstrumentProvider.btcusdt_perp_binance()
            elif pair_name == "ETHUSDT":
                instrument = TestInstrumentProvider.ethusdt_perp_binance()
            else:
                # Manually create for other pairs
                instrument = CryptoPerpetual(
                    instrument_id=InstrumentId.from_str(nautilus_symbol),
                    raw_symbol=Symbol(pair_name),
                    venue=Venue("BINANCE"),
                    price_precision=4,
                    size_precision=3,
                    price_increment=Price.from_str("0.0001"),
                    size_increment=Quantity.from_str("0.001"),
                    lot_size=Quantity.from_str("0.001"),
                    quote_currency=USDT,
                    underlying_currency=Currency(pair_name.replace("USDT", "")),
                    settlement_currency=USDT,
                    margin_currency=USDT,
                )
            
            engine.add_instrument(instrument)
            instruments.append(instrument)
            
            # Add Strategy for this instrument
            strat_config = VortexConfig(instrument_id=instrument.id)
            strategy = VortexNautilusAdapter(config=strat_config)
            engine.add_strategy(strategy)
        except Exception as e:
            print(f"Error adding instrument/strategy for {pair_name}: {e}")
    
    # 4. Data Loading (Batch loading for all pairs)
    import pandas as pd
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.core.datetime import dt_to_unix_nanos
    from nautilus_trader.model.objects import Price, Quantity
    import glob

    print(f"Searching for data for {len(instruments)} instruments...")
    
    for instrument in instruments:
        raw_name = str(instrument.id).split('-')[0] # e.g. BTCUSDT
        
        # Try to find specific data file for this coin
        data_pattern = f"tests/nautilus_integration/data_{raw_name}_1m_*.csv"
        data_files = glob.glob(data_pattern)
        if not data_files:
             data_pattern = f"nautilus_integration/data_{raw_name}_1m_*.csv"
             data_files = glob.glob(data_pattern)
             
        if data_files:
            csv_path = max(data_files)
            print(f"Loading {raw_name} data from {csv_path}...")
            try:
                 df = pd.read_csv(csv_path)
                 bars = []
                 bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
                 
                 for _, row in df.iterrows():
                     ts = dt_to_unix_nanos(pd.to_datetime(row['timestamp'], unit='ms'))
                     open_px = f"{float(row['open']):.{instrument.price_precision}f}"
                     high_px = f"{float(row['high']):.{instrument.price_precision}f}"
                     low_px = f"{float(row['low']):.{instrument.price_precision}f}"
                     close_px = f"{float(row['close']):.{instrument.price_precision}f}"
                     vol = f"{float(row['volume']):.{instrument.size_precision}f}"
                     
                     bar = Bar(bar_type, Price.from_str(open_px), Price.from_str(high_px), 
                               Price.from_str(low_px), Price.from_str(close_px), 
                               Quantity.from_str(vol), ts, ts)
                     bars.append(bar)
                 
                 engine.add_data(bars)
                 print(f"Successfully loaded {len(bars)} bars for {raw_name}.")
            except Exception as e:
                 print(f"Error loading {raw_name} data: {e}")
        else:
            print(f"⚠️ No data found for {raw_name}, skipping data load for this coin.")
    
    # 5. Run simulation
    print("--- VORTEX-7 Multi-Asset Nautilus Backtest Initiated ---")
    engine.run()
    print("Backtest Finished! Check logs for results.")

if __name__ == "__main__":
    run_vortex_backtest()
