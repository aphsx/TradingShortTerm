"""
fetch_data.py — ดึงข้อมูลจาก Binance Futures → Nautilus Catalog
=================================================================
รองรับ 2 ประเภทข้อมูล:
  1. TradeTick (aggTrades) — สำหรับ ValueBar backtest (default)
  2. Bar (OHLCV klines) — สำหรับ reference หรือ time-bar backtest

วิธีใช้:
    python fetch_data.py                        # default: BTCUSDT 30 วัน (trades + bars)
    python fetch_data.py --days 7               # 7 วันย้อนหลัง
    python fetch_data.py --symbol ETHUSDT       # เปลี่ยน symbol
    python fetch_data.py --trades-only          # ดึงเฉพาะ TradeTick
    python fetch_data.py --bars-only            # ดึงเฉพาะ Bar (เหมือนเดิม)
    python fetch_data.py --interval 1m          # bar interval (ใช้กับ --bars-only)
"""

import sys
import time
import shutil
import argparse
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

import requests

from nautilus_trader.model.currencies import USDT, BTC, ETH
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, TradeId
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

BINANCE_FUTURES_KLINES    = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_FUTURES_AGTRADES  = "https://fapi.binance.com/fapi/v1/aggTrades"
MAX_BARS_PER_REQUEST      = 1500   # Binance limit per klines request
MAX_TRADES_PER_REQUEST    = 1000   # Binance limit per aggTrades request


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Binance Futures data into Nautilus catalog")
    parser.add_argument("--symbol",      default="BTCUSDT", help="Trading pair (e.g. BTCUSDT, ETHUSDT)")
    parser.add_argument("--days",        type=int, default=30, help="Days of historical data to fetch")
    parser.add_argument("--interval",    default="1m", help="Bar interval (ใช้กับ --bars-only): 1m, 5m, 15m, 1h ...")
    parser.add_argument("--trades-only", action="store_true", help="ดึงเฉพาะ TradeTick (aggTrades)")
    parser.add_argument("--bars-only",   action="store_true", help="ดึงเฉพาะ Bar (OHLCV klines)")
    parser.add_argument("--force",       action="store_true", help="ลบข้อมูลเก่าทั้งหมดก่อน write ใหม่")
    parser.add_argument("--max-trades",  type=int, default=500_000,
                        help="จำกัดจำนวน TradeTick ที่ดึง (default=500000, 0=ไม่จำกัด)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Build Instrument
# ---------------------------------------------------------------------------
def build_instrument(symbol: str) -> CryptoPerpetual:
    venue = Venue(VENUE_NAME)
    base_sym = symbol.replace("USDT", "")
    base_cur = BASE_CURRENCY_MAP.get(base_sym, BTC)

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
# OHLCV Bars (klines)
# ---------------------------------------------------------------------------
def fetch_binance_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    all_klines = []
    current_start = start_ms

    print(f"  Fetching {symbol} {interval} klines from Binance Futures...")

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
        dt = datetime.fromtimestamp(last_open_time / 1000, tz=timezone.utc)
        print(f"    Fetched {len(all_klines):>6,} bars ... up to {dt.strftime('%Y-%m-%d %H:%M')}", end="\r")

        if len(klines) < MAX_BARS_PER_REQUEST:
            break

        current_start = last_open_time + 1
        time.sleep(0.1)

    print()
    return all_klines


def klines_to_bars(klines: list, bar_type: BarType, instrument: CryptoPerpetual) -> list[Bar]:
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


def fetch_bars(symbol: str, days: int, interval: str,
               catalog: ParquetDataCatalog, instrument: CryptoPerpetual):
    interval_map = {
        "1m": "1-MINUTE", "3m": "3-MINUTE", "5m": "5-MINUTE",
        "15m": "15-MINUTE", "30m": "30-MINUTE",
        "1h": "1-HOUR", "2h": "2-HOUR", "4h": "4-HOUR", "1d": "1-DAY",
    }
    if interval not in interval_map:
        print(f"[ERROR] Unknown interval: {interval}. Use: {list(interval_map.keys())}")
        sys.exit(1)

    perp_symbol = f"{symbol}-PERP"
    instrument_id_str = f"{perp_symbol}.{VENUE_NAME}"
    bar_type_str = f"{instrument_id_str}-{interval_map[interval]}-LAST-EXTERNAL"

    now_ms   = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

    # ลบ bar เก่า
    bar_data_dir = CATALOG_PATH / "data" / "bar"
    if bar_data_dir.exists():
        print(f"\n[!] ลบข้อมูล Bar เก่าใน catalog...")
        shutil.rmtree(bar_data_dir)

    klines = fetch_binance_klines(symbol, interval, start_ms, now_ms)
    print(f"    Total klines: {len(klines):,}")
    if not klines:
        return

    bar_type = BarType.from_str(bar_type_str)
    bars = klines_to_bars(klines, bar_type, instrument)

    print(f"\n[Bars] Writing {len(bars):,} bars to catalog...")
    catalog.write_data(bars)

    stored = catalog.bars([bar_type])
    print(f"       Stored : {len(stored):,} bars")
    print(f'       bar_type: "{bar_type_str}"')


# ---------------------------------------------------------------------------
# TradeTick (aggTrades) — ข้อมูลตลาดจริงทุก trade
# ---------------------------------------------------------------------------
def fetch_binance_agg_trades(symbol: str, start_ms: int, end_ms: int,
                             max_trades: int = 500_000) -> list:
    """
    ดึง aggTrades จาก Binance Futures API
    Pagination ด้วย fromId เพื่อป้องกันการข้ามข้อมูลใน ms เดียวกัน

    aggTrade format:
      a: aggTradeId, p: price, q: qty
      T: timestamp (ms), m: isBuyerMaker
    """
    all_trades = []
    from_id = None
    limit_str = f"{max_trades:,}" if max_trades > 0 else "ไม่จำกัด"

    print(f"  Fetching {symbol} aggTrades from Binance Futures... (limit={limit_str})")
    print(f"  (BTC ~200k-500k trades/วัน)")

    while True:
        if from_id is None:
            # batch แรก: ใช้ startTime
            params = {
                "symbol":    symbol,
                "startTime": start_ms,
                "endTime":   end_ms,
                "limit":     MAX_TRADES_PER_REQUEST,
            }
        else:
            # batch ถัดไป: ใช้ fromId (แม่นยำกว่า startTime)
            params = {
                "symbol": symbol,
                "fromId": from_id,
                "limit":  MAX_TRADES_PER_REQUEST,
            }

        # Retry with backoff on rate limit or transient errors
        for attempt in range(5):
            try:
                resp = requests.get(BINANCE_FUTURES_AGTRADES, params=params, timeout=15)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 10)) + attempt * 5
                    print(f"\n    [Rate limit] Waiting {wait}s before retry...", end="\r")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.ConnectionError:
                wait = 5 * (attempt + 1)
                print(f"\n    [ConnError] Retry in {wait}s...", end="\r")
                time.sleep(wait)
        trades = resp.json()

        if not trades:
            break

        # กรองเฉพาะ trades ที่อยู่ใน time range
        if from_id is not None:
            trades = [t for t in trades if t["T"] <= end_ms]

        if not trades:
            break

        all_trades.extend(trades)
        last_trade = trades[-1]
        last_ts_ms = last_trade["T"]

        dt = datetime.fromtimestamp(last_ts_ms / 1000, tz=timezone.utc)
        print(
            f"    Fetched {len(all_trades):>8,} trades ... up to {dt.strftime('%Y-%m-%d %H:%M:%S')}",
            end="\r",
        )

        # หยุดถ้าถึง end_ms แล้ว
        if last_ts_ms >= end_ms:
            break

        # ถ้าได้น้อยกว่า limit = หมดข้อมูลแล้ว
        if len(trades) < MAX_TRADES_PER_REQUEST:
            break

        # ต่อ batch ถัดไปจาก aggTradeId สุดท้าย + 1
        from_id = last_trade["a"] + 1

        # หยุดถ้าถึง max_trades
        if max_trades > 0 and len(all_trades) >= max_trades:
            print(f"\n    [Limit] ถึง max_trades={max_trades:,} แล้ว หยุดดึง")
            break

        time.sleep(0.05)  # rate limit: ป้องกัน 429

    print()
    return all_trades


def agg_trades_to_ticks(
    trades: list,
    instrument: CryptoPerpetual,
) -> list[TradeTick]:
    """
    แปลง Binance aggTrade → Nautilus TradeTick

    isBuyerMaker=True  → buyer เป็น maker → seller เป็น aggressor
    isBuyerMaker=False → seller เป็น maker → buyer เป็น aggressor
    """
    ticks = []
    p = instrument.price_precision
    s = instrument.size_precision
    instrument_id = instrument.id

    for t in trades:
        ts_ns = int(t["T"]) * 1_000_000  # ms → ns
        aggressor = AggressorSide.SELLER if t["m"] else AggressorSide.BUYER

        ticks.append(TradeTick(
            instrument_id=instrument_id,
            price=Price(float(t["p"]), precision=p),
            size=Quantity(float(t["q"]), precision=s),
            aggressor_side=aggressor,
            trade_id=TradeId(str(t["a"])),
            ts_event=ts_ns,
            ts_init=ts_ns,
        ))

    return ticks


def fetch_trades(symbol: str, days: int,
                 catalog: ParquetDataCatalog, instrument: CryptoPerpetual,
                 max_trades: int = 500_000):
    now_ms   = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

    # ลบ tick เก่า
    tick_data_dir = CATALOG_PATH / "data" / "trade_tick"
    if tick_data_dir.exists():
        print(f"\n[!] ลบข้อมูล TradeTick เก่าใน catalog...")
        shutil.rmtree(tick_data_dir)

    raw = fetch_binance_agg_trades(symbol, start_ms, now_ms, max_trades=max_trades)
    print(f"    Total aggTrades: {len(raw):,}")
    if not raw:
        return

    ticks = agg_trades_to_ticks(raw, instrument)

    # เขียนเป็น batch (ป้องกัน memory)
    BATCH_SIZE = 100_000
    total = len(ticks)
    print(f"\n[Trades] Writing {total:,} TradeTicks to catalog...")
    for i in range(0, total, BATCH_SIZE):
        batch = ticks[i:i + BATCH_SIZE]
        catalog.write_data(batch)
        print(f"         Written {min(i + BATCH_SIZE, total):,}/{total:,}", end="\r")

    print(f"\n         Done.")
    print(f'         ValueBar bar_type: "{instrument.id}-50000-VALUE-LAST-INTERNAL"')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def fetch(symbol: str = "BTCUSDT", days: int = 30, interval: str = "1m",
          trades_only: bool = False, bars_only: bool = False,
          max_trades: int = 500_000):

    print("=" * 64)
    print("  Nautilus Data Fetcher")
    print("=" * 64)
    print(f"  Symbol  : {symbol} Perpetual Futures")
    print(f"  Days    : {days}")
    print(f"  Catalog : {CATALOG_PATH.resolve()}")

    CATALOG_PATH.mkdir(parents=True, exist_ok=True)
    catalog  = ParquetDataCatalog(str(CATALOG_PATH))
    instr    = build_instrument(symbol)
    catalog.write_data([instr])
    print(f"\n[1] Instrument: {instr.id}")

    do_trades = not bars_only
    do_bars   = not trades_only

    if do_trades:
        print(f"\n[2] TradeTick (aggTrades) — ข้อมูลตลาดจริง")
        fetch_trades(symbol, days, catalog, instr, max_trades=max_trades)

    if do_bars:
        print(f"\n[3] Bar (OHLCV klines) — {interval}")
        fetch_bars(symbol, days, interval, catalog, instr)

    print(f"\n[OK] Done!")
    if do_trades:
        print(f'     ValueBar backtest  → bar_type: "{instr.id}-50000-VALUE-LAST-INTERNAL"')
    if do_bars:
        interval_map = {
            "1m":"1-MINUTE","3m":"3-MINUTE","5m":"5-MINUTE",
            "15m":"15-MINUTE","30m":"30-MINUTE",
            "1h":"1-HOUR","2h":"2-HOUR","4h":"4-HOUR","1d":"1-DAY",
        }
        imap = interval_map.get(interval, "1-MINUTE")
        print(f'     Bar backtest       → bar_type: "{instr.id}-{imap}-LAST-EXTERNAL"')
    print(f"\n     Next: python run_node.py")


if __name__ == "__main__":
    args = parse_args()
    fetch(
        symbol=args.symbol,
        days=args.days,
        interval=args.interval,
        trades_only=args.trades_only,
        bars_only=args.bars_only,
        max_trades=args.max_trades,
    )
