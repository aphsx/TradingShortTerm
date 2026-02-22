from nautilus_trader.trading.strategy import Strategy
import inspect

print("Strategy methods:")
print(f"subscribe_order_book_at_interval: {inspect.signature(Strategy.subscribe_order_book_at_interval)}")
print(f"subscribe_order_book_depth: {inspect.signature(Strategy.subscribe_order_book_depth)}")
