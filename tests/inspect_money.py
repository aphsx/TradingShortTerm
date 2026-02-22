from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USD
import inspect

print("Money info:")
try:
    print(f"Money(100000, USD) worked: {Money(100000, USD)}")
except Exception as e:
    print(f"Money(100000, USD) failed: {e}")

try:
    # Maybe Money(value, currency, precision?)
    pass
except:
    pass
