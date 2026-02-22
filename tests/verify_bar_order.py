from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.core.datetime import dt_to_unix_nanos
import pandas as pd

instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
bar_type = BarType.from_str("BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL")

print("Testing Bar construction with correct order...")
try:
    # TRY 1: Positional order from stub: bar_type, open, high, low, close, volume, ts_event, ts_init
    bar = Bar(
        bar_type,
        Price.from_str("100.0"),
        Price.from_str("110.0"),
        Price.from_str("90.0"),
        Price.from_str("105.0"),
        1000.0, # volume as float
        2000000000, # ts_event
        2000000000  # ts_init
    )
    print("SUCCESS: Positional order (float volume) worked!")
except Exception as e:
    print(f"FAILED: Positional order (float volume) failed: {e}")

try:
    # TRY 2: Keyword arguments
    bar = Bar(
        bar_type=bar_type,
        open=Price.from_str("100.0"),
        high=Price.from_str("110.0"),
        low=Price.from_str("90.0"),
        close=Price.from_str("105.0"),
        volume=1000.0,
        ts_event=2000000000,
        ts_init=2000000000
    )
    print("SUCCESS: Keyword arguments worked!")
except Exception as e:
    print(f"FAILED: Keyword arguments failed: {e}")

try:
    # TRY 3: Quantity for volume
    bar = Bar(
        bar_type,
        Price.from_str("100.0"),
        Price.from_str("110.0"),
        Price.from_str("90.0"),
        Price.from_str("105.0"),
        Quantity.from_str("1000.0"),
        2000000000,
        2000000000
    )
    print("SUCCESS: Quantity volume worked!")
except Exception as e:
    print(f"FAILED: Quantity volume failed: {e}")
