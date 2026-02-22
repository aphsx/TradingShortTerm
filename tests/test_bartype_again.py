from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import BarAggregation, PriceType

instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

# Try various formats based on the BarAggregation enum names
formats = [
    "BTCUSDT.BINANCE-1-MINUTE-LAST",
    "BTCUSDT.BINANCE-1-SECOND-LAST",
    "BTCUSDT.BINANCE-1-TICK-LAST",
]

for f in formats:
    try:
        bt = BarType.from_str(f)
        print(f"SUCCESS: {f} -> {bt}")
        print(f"Repr: {repr(bt)}")
    except Exception as e:
        print(f"FAILED: {f} -> {e}")

# Try to create it via the enum
try:
    bt = BarType(instrument_id, 1, BarAggregation.MINUTE, PriceType.LAST)
    print(f"\nManual success: {bt}")
    print(f"Manual string: {str(bt)}")
except Exception as e:
    print(f"\nManual failed: {e}")
