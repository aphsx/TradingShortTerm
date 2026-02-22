from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import BarAggregation
import inspect

print("BarType methods/properties:")
print([m for m in dir(BarType) if not m.startswith('_')])

print("\nBar methods/properties:")
print([m for m in dir(Bar) if not m.startswith('_')])

# Try to create a BarType
try:
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    bar_type = BarType(instrument_id, "1-MINUTE", BarAggregation.TIME)
    print(f"\nSuccessfully created BarType: {bar_type}")
except Exception as e:
    print(f"\nFailed to create BarType: {e}")

# Try to see Bar help or documentation if possible
# Since I can't see docstrings easily, I'll try to guess based on properties
