from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.enums import BarAggregation, PriceType

instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
bar_type = BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")

print(f"Price.from_str('100.5') type: {type(Price.from_str('100.5'))}")

# Try to create a Bar
try:
    bar = Bar(
        bar_type,
        1000000000, # ts_event
        1000000000, # ts_init
        Price.from_str("100.0"),
        Price.from_str("110.0"),
        Price.from_str("90.0"),
        Price.from_str("105.0"),
        1000.0 # volume
    )
    print("Bar construction success!")
except Exception as e:
    print(f"Bar construction failed: {e}")
    import traceback
    traceback.print_exc()

# Check Bar properties
if 'bar' in locals():
    print(f"Bar volume type: {type(bar.volume)}")
