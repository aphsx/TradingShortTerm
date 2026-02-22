import numpy as np
import pandas as pd
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.data import Bar, Tick
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId

def ccxt_klines_to_nautilus_bars(symbol: str, klines: list) -> list[Bar]:
    """
    Convert CCXT format klines [timestamp, open, high, low, close, volume]
    to NautilusTrader Bar objects.
    """
    instrument_id = InstrumentId.from_str(f"BINANCE.{symbol}")
    bars = []
    for k in klines:
        bar = Bar(
            instrument_id=instrument_id,
            bar_type="1m", # Default to 1m
            ts_event=dt_to_unix_nanos(pd.to_datetime(k[0], unit='ms')),
            ts_init=dt_to_unix_nanos(pd.to_datetime(k[0], unit='ms')),
            open=float(k[1]),
            high=float(k[2]),
            low=float(k[3]),
            close=float(k[4]),
            volume=float(k[5]),
        )
        bars.append(bar)
    return bars

def nautilus_bar_to_list(bar: Bar) -> list:
    """Convert Nautilus Bar back to the list format expected by Engines (E3, E5)"""
    return [
        int(bar.ts_event / 1_000_000), # ms
        float(bar.open),
        float(bar.high),
        float(bar.low),
        float(bar.close),
        float(bar.volume)
    ]

def nautilus_book_to_dict(book) -> dict:
    """Convert Nautilus OrderBook to dict format expected by Engine1"""
    # Nautilus OrderBook might have different accessors depending on version
    # This is a generic conversion
    return {
        "bids": [[float(level.price), float(level.size)] for level in book.bids],
        "asks": [[float(level.price), float(level.size)] for level in book.asks]
    }
