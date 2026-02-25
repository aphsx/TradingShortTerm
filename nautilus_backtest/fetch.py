"""
fetch.py — Download Binance Futures data from data.binance.vision → Nautilus Catalog
======================================================================================
Usage:
    python fetch.py                              # BTCUSDT, 30 days (trades + bars)
    python fetch.py --symbol ETHUSDT --days 7
    python fetch.py --trades-only
    python fetch.py --bars-only --interval 1m
    python fetch.py --force                      # clear catalog and re-download
"""

import io
import csv
import shutil
import zipfile
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import requests

from nautilus_trader.model.currencies import USDT, BTC, ETH
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, TradeId
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog


# ── Constants ──────────────────────────────────────────────────────────────────

CATALOG_PATH = Path(__file__).parent / "catalog"
VENUE_NAME   = "BINANCE"
BASE_URL     = "https://data.binance.vision/data/futures/um/daily"

BASE_CURRENCY_MAP = {"BTC": BTC, "ETH": ETH}

INTERVAL_MAP = {
    "1m":  "1-MINUTE",
    "3m":  "3-MINUTE",
    "5m":  "5-MINUTE",
    "15m": "15-MINUTE",
    "30m": "30-MINUTE",
    "1h":  "1-HOUR",
    "4h":  "4-HOUR",
    "1d":  "1-DAY",
}


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fetch Binance Futures data → Nautilus catalog")
    p.add_argument("--symbol",      default="BTCUSDT",  help="Symbol e.g. BTCUSDT, ETHUSDT")
    p.add_argument("--days",        type=int, default=30, help="Days of history (default 30)")
    p.add_argument("--interval",    default="1m",       help="Kline interval: 1m 5m 15m 1h 4h")
    p.add_argument("--trades-only", action="store_true", help="Download aggTrades only")
    p.add_argument("--bars-only",   action="store_true", help="Download klines only")
    p.add_argument("--force",       action="store_true", help="Clear catalog before download")
    return p.parse_args()


# ── Instrument ─────────────────────────────────────────────────────────────────

def build_instrument(symbol: str) -> CryptoPerpetual:
    base = symbol.replace("USDT", "")
    return CryptoPerpetual(
        instrument_id=InstrumentId(Symbol(f"{symbol}-PERP"), Venue(VENUE_NAME)),
        raw_symbol=Symbol(f"{symbol}-PERP"),
        base_currency=BASE_CURRENCY_MAP.get(base, BTC),
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=2,
        size_precision=3,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.001"),
        max_quantity=Quantity.from_str("1000.0"),
        min_quantity=Quantity.from_str("0.001"),
        max_notional=None,
        min_notional=Money(5, USDT),
        max_price=Price.from_str("9999999.0"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0.05"),
        margin_maint=Decimal("0.025"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0004"),
        ts_event=0,
        ts_init=0,
    )


# ── Download helpers ───────────────────────────────────────────────────────────

def download_zip(url: str) -> bytes | None:
    """Download ZIP, return bytes or None if not found / error."""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content
    except requests.RequestException as e:
        print(f"[WARN] {e}")
        return None


def read_csv_from_zip(data: bytes) -> list[list[str]]:
    """Unzip in-memory, parse CSV, skip header row if present."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open(zf.namelist()[0]) as f:
            text = f.read().decode("utf-8")

    rows = [r for r in csv.reader(text.splitlines()) if r]

    # Skip header if first cell is not numeric
    if rows:
        try:
            int(rows[0][0].strip())
        except ValueError:
            rows = rows[1:]

    return rows


# ── aggTrades → TradeTick ──────────────────────────────────────────────────────
#
# CSV columns (no header):
#   [0] agg_trade_id
#   [1] price
#   [2] quantity
#   [3] first_trade_id
#   [4] last_trade_id
#   [5] transact_time  (ms)
#   [6] is_buyer_maker (True/False)

def rows_to_trade_ticks(rows: list, instrument: CryptoPerpetual) -> list[TradeTick]:
    p   = instrument.price_precision
    s   = instrument.size_precision
    iid = instrument.id
    ticks = []
    for row in rows:
        if len(row) < 7:
            continue
        ts_ns         = int(row[5]) * 1_000_000          # ms → ns
        is_buyer_maker = row[6].strip().lower() in ("true", "1")
        aggressor      = AggressorSide.SELLER if is_buyer_maker else AggressorSide.BUYER
        ticks.append(TradeTick(
            instrument_id=iid,
            price=Price(float(row[1]), precision=p),
            size=Quantity(float(row[2]), precision=s),
            aggressor_side=aggressor,
            trade_id=TradeId(row[0]),
            ts_event=ts_ns,
            ts_init=ts_ns,
        ))
    return ticks


def fetch_trades(symbol: str, dates: list, catalog: ParquetDataCatalog,
                 instrument: CryptoPerpetual) -> int:
    tick_dir = CATALOG_PATH / "data" / "trade_tick"
    if tick_dir.exists():
        shutil.rmtree(tick_dir)

    total = 0
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/aggTrades/{symbol}/{symbol}-aggTrades-{date_str}.zip"
        print(f"  [{date_str}] aggTrades ...", end=" ", flush=True)

        data = download_zip(url)
        if data is None:
            print("not found")
            continue

        rows  = read_csv_from_zip(data)
        ticks = rows_to_trade_ticks(rows, instrument)
        if ticks:
            catalog.write_data(ticks)
            total += len(ticks)
            print(f"{len(ticks):>8,} ticks")
        else:
            print("empty")

    return total


# ── klines → Bar ──────────────────────────────────────────────────────────────
#
# CSV columns (no header):
#   [0] open_time         (ms)
#   [1] open
#   [2] high
#   [3] low
#   [4] close
#   [5] volume
#   [6] close_time        (ms)
#   [7] quote_asset_volume
#   [8] number_of_trades
#   [9] taker_buy_base_asset_volume
#  [10] taker_buy_quote_asset_volume
#  [11] ignore

def rows_to_bars(rows: list, bar_type: BarType,
                 instrument: CryptoPerpetual) -> list[Bar]:
    p    = instrument.price_precision
    s    = instrument.size_precision
    bars = []
    for row in rows:
        if len(row) < 6:
            continue
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
    return bars


def fetch_bars(symbol: str, dates: list, interval: str,
               catalog: ParquetDataCatalog, instrument: CryptoPerpetual) -> int:
    if interval not in INTERVAL_MAP:
        print(f"[ERROR] Unknown interval '{interval}'. Options: {list(INTERVAL_MAP)}")
        return 0

    bar_dir = CATALOG_PATH / "data" / "bar"
    if bar_dir.exists():
        shutil.rmtree(bar_dir)

    iid_str  = f"{symbol}-PERP.{VENUE_NAME}"
    bar_type = BarType.from_str(f"{iid_str}-{INTERVAL_MAP[interval]}-LAST-EXTERNAL")

    total = 0
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/klines/{symbol}/{interval}/{symbol}-{interval}-{date_str}.zip"
        print(f"  [{date_str}] klines {interval} ...", end=" ", flush=True)

        data = download_zip(url)
        if data is None:
            print("not found")
            continue

        rows = read_csv_from_zip(data)
        bars = rows_to_bars(rows, bar_type, instrument)
        if bars:
            catalog.write_data(bars)
            total += len(bars)
            print(f"{len(bars):>6,} bars")
        else:
            print("empty")

    return total


# ── Main ───────────────────────────────────────────────────────────────────────

def fetch(symbol: str = "BTCUSDT", days: int = 30, interval: str = "1m",
          trades_only: bool = False, bars_only: bool = False, force: bool = False):

    print("=" * 60)
    print("  Binance Vision Fetcher → Nautilus Catalog")
    print("=" * 60)
    print(f"  Symbol  : {symbol}-PERP (Futures)")
    print(f"  Days    : {days}")
    print(f"  Source  : {BASE_URL}")
    print(f"  Catalog : {CATALOG_PATH.resolve()}")

    if force and CATALOG_PATH.exists():
        print("\n[!] --force: clearing catalog...")
        shutil.rmtree(CATALOG_PATH)

    CATALOG_PATH.mkdir(parents=True, exist_ok=True)

    # Date range: yesterday → N days back (today's data often not ready yet)
    today = datetime.now(tz=timezone.utc).date()
    dates = sorted([
        datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=i)
        for i in range(1, days + 1)
    ])

    catalog    = ParquetDataCatalog(str(CATALOG_PATH))
    instrument = build_instrument(symbol)
    catalog.write_data([instrument])
    print(f"\n[✓] Instrument: {instrument.id}")

    do_trades = not bars_only
    do_bars   = not trades_only

    if do_trades:
        print(f"\n[1] aggTrades → TradeTick ({days} days)")
        total_ticks = fetch_trades(symbol, dates, catalog, instrument)
        print(f"    Total: {total_ticks:,} ticks")

    if do_bars:
        print(f"\n[2] klines → Bar/{interval} ({days} days)")
        total_bars = fetch_bars(symbol, dates, interval, catalog, instrument)
        print(f"    Total: {total_bars:,} bars")

    iid_str = f"{symbol}-PERP.{VENUE_NAME}"
    print(f"\n{'=' * 60}")
    print(f"  Done! Next: python run.py")
    if do_trades:
        print(f'  ValueBar type : "{iid_str}-50000-VALUE-LAST-INTERNAL"')
    if do_bars and interval in INTERVAL_MAP:
        print(f'  Bar type      : "{iid_str}-{INTERVAL_MAP[interval]}-LAST-EXTERNAL"')
    print("=" * 60)


if __name__ == "__main__":
    args = parse_args()
    fetch(
        symbol=args.symbol,
        days=args.days,
        interval=args.interval,
        trades_only=args.trades_only,
        bars_only=args.bars_only,
        force=args.force,
    )
