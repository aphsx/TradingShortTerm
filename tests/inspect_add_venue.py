from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
import inspect

engine_config = BacktestEngineConfig()
engine = BacktestEngine(config=engine_config)

print("BacktestEngine.add_venue signature:")
print(inspect.signature(engine.add_venue))
