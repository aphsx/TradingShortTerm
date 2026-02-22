from nautilus_trader.model.data import Bar
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.config import StrategyConfig
import inspect

print("Bar.__init__ signature:")
print(inspect.signature(Bar.__init__))

print("\nStrategy.subscribe_bars signature:")
print(inspect.signature(Strategy.subscribe_bars))

print("\nStrategyConfig.__init__ signature:")
print(inspect.signature(StrategyConfig.__init__))
