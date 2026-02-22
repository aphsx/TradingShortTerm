from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import BarAggregation, PriceType

# Create the standard instrument
instrument = TestInstrumentProvider.btcusdt_perp_binance()
print(f"Instrument ID: {instrument.id}")
print(f"Instrument ID Type: {type(instrument.id)}")

# Let's try to create a 1-minute BarType for this instrument
# Using MINUTE aggregation
try:
    # Most reliable way: use standard spec
    # BarType(instrument_id, bar_spec)
    from nautilus_trader.model.data import BarSpecification
    spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
    bt = BarType(instrument.id, spec)
    print(f"SUCCESS Manual BarType: {bt}")
    print(f"String format for reference: {str(bt)}")
except Exception as e:
    print(f"FAILED Manual BarType: {e}")

try:
    # Try BarType.from_str with the correct format if possible
    # Some versions use '.' or ':' as separator between ID and spec
    # Let's see how str(bt) looks if successful
    pass
except:
    pass
