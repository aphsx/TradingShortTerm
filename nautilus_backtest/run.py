"""
run.py — Multi-Asset BacktestEngine Orchestrator
=================================================
Loads all instruments and data from the catalog, configures the
BacktestEngine, runs the strategy, and generates analytics reports.

Usage:
    python run.py                                   # all 5 symbols, defaults
    python run.py --symbols SOLUSDT,BNBUSDT         # specific instruments
    python run.py --balance 50000                   # custom starting balance
    python run.py --bar-value 25000                 # VALUE bar threshold
    python run.py --intervals 5m,15m               # include external kline bars
    python run.py --log-level DEBUG                 # verbose logging
    python run.py --strategy signal                 # use SignalEngineStrategy

Requires data in catalog:
    python fetch.py --days 30
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from instruments import (
    build_all_instruments,
    get_instrument_id_str,
    INSTRUMENT_SPECS,
)
from strategy import (
    MultiAssetStrategy,
    MultiAssetStrategyConfig,
    SignalEngineStrategy,
)
from analytics import BacktestAnalytics

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────

CATALOG_PATH = Path(__file__).parent / "catalog"
VENUE_NAME   = "BINANCE"
REPORTS_DIR  = Path(__file__).parent / "reports"

# ── Interval map (CLI string → Nautilus BarSpec string) ──────────────────────

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

# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Multi-asset Nautilus BacktestEngine runner"
    )
    p.add_argument(
        "--symbols",
        default=",".join(INSTRUMENT_SPECS.keys()),
        help="Comma-separated symbols (default: all 5)",
    )
    p.add_argument(
        "--balance",
        type=float,
        default=float(os.getenv("BACKTEST_INITIAL_BALANCE", "10000.0")),
        help="Starting USDT balance (default: 10000)",
    )
    p.add_argument(
        "--bar-value",
        type=float,
        default=50_000.0,
        help="VALUE bar notional threshold in USD (default: 50000)",
    )
    p.add_argument(
        "--intervals",
        default="",
        help=(
            "Comma-separated kline intervals to include as external bars, "
            "e.g. 5m,15m (default: none — VALUE bars only)"
        ),
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Engine log level (default: INFO)",
    )
    p.add_argument(
        "--strategy",
        default="base",
        choices=["base", "signal"],
        help=(
            "'base' = MultiAssetStrategy (override on_bar_logic for your logic), "
            "'signal' = SignalEngineStrategy (uses live_engine/signal_engine.py)"
        ),
    )
    return p.parse_args()


# ── Run ───────────────────────────────────────────────────────────────────────

def run() -> None:
    args    = parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    ext_intervals = [
        i.strip() for i in args.intervals.split(",") if i.strip()
    ] if args.intervals else []

    # ── Validate catalog ──────────────────────────────────────────────────────
    if not CATALOG_PATH.exists():
        print("[ERROR] Catalog not found. Run: python fetch.py --days 30")
        sys.exit(1)

    catalog = ParquetDataCatalog(str(CATALOG_PATH))

    # ── Print header ─────────────────────────────────────────────────────────
    print("=" * 65)
    print("  Multi-Asset Backtest".center(65))
    print("=" * 65)
    print(f"  Symbols   : {', '.join(symbols)}")
    print(f"  Balance   : {args.balance:,.2f} USDT")
    print(f"  VALUE bar : ${args.bar_value:,.0f} notional")
    print(f"  Ext bars  : {', '.join(ext_intervals) if ext_intervals else 'none'}")
    print(f"  Strategy  : {args.strategy}")
    print()

    # ── Build instruments ─────────────────────────────────────────────────────
    instruments = build_all_instruments(symbols)

    # ── Load data per symbol ──────────────────────────────────────────────────
    all_ticks:       list = []
    all_ext_bars:    list = []
    bar_types_config: dict[str, tuple[str, ...]] = {}

    print("  Loading data from catalog...")
    for symbol in symbols:
        iid_str = get_instrument_id_str(symbol)

        # Trade ticks (for VALUE bar aggregation)
        ticks = catalog.trade_ticks(instrument_ids=[iid_str])
        if ticks:
            all_ticks.extend(ticks)
            print(f"    {symbol:10s}: {len(ticks):>12,} ticks")
        else:
            print(f"    {symbol:10s}: [WARN] no ticks — run fetch.py first")

        # VALUE bar type (INTERNAL — created on-the-fly from ticks by engine)
        val_n    = int(args.bar_value)
        value_bt = f"{iid_str}-{val_n}-VALUE-LAST-INTERNAL"
        bt_list  = [value_bt]

        # External kline bars (EXTERNAL — pre-built from klines CSVs)
        for interval in ext_intervals:
            if interval not in INTERVAL_MAP:
                print(f"    [WARN] Unknown interval '{interval}', skipping")
                continue
            ext_bt   = f"{iid_str}-{INTERVAL_MAP[interval]}-LAST-EXTERNAL"
            ext_bars = catalog.bars(bar_types=[ext_bt])
            if ext_bars:
                all_ext_bars.extend(ext_bars)
                bt_list.append(ext_bt)
                print(f"    {symbol:10s}: {len(ext_bars):>10,} bars ({interval})")

        bar_types_config[iid_str] = tuple(bt_list)

    total_events = len(all_ticks) + len(all_ext_bars)
    print(f"\n  Total events: {total_events:,}")

    if not all_ticks:
        print("[ERROR] No tick data found. Run: python fetch.py --days 30")
        sys.exit(1)

    # ── Create BacktestEngine ─────────────────────────────────────────────────
    print("\n  Configuring engine...")
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            logging=LoggingConfig(log_level=args.log_level),
        )
    )

    # Single BINANCE venue — margin account, NETTING mode (one position per side)
    engine.add_venue(
        venue=Venue(VENUE_NAME),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(args.balance, USDT)],
    )

    # Add all instruments
    for inst in instruments:
        engine.add_instrument(inst)
        print(f"    + {inst.id}")

    # Add trade ticks (engine interleaves by timestamp automatically)
    engine.add_data(all_ticks)
    print(f"    + {len(all_ticks):,} TradeTick objects")

    # Add external bars
    if all_ext_bars:
        engine.add_data(all_ext_bars)
        print(f"    + {len(all_ext_bars):,} Bar objects (klines)")

    # Load and add GenericData (bookDepth and metrics)
    _load_generic_data(catalog, symbols, engine)

    # ── Create strategy ────────────────────────────────────────────────────────
    iid_strs = [get_instrument_id_str(s) for s in symbols]
    config   = MultiAssetStrategyConfig(
        instrument_ids=tuple(iid_strs),
        bar_types=bar_types_config,
    )

    if args.strategy == "signal":
        strategy = SignalEngineStrategy(config=config)
        print(f"\n  Strategy: SignalEngineStrategy (live_engine/signal_engine.py)")
    else:
        strategy = MultiAssetStrategy(config=config)
        print(f"\n  Strategy: MultiAssetStrategy (base — no-op, override on_bar_logic)")

    engine.add_strategy(strategy)

    # ── Run ───────────────────────────────────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("  Running backtest...")
    print(f"{'─' * 65}\n")

    engine.run()

    # ── Analytics ─────────────────────────────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("  Generating reports...")
    print(f"{'─' * 65}")

    analytics = BacktestAnalytics(engine, REPORTS_DIR)
    analytics.generate_all()

    engine.dispose()
    print("\n  Done.")


def _load_generic_data(
    catalog: ParquetDataCatalog,
    symbols: list[str],
    engine: BacktestEngine,
) -> None:
    """
    Attempt to load bookDepth and metrics GenericData from catalog.
    Silently skips if no custom data is found (graceful degradation).
    """
    try:
        from fetch import BookDepthData, MarketMetrics
        from nautilus_trader.model.data import DataType

        for symbol in symbols:
            # BookDepth
            try:
                depth_data = catalog.generic_data(
                    data_cls=BookDepthData,
                    metadata={"instrument_id": get_instrument_id_str(symbol)},
                )
                if depth_data:
                    engine.add_data(depth_data)
                    print(f"    + {symbol}: {len(depth_data):,} BookDepthData rows")
            except Exception:
                pass  # No bookDepth in catalog — skip

            # Metrics
            try:
                metrics_data = catalog.generic_data(
                    data_cls=MarketMetrics,
                    metadata={"instrument_id": get_instrument_id_str(symbol)},
                )
                if metrics_data:
                    engine.add_data(metrics_data)
                    print(f"    + {symbol}: {len(metrics_data):,} MarketMetrics rows")
            except Exception:
                pass  # No metrics in catalog — skip

    except Exception:
        pass  # Custom data not available — skip silently


if __name__ == "__main__":
    run()
