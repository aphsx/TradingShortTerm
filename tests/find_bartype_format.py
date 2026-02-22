from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import BarAggregation, PriceType

instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

# Try various formats
formats = [
    "BTCUSDT.BINANCE-1-MINUTE-LAST-TIME",
    "BTCUSDT.BINANCE-1-MIN-LAST-TIME",
    "BTCUSDT.BINANCE-1-m-LAST-TIME",
    "BTCUSDT.BINANCE-60-SECOND-LAST-TIME",
]

for f in formats:
    try:
        bt = BarType.from_str(f)
        print(f"SUCCESS: {f} -> {bt}")
    except Exception as e:
        print(f"FAILED: {f} -> {e}")

# Check available aggregations and price types
import nautilus_trader.model.enums as enums
print("\nBarAggregation values:")
for name, obj in enums.__dict__.items():
    if isinstance(obj, type) and issubclass(obj, enums.BarAggregation) if hasattr(enums, 'BarAggregation') else False:
        # This might not work if it's a Cython enum
        pass

# Better way to check enums
print("BarAggregation:", [m for m in dir(enums.BarAggregation) if not m.startswith('_')])
print("PriceType:", [m for m in dir(enums.PriceType) if not m.startswith('_')])

# Create manually and see string representation
try:
    # Most likely signature: instrument_id, interval_nanos (or similar), aggregation, price_type
    # Let's try to find standard constructors
    bt = BarType.standard(instrument_id, 60_000_000_000, BarAggregation.TIME, PriceType.LAST)
    print(f"\nManual Standard: {bt}")
    print(f"String representation: {str(bt)}")
except Exception as e:
    print(f"\nManual Standard failed: {e}")
