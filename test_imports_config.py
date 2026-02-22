try:
    from nautilus_trader.config import StrategyConfig
    print("Found StrategyConfig at nautilus_trader.config")
except ImportError:
    try:
        from nautilus_trader.trading.strategy import StrategyConfig
        print("Found StrategyConfig at nautilus_trader.trading.strategy")
    except ImportError as e:
        print(f"Could not find StrategyConfig: {e}")
