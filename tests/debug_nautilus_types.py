from nautilus_trader.model.data import BarType, Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import BarAggregation, PriceType

instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

# What are the standard BarTypes?
try:
    # TRY 1: Manual constructor with 3 args (as hinted by the "takes at most 3" error)
    # Most likely: instrument_id, interval_nanos, bar_specification
    # Or: instrument_id, bar_specification, aggregation_source
    pass
except:
    pass

# TRY 2: Explore BarType.standard
try:
    # standard(instrument_id, number, aggregation, price_type)
    # wait, the error said "TIME" was invalid?
    # Maybe it's not BarAggregation.TIME but BarAggregation.MINUTE?
    bt = BarType.standard(instrument_id, 1, BarAggregation.MINUTE, PriceType.LAST)
    print(f"BarType.standard: {bt}")
    print(f"BarType.standard repr: {repr(bt)}")
except Exception as e:
    print(f"BarType.standard failed: {e}")

# TRY 3: Look at the error from my previous run:
# ValueError: Error parsing BarType from 'BTCUSDT-PERP.BINANCE-1-MINUTE-INTERNAL-TIME-PRICE', 
# invalid token: 'MINUTE' at position 1
# Token 0: BTCUSDT-PERP.BINANCE
# Token 1: 1
# Token 2: MINUTE -> FAILED.
# Maybe it's NOT MINUTE but something else.

print("\nBarAggregation members:")
for i in BarAggregation:
    print(f"- {i.name}: {int(i)}")

print("\nPriceType members:")
for i in PriceType:
    print(f"- {i.name}: {int(i)}")
