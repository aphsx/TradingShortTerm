"""
run.py — Nautilus BacktestEngine (default approach)
=====================================================
Usage:
    python run.py
    python run.py --balance 5000
    python run.py --mode breakout

Requires data in catalog first:
    python fetch.py --days 30
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from strategy import LiveStrategy, LiveStrategyConfig

load_dotenv(Path(__file__).parent.parent / ".env")

CATALOG_PATH      = Path(__file__).parent / "catalog"
VENUE_NAME        = "BINANCE"
SYMBOL            = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"
REPORTS_DIR       = Path(__file__).parent / "reports"

DEFAULT_BALANCE = float(os.getenv("BACKTEST_INITIAL_BALANCE", "10000.0"))
if "--balance" in sys.argv:
    idx = sys.argv.index("--balance")
    if idx + 1 < len(sys.argv):
        DEFAULT_BALANCE = float(sys.argv[idx + 1])

DEFAULT_MODE = "hybrid"
if "--mode" in sys.argv:
    idx = sys.argv.index("--mode")
    if idx + 1 < len(sys.argv):
        DEFAULT_MODE = sys.argv[idx + 1]


def save_reports(engine: BacktestEngine) -> None:
    import json
    from datetime import datetime, timezone

    REPORTS_DIR.mkdir(exist_ok=True)
    ts     = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = REPORTS_DIR / ts

    try:
        orders_df = engine.trader.generate_orders_report()
        if orders_df is not None and len(orders_df) > 0:
            orders_df.to_csv(f"{prefix}_orders.csv", index=True)

        positions_df = engine.trader.generate_positions_report()
        if positions_df is not None and len(positions_df) > 0:
            positions_df.to_csv(f"{prefix}_positions.csv", index=True)

        account_df = engine.trader.generate_account_report(Venue(VENUE_NAME))
        if account_df is not None and len(account_df) > 0:
            account_df.to_csv(f"{prefix}_account.csv", index=True)

        print(f"  [Saved] reports/{ts}_*.csv")
    except Exception as e:
        print(f"  [WARN] save_reports: {e}")


def run():
    if not CATALOG_PATH.exists():
        print("[ERROR] Catalog not found. Run: python fetch.py")
        return

    catalog     = ParquetDataCatalog(str(CATALOG_PATH))
    instruments = catalog.instruments()
    if not instruments:
        print("[ERROR] No instruments in catalog. Run: python fetch.py")
        return

    ticks = catalog.trade_ticks(instrument_ids=[INSTRUMENT_ID_STR])
    if not ticks:
        print("[ERROR] No TradeTick data. Run: python fetch.py --days 30")
        return

    print("=" * 60)
    print(f"  Backtest — SINGLE".center(60))
    print("=" * 60)
    print(f"  Pair      : {instruments[0].id}")
    print(f"  TradeTick : {len(ticks):,}")
    print(f"  Bar type  : ValueBar $50k (INTERNAL, aggregated from ticks)")
    print(f"  Balance   : {DEFAULT_BALANCE:,.2f} USDT")
    print(f"  Mode      : {DEFAULT_MODE}")
    print(f"\n  Running...\n")

    # ── Engine ─────────────────────────────────────────────────────────
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            logging=LoggingConfig(log_level="INFO"),
        )
    )

    # ── Venue ──────────────────────────────────────────────────────────
    engine.add_venue(
        venue=Venue(VENUE_NAME),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(DEFAULT_BALANCE, USDT)],
    )

    # ── Instrument + Data ──────────────────────────────────────────────
    engine.add_instrument(instruments[0])
    engine.add_data(ticks)
    # VALUE-LAST-INTERNAL bars are aggregated from ticks automatically
    # when the strategy calls subscribe_bars() — no need to add them here.

    # ── Strategy ───────────────────────────────────────────────────────
    strategy = LiveStrategy(
        config=LiveStrategyConfig(
            instrument_id=INSTRUMENT_ID_STR,
            entry_mode=DEFAULT_MODE,
        )
    )
    engine.add_strategy(strategy)

    # ── Run ────────────────────────────────────────────────────────────
    engine.run()
    save_reports(engine)
    engine.dispose()


if __name__ == "__main__":
    run()
