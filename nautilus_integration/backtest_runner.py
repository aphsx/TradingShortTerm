import os
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# Import our adapter
from nautilus_integration.strat_adapter import VortexNautilusAdapter

class VortexConfig(StrategyConfig):
    instrument_id: InstrumentId

def run_vortex_backtest(csv_path=None):
    """
    Main script to run a NautilusTrader backtest for the VORTEX-7 engine.
    """
    # 1. Setup Engine
    engine_config = BacktestEngineConfig(trader_id="VORTEX-BACKTESTER")
    engine = BacktestEngine(config=engine_config)
    
    # 2. Create Instrument (e.g., BTCUSDT)
    instrument = TestInstrumentProvider.default_binance_futures("BTCUSDT-PERP")
    engine.add_instrument(instrument)
    
    # 3. Add Strategy
    strat_config = VortexConfig(instrument_id=instrument.id)
    strategy = VortexNautilusAdapter(config=strat_config)
    engine.add_strategy(strategy)
    
    # 4. Data Loading
    if csv_path and os.path.exists(csv_path):
        import pandas as pd
        from nautilus_trader.model.data import Bar
        from nautilus_trader.core.datetime import dt_to_unix_nanos
        
        print(f"Loading data from {csv_path}...")
        df = pd.DataFrame()
        try:
             df = pd.read_csv(csv_path)
             bars = []
             for _, row in df.iterrows():
                 bar = Bar(
                     instrument_id=instrument.id,
                     bar_type="1m",
                     ts_event=dt_to_unix_nanos(pd.to_datetime(row['timestamp'], unit='ms')),
                     ts_init=dt_to_unix_nanos(pd.to_datetime(row['timestamp'], unit='ms')),
                     open=float(row['open']),
                     high=float(row['high']),
                     low=float(row['low']),
                     close=float(row['close']),
                     volume=float(row['volume']),
                 )
                 bars.append(bar)
             
             engine.add_data(bars)
             print(f"Successfully loaded {len(bars)} bars.")
        except Exception as e:
             print(f"Error loading data: {e}")
    else:
        print("No CSV data provided, test won't run with real history.")
    
    # 5. Run simulation
    print("--- VORTEX-7 Nautilus Backtest Initiated ---")
    if csv_path:
        engine.run()
        print("Backtest Finished! Check logs for results.")
    else:
        print("Note: Provide a CSV path to run the actual simulation.")

if __name__ == "__main__":
    # Find the latest data file if not specified
    import glob
    data_files = glob.glob("nautilus_integration/data_BTCUSDT_1m_*.csv")
    latest_file = max(data_files) if data_files else None
    
    run_vortex_backtest(latest_file)
