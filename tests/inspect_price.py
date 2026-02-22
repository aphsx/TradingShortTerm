from nautilus_trader.model.objects import Price
import inspect

print("Price methods:")
methods = [m for m in dir(Price) if not m.startswith('_')]
for m in methods:
    print(f"- {m}")

try:
    p = Price(100.0)
    print(f"\nPrice(100.0) worked: {p}")
except Exception as e:
    print(f"\nPrice(100.0) failed: {e}")

try:
    p = Price.from_double(100.0)
    print(f"Price.from_double(100.0) worked: {p}")
except Exception as e:
    print(f"Price.from_double(100.0) failed: {e}")
