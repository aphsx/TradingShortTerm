"""
fetch.py — Download ALL free Binance Vision data → Nautilus Catalog
====================================================================
Data types fetched:
  1. aggTrades  → TradeTick    (tick-level trades, for VALUE bar aggregation)
  2. klines     → Bar          (OHLCV at configurable intervals)
  3. bookDepth  → GenericData  (order book depth at ±0.2/1/2/3/4/5% levels)
  4. metrics    → GenericData  (OI, long/short ratios, taker vol, every 5min)

Usage:
    python fetch.py                                         # all 5 symbols, 30 days
    python fetch.py --symbols SOLUSDT,BNBUSDT               # specific symbols
    python fetch.py --days 7 --intervals 1m,5m,15m          # multi-timeframe
    python fetch.py --trades-only                           # only aggTrades
    python fetch.py --no-depth --no-metrics                 # skip custom data
    python fetch.py --force                                 # clear catalog first
"""

from __future__ import annotations

import io
import csv
import shutil
import zipfile
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import requests

from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar, BarType, TradeTick, GenericData, DataType
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, TradeId
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from instruments import (
    build_instrument,
    build_all_instruments,
    get_instrument_id_str,
    INSTRUMENT_SPECS,
)

# ── Constants ─────────────────────────────────────────────────────────────────

CATALOG_PATH = Path(__file__).parent / "catalog"
VENUE_NAME   = "BINANCE"
BASE_URL     = "https://data.binance.vision/data/futures/um/daily"

INTERVAL_MAP: dict[str, str] = {
    "1m":  "1-MINUTE",
    "3m":  "3-MINUTE",
    "5m":  "5-MINUTE",
    "15m": "15-MINUTE",
    "30m": "30-MINUTE",
    "1h":  "1-HOUR",
    "4h":  "4-HOUR",
    "6h":  "6-HOUR",
    "12h": "12-HOUR",
    "1d":  "1-DAY",
}

DEFAULT_SYMBOLS  = list(INSTRUMENT_SPECS.keys())  # all 5
DEFAULT_INTERVAL = "1m"

# ── Custom data types (GenericData wrappers) ──────────────────────────────────

@dataclass
class BookDepthData:
    """
    Order book depth snapshot at one percentage level.

    Binance provides snapshots every ~30 seconds at 12 percentage levels:
    negative = ask side (above mid), positive = bid side (below mid)
    Levels: ±0.2, ±1.0, ±2.0, ±3.0, ±4.0, ±5.0

    Fields:
        instrument_id : instrument this data belongs to
        percentage    : distance from mid-price (negative=ask, positive=bid)
        depth         : cumulative quantity at this level (base currency)
        notional      : cumulative USD value at this level
        ts_event      : event timestamp (nanoseconds)
        ts_init       : init timestamp (nanoseconds)
    """
    instrument_id: str
    percentage: float
    depth: float
    notional: float
    ts_event: int
    ts_init: int


@dataclass
class MarketMetrics:
    """
    Market-wide sentiment metrics from Binance (every 5 minutes).

    Fields:
        instrument_id       : instrument this data belongs to
        open_interest       : total open interest (base currency)
        open_interest_value : total open interest (USD)
        top_trader_ls_count : top trader long/short ratio by account count
        top_trader_ls_pos   : top trader long/short ratio by position size
        global_ls_ratio     : all users long/short ratio
        taker_buy_sell_ratio: taker buy volume / taker sell volume
        ts_event            : event timestamp (nanoseconds)
        ts_init             : init timestamp (nanoseconds)
    """
    instrument_id: str
    open_interest: float
    open_interest_value: float
    top_trader_ls_count: float
    top_trader_ls_pos: float
    global_ls_ratio: float
    taker_buy_sell_ratio: float
    ts_event: int
    ts_init: int


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch Binance Futures data → Nautilus catalog"
    )
    p.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help=f"Comma-separated symbols (default: {','.join(DEFAULT_SYMBOLS)})",
    )
    p.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days of history to download (default: 30)",
    )
    p.add_argument(
        "--intervals",
        default=DEFAULT_INTERVAL,
        help=f"Comma-separated kline intervals, e.g. 1m,5m,15m (default: {DEFAULT_INTERVAL})",
    )
    p.add_argument(
        "--trades-only",
        action="store_true",
        help="Download aggTrades only (skip klines, bookDepth, metrics)",
    )
    p.add_argument(
        "--bars-only",
        action="store_true",
        help="Download klines only (skip aggTrades, bookDepth, metrics)",
    )
    p.add_argument(
        "--no-depth",
        action="store_true",
        help="Skip bookDepth download",
    )
    p.add_argument(
        "--no-metrics",
        action="store_true",
        help="Skip metrics download",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Clear entire catalog before downloading",
    )
    return p.parse_args()


# ── Download helpers ──────────────────────────────────────────────────────────

def download_zip(url: str) -> bytes | None:
    """Download a ZIP file. Returns bytes or None if 404/error."""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content
    except requests.RequestException as e:
        print(f"    [WARN] {e}")
        return None


def read_csv_from_zip(data: bytes) -> list[list[str]]:
    """Unzip in-memory, parse CSV, strip header row if first cell is non-numeric."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open(zf.namelist()[0]) as f:
            text = f.read().decode("utf-8")

    rows = [r for r in csv.reader(text.splitlines()) if r]

    if rows:
        try:
            float(rows[0][0].strip())
        except ValueError:
            rows = rows[1:]  # skip header

    return rows


# ── aggTrades → TradeTick ─────────────────────────────────────────────────────
#
# CSV columns (no header):
#   [0] agg_trade_id
#   [1] price
#   [2] quantity
#   [3] first_trade_id
#   [4] last_trade_id
#   [5] transact_time  (ms)
#   [6] is_buyer_maker (True/False)

def rows_to_trade_ticks(
    rows: list[list[str]], instrument: CryptoPerpetual
) -> list[TradeTick]:
    p   = instrument.price_precision
    s   = instrument.size_precision
    iid = instrument.id
    ticks: list[TradeTick] = []
    for row in rows:
        if len(row) < 7:
            continue
        try:
            ts_ns = int(row[5]) * 1_000_000   # ms → ns
            is_buyer_maker = row[6].strip().lower() in ("true", "1")
            aggressor = AggressorSide.SELLER if is_buyer_maker else AggressorSide.BUYER
            ticks.append(TradeTick(
                instrument_id=iid,
                price=Price(float(row[1]), precision=p),
                size=Quantity(float(row[2]), precision=s),
                aggressor_side=aggressor,
                trade_id=TradeId(row[0]),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        except (ValueError, IndexError):
            continue
    return ticks


def fetch_trades(
    symbol: str,
    dates: list[datetime],
    catalog: ParquetDataCatalog,
    instrument: CryptoPerpetual,
) -> int:
    """Download aggTrades for all dates and write to catalog. Returns total ticks."""
    total = 0
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/aggTrades/{symbol}/{symbol}-aggTrades-{date_str}.zip"
        print(f"    [{date_str}] aggTrades ...", end=" ", flush=True)

        data = download_zip(url)
        if data is None:
            print("not found")
            continue

        rows  = read_csv_from_zip(data)
        ticks = rows_to_trade_ticks(rows, instrument)
        if ticks:
            catalog.write_data(ticks)
            total += len(ticks)
            print(f"{len(ticks):>10,} ticks")
        else:
            print("empty")

    return total


# ── klines → Bar ─────────────────────────────────────────────────────────────
#
# CSV columns (no header):
#   [0]  open_time   (ms)
#   [1]  open
#   [2]  high
#   [3]  low
#   [4]  close
#   [5]  volume
#   [6]  close_time  (ms)
#   [7]  quote_asset_volume
#   [8]  number_of_trades
#   [9]  taker_buy_base_asset_volume
#  [10]  taker_buy_quote_asset_volume
#  [11]  ignore

def rows_to_bars(
    rows: list[list[str]],
    bar_type: BarType,
    instrument: CryptoPerpetual,
) -> list[Bar]:
    p    = instrument.price_precision
    s    = instrument.size_precision
    bars: list[Bar] = []
    for row in rows:
        if len(row) < 6:
            continue
        try:
            ts_ns = int(row[0]) * 1_000_000  # open_time ms → ns
            bars.append(Bar(
                bar_type=bar_type,
                open=Price(float(row[1]),  precision=p),
                high=Price(float(row[2]),  precision=p),
                low=Price(float(row[3]),   precision=p),
                close=Price(float(row[4]), precision=p),
                volume=Quantity(float(row[5]), precision=s),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        except (ValueError, IndexError):
            continue
    return bars


def fetch_bars(
    symbol: str,
    dates: list[datetime],
    interval: str,
    catalog: ParquetDataCatalog,
    instrument: CryptoPerpetual,
) -> int:
    """Download klines for one interval and write to catalog. Returns total bars."""
    if interval not in INTERVAL_MAP:
        print(f"    [ERROR] Unknown interval '{interval}'. Options: {list(INTERVAL_MAP)}")
        return 0

    iid_str  = get_instrument_id_str(symbol)
    bar_type = BarType.from_str(f"{iid_str}-{INTERVAL_MAP[interval]}-LAST-EXTERNAL")
    total    = 0

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        url = (
            f"{BASE_URL}/klines/{symbol}/{interval}/"
            f"{symbol}-{interval}-{date_str}.zip"
        )
        print(f"    [{date_str}] klines/{interval} ...", end=" ", flush=True)

        data = download_zip(url)
        if data is None:
            print("not found")
            continue

        rows = read_csv_from_zip(data)
        bars = rows_to_bars(rows, bar_type, instrument)
        if bars:
            catalog.write_data(bars)
            total += len(bars)
            print(f"{len(bars):>8,} bars")
        else:
            print("empty")

    return total


# ── bookDepth → GenericData ───────────────────────────────────────────────────
#
# CSV columns (with header):
#   timestamp   : "2026-02-27 00:00:08"
#   percentage  : -5.00 (negative=ask side, positive=bid side)
#   depth       : cumulative quantity at this level
#   notional    : cumulative USD value at this level

def rows_to_book_depth(
    rows: list[list[str]],
    instrument: CryptoPerpetual,
) -> list[GenericData]:
    iid_str = str(instrument.id)
    results: list[GenericData] = []
    data_type = DataType(BookDepthData)

    for row in rows:
        if len(row) < 4:
            continue
        try:
            # Parse timestamp: "2026-02-27 00:00:08" → nanoseconds
            dt = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
            ts_ns = int(dt.timestamp() * 1e9)

            item = BookDepthData(
                instrument_id=iid_str,
                percentage=float(row[1]),
                depth=float(row[2]),
                notional=float(row[3]),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
            results.append(GenericData(data_type=data_type, data=item))
        except (ValueError, IndexError):
            continue

    return results


def fetch_book_depth(
    symbol: str,
    dates: list[datetime],
    catalog: ParquetDataCatalog,
    instrument: CryptoPerpetual,
) -> int:
    """Download bookDepth snapshots and write to catalog. Returns total rows."""
    total = 0
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/bookDepth/{symbol}/{symbol}-bookDepth-{date_str}.zip"
        print(f"    [{date_str}] bookDepth ...", end=" ", flush=True)

        data = download_zip(url)
        if data is None:
            print("not found")
            continue

        rows = read_csv_from_zip(data)
        items = rows_to_book_depth(rows, instrument)
        if items:
            catalog.write_data(items)
            total += len(items)
            print(f"{len(items):>8,} rows")
        else:
            print("empty")

    return total


# ── metrics → GenericData ─────────────────────────────────────────────────────
#
# CSV columns (with header):
#   create_time, symbol, sum_open_interest, sum_open_interest_value,
#   count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
#   count_long_short_ratio, sum_taker_long_short_vol_ratio

def rows_to_metrics(
    rows: list[list[str]],
    instrument: CryptoPerpetual,
) -> list[GenericData]:
    iid_str = str(instrument.id)
    results: list[GenericData] = []
    data_type = DataType(MarketMetrics)

    for row in rows:
        if len(row) < 8:
            continue
        # Skip header row (first cell is "create_time")
        if row[0].strip().lower().startswith("create"):
            continue
        try:
            dt = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
            ts_ns = int(dt.timestamp() * 1e9)

            item = MarketMetrics(
                instrument_id=iid_str,
                open_interest=float(row[2]),
                open_interest_value=float(row[3]),
                top_trader_ls_count=float(row[4]),
                top_trader_ls_pos=float(row[5]),
                global_ls_ratio=float(row[6]),
                taker_buy_sell_ratio=float(row[7]),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
            results.append(GenericData(data_type=data_type, data=item))
        except (ValueError, IndexError):
            continue

    return results


def fetch_metrics(
    symbol: str,
    dates: list[datetime],
    catalog: ParquetDataCatalog,
    instrument: CryptoPerpetual,
) -> int:
    """Download market metrics and write to catalog. Returns total rows."""
    total = 0
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/metrics/{symbol}/{symbol}-metrics-{date_str}.zip"
        print(f"    [{date_str}] metrics  ...", end=" ", flush=True)

        data = download_zip(url)
        if data is None:
            print("not found")
            continue

        rows = read_csv_from_zip(data)
        items = rows_to_metrics(rows, instrument)
        if items:
            catalog.write_data(items)
            total += len(items)
            print(f"{len(items):>8,} rows")
        else:
            print("empty")

    return total


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch(
    symbols: list[str],
    days: int = 30,
    intervals: list[str] | None = None,
    trades_only: bool = False,
    bars_only: bool = False,
    no_depth: bool = False,
    no_metrics: bool = False,
    force: bool = False,
) -> None:
    """
    Download all requested data for all symbols.

    Args:
        symbols    : list of symbol strings, e.g. ["SOLUSDT", "BNBUSDT"]
        days       : number of days of history (yesterday going back)
        intervals  : kline intervals to download, e.g. ["1m", "5m"]
        trades_only: if True, only download aggTrades
        bars_only  : if True, only download klines
        no_depth   : if True, skip bookDepth
        no_metrics : if True, skip metrics
        force      : if True, clear entire catalog before downloading
    """
    if intervals is None:
        intervals = [DEFAULT_INTERVAL]

    print("=" * 65)
    print("  Binance Vision → Nautilus Catalog  (Multi-Asset)")
    print("=" * 65)
    print(f"  Symbols  : {', '.join(symbols)}")
    print(f"  Days     : {days}")
    print(f"  Intervals: {', '.join(intervals)}")
    print(f"  Source   : {BASE_URL}")
    print(f"  Catalog  : {CATALOG_PATH.resolve()}")

    if force and CATALOG_PATH.exists():
        print("\n[!] --force: clearing entire catalog...")
        shutil.rmtree(CATALOG_PATH)

    CATALOG_PATH.mkdir(parents=True, exist_ok=True)

    # Date range: yesterday back N days (today's data often not yet published)
    today = datetime.now(tz=timezone.utc).date()
    dates = sorted([
        datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        - timedelta(days=i)
        for i in range(1, days + 1)
    ])

    catalog = ParquetDataCatalog(str(CATALOG_PATH))

    # Determine which data types to fetch
    do_trades  = not bars_only
    do_bars    = not trades_only
    do_depth   = not trades_only and not bars_only and not no_depth
    do_metrics = not trades_only and not bars_only and not no_metrics

    # ── Per-symbol fetch loop ────────────────────────────────────────────────
    for symbol in symbols:
        print(f"\n{'─' * 65}")
        print(f"  {symbol}-PERP")
        print(f"{'─' * 65}")

        instrument = build_instrument(symbol)
        catalog.write_data([instrument])
        print(f"  [✓] Instrument registered: {instrument.id}")

        if do_trades:
            print(f"\n  [1] aggTrades → TradeTick")
            n = fetch_trades(symbol, dates, catalog, instrument)
            print(f"      Total: {n:,} ticks")

        if do_bars:
            for i, interval in enumerate(intervals, start=2):
                print(f"\n  [{i}] klines/{interval} → Bar")
                n = fetch_bars(symbol, dates, interval, catalog, instrument)
                print(f"      Total: {n:,} bars")

        if do_depth:
            print(f"\n  bookDepth → GenericData (BookDepthData)")
            n = fetch_book_depth(symbol, dates, catalog, instrument)
            print(f"      Total: {n:,} rows (~{n//12:,} snapshots)")

        if do_metrics:
            print(f"\n  metrics → GenericData (MarketMetrics)")
            n = fetch_metrics(symbol, dates, catalog, instrument)
            print(f"      Total: {n:,} rows")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 65}")
    print("  Done!")
    print(f"\n  Next steps:")
    print(f"    python run.py")
    print(f"    python run.py --symbols {','.join(symbols)}")
    print(f"\n  VALUE bar types (for strategy config):")
    for symbol in symbols:
        iid = f"{symbol}-PERP.BINANCE"
        print(f"    {iid}-50000-VALUE-LAST-INTERNAL")
    print("=" * 65)


if __name__ == "__main__":
    args = parse_args()

    fetch(
        symbols=[s.strip() for s in args.symbols.split(",")],
        days=args.days,
        intervals=[i.strip() for i in args.intervals.split(",")],
        trades_only=args.trades_only,
        bars_only=args.bars_only,
        no_depth=args.no_depth,
        no_metrics=args.no_metrics,
        force=args.force,
    )
