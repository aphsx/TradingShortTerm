from nautilus_trader.model.objects import Price
import inspect

print("Price.__init__ signature:")
try:
    print(inspect.signature(Price.__init__))
except Exception as e:
    print(f"Could not get signature: {e}")

# Try common initialization patterns
try:
    p = Price.from_str("100.50")
    print(f"from_str('100.50') success: {p}")
except Exception as e:
    print(f"from_str failed: {e}")

try:
    # Many Nautilus types use (value, precision) or (raw_value, precision)
    p = Price(10050, 2)
    print(f"Price(10050, 2) success: {p}")
except Exception as e:
    print(f"Price(10050, 2) failed: {e}")

try:
    # Or maybe it's (value) but it's not a float?
    p = Price(100)
    print(f"Price(100) success: {p}")
except Exception as e:
    print(f"Price(100) failed: {e}")
