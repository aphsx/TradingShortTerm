try:
    from nautilus_trader.trading.strategy import Strategy
    print("Found Strategy at nautilus_trader.trading.strategy")
except ImportError:
    try:
        from nautilus_trader.strategy import Strategy
        print("Found Strategy at nautilus_trader.strategy")
    except ImportError as e:
        print(f"Could not find Strategy: {e}")

# Check other common imports
try:
    from nautilus_trader.model.enums import OrderSide
    print("Found OrderSide at nautilus_trader.model.enums")
except ImportError as e:
    print(f"Could not find OrderSide: {e}")
