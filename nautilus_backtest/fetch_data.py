"""
fetch_data.py — ดึงข้อมูลจาก Binance Futures → Nautilus Catalog
=================================================================
ดึง OHLCV Bar data จาก Binance public API (ไม่ต้องใช้ API Key)
แล้วเขียนตรงเข้า ParquetDataCatalog ที่ BacktestNode ต้องการ

วิธีใช้:
    python fetch_data.py                        # default: BTCUSDT 30 วัน 1m
    python fetch_data.py --days 7               # 7 วันย้อนหลัง
    python fetch_data.py --symbol ETHUSDT       # เปลี่ยน symbol
    python fetch_data.py --interval 5m          # เปลี่ยน timeframe
    python fetch_data.py --symbol BTCUSDT --days 60 --interval 15m

Intervals ที่รองรับ: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d
"""

import sys
import time
import shutil
import argparse
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import requests

from nautilus_trader.model.currencies import USDT, BTC, ETH
from nautilus_trader.model.data import BarType, Bar
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CATALOG_PATH   = Path(__file__).parent / "catalog"
VENUE_NAME     = "BINANCE"
BASE_CURRENCY_MAP = {
    "BTC": BTC,
    "ETH": ETH,
}

# Binance Futures OHLCV endpoint (public, no API key needed)
BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"
MAX_BARS_PER_REQUEST   = 1500   # Binance limit per request


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Binance Futures data into Nautilus catalog")
    parser.add_argument("--symbol",   default="BTCUSDT",  help="Trading pair (e.g. BTCUSDT, ETHUSDT)")
    parser.add_argument("--days",     type=int, default=30, help="Days of historical data to fetch")
    parser.add_argument("--interval", default="1m",        help="Bar interval: 1m, 5m, 15m, 1h ...")
    parser.add_argument("--force",    action="store_true", help="ลบข้อมูล Bar เก่าใน catalog ก่อน write ใหม่ (แก้ Intervals not disjoint)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Step 1: สร้าง CryptoPerpetual instrument
# ---------------------------------------------------------------------------
def build_instrument(symbol: str) -> CryptoPerpetual:
    """
    สร้าง Nautilus CryptoPerpetual instrument
    ค่าตรงกับ Binance Futures spec จริง
    """
    venue = Venue(VENUE_NAME)
    # แยก base currency จาก symbol (BTCUSDT → BTC)
    base_sym = symbol.replace("USDT", "")
    base_cur = BASE_CURRENCY_MAP.get(base_sym, BTC)  # default BTC ถ้าไม่รู้จัก

    perp_symbol = f"{symbol}-PERP"
    return CryptoPerpetual(
        instrument_id=InstrumentId(Symbol(perp_symbol), venue),
        raw_symbol=Symbol(perp_symbol),
        base_currency=base_cur,
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


# ---------------------------------------------------------------------------
# Step 2: ดึง OHLCV จาก Binance Futures API
# ---------------------------------------------------------------------------
def fetch_binance_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> list[list]:
    """
    ดึง klines จาก Binance Futures API แบบแบ่ง batch
    คืนค่าเป็น list ของ [open_time, open, high, low, close, volume, ...]
    """
    all_klines = []
    current_start = start_ms

    print(f"  Fetching {symbol} {interval} from Binance Futures...")

    while current_start < end_ms:
        params = {
            "symbol":    symbol,
            "interval":  interval,
            "startTime": current_start,
            "endTime":   end_ms,
            "limit":     MAX_BARS_PER_REQUEST,
        }

        resp = requests.get(BINANCE_FUTURES_KLINES, params=params, timeout=10)
        resp.raise_for_status()
        klines = resp.json()

        if not klines:
            break

        all_klines.extend(klines)
        last_open_time = klines[-1][0]

        # Progress
        dt = datetime.fromtimestamp(last_open_time / 1000, tz=timezone.utc)
        print(f"    Fetched {len(all_klines):>6,} bars ... up to {dt.strftime('%Y-%m-%d %H:%M')}", end="\r")

        # ถ้าได้ครบแล้ว หรือได้น้อยกว่า limit = จบแล้ว
        if len(klines) < MAX_BARS_PER_REQUEST:
            break

        # ไม่ duplicate — เริ่ม batch ถัดไปจาก bar สุดท้าย + 1ms
        current_start = last_open_time + 1

        # Rate limit: ป้องกัน 429
        time.sleep(0.1)

    print()   # newline หลัง \r
    return all_klines


# ---------------------------------------------------------------------------
# Step 3: แปลง klines → Nautilus Bar objects
# ---------------------------------------------------------------------------
def klines_to_bars(
    klines: list[list],
    bar_type: BarType,
    instrument: CryptoPerpetual,
) -> list[Bar]:
    """
    Binance kline format:
    [0] open_time (ms), [1] open, [2] high, [3] low, [4] close, [5] volume,
    [6] close_time, [7-11] misc
    """
    bars = []
    p = instrument.price_precision
    s = instrument.size_precision

    for k in klines:
        open_time_ns = int(k[0]) * 1_000_000  # ms → ns
        bars.append(Bar(
            bar_type=bar_type,
            open=Price(float(k[1]), precision=p),
            high=Price(float(k[2]), precision=p),
            low=Price(float(k[3]), precision=p),
            close=Price(float(k[4]), precision=p),
            volume=Quantity(float(k[5]), precision=s),
            ts_event=open_time_ns,
            ts_init=open_time_ns,
        ))
    return bars


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def fetch(symbol: str = "BTCUSDT", days: int = 30, interval: str = "1m"):
    perp_symbol = f"{symbol}-PERP"
    instrument_id_str = f"{perp_symbol}.{VENUE_NAME}"
    bar_type_str = f"{instrument_id_str}-1-MINUTE-LAST-EXTERNAL"

    # แก้ bar_type_str ถ้า interval ไม่ใช่ 1m
    interval_map = {
        "1m": "1-MINUTE", "3m": "3-MINUTE", "5m": "5-MINUTE",
        "15m": "15-MINUTE", "30m": "30-MINUTE",
        "1h": "1-HOUR", "2h": "2-HOUR", "4h": "4-HOUR", "1d": "1-DAY",
    }
    if interval not in interval_map:
        print(f"[ERROR] Unknown interval: {interval}. Use: {list(interval_map.keys())}")
        sys.exit(1)
    bar_type_str = f"{instrument_id_str}-{interval_map[interval]}-LAST-EXTERNAL"

    print("=" * 60)
    print("  Nautilus Data Fetcher")
    print("=" * 60)
    print(f"  Symbol    : {symbol} Perpetual Futures")
    print(f"  Interval  : {interval}")
    print(f"  Days      : {days}")
    print(f"  Catalog   : {CATALOG_PATH.resolve()}")

    # คำนวณ time range
    now_ms      = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ms    = now_ms - (days * 24 * 60 * 60 * 1000)

    # [1] Catalog — ลบข้อมูล Bar เก่าออกก่อน (ป้องกัน disjoint interval error)
    CATALOG_PATH.mkdir(parents=True, exist_ok=True)

    bar_data_dir = CATALOG_PATH / "data" / "bar"
    if bar_data_dir.exists():
        print(f"\n[!] ลบข้อมูล Bar เก่าใน catalog...")
        shutil.rmtree(bar_data_dir)
        print(f"    Done.")

    catalog = ParquetDataCatalog(str(CATALOG_PATH))

    # [2] Instrument
    instrument = build_instrument(symbol)
    catalog.write_data([instrument])
    print(f"\n[1] Instrument written: {instrument.id}")

    # [3] Fetch from Binance
    print(f"\n[2] Fetching data...")
    klines = fetch_binance_klines(symbol, interval, start_ms, now_ms)
    print(f"    Total klines fetched : {len(klines):,}")

    if not klines:
        print("[ERROR] No data returned from Binance. Check symbol/interval.")
        return

    # [4] Convert
    bar_type = BarType.from_str(bar_type_str)
    bars = klines_to_bars(klines, bar_type, instrument)
    print(f"    Bars created         : {len(bars):,}")

    # [5] Write to catalog
    print(f"\n[3] Writing to catalog...")
    catalog.write_data(bars)

    # [6] Verify
    stored = catalog.bars([bar_type])
    print(f"    Bars in catalog      : {len(stored):,}")
    print(f"\n    Range: {stored[0].ts_event // 1_000_000} ms → {stored[-1].ts_event // 1_000_000} ms")

    print(f"\n[OK] Done! bar_type for run_node.py:")
    print(f'     "{bar_type_str}"')
    print(f"\n     Next: python run_node.py")


if __name__ == "__main__":
    args = parse_args()
    fetch(symbol=args.symbol, days=args.days, interval=args.interval)
