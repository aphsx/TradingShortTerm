from nautilus_trader.trading.strategy import Strategy
import inspect

print("Strategy subscription methods:")
methods = [m for m in dir(Strategy) if m.startswith('subscribe_')]
for m in methods:
    print(f"- {m}")
