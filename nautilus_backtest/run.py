"""
run.py — Nautilus BacktestNode
================================
Usage:
    python run.py                    # single run
    python run.py --sweep            # quick sweep (5 configs)
    python run.py --sweep --full     # full sweep (20+ configs)
    python run.py --balance 5000
    python run.py --mode breakout

Requires data in catalog first:
    python fetch.py --days 30
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    BarAggregatorConfig,
    ImportableStrategyConfig,
    LoggingConfig,
)
from nautilus_trader.model.data import BarType, TradeTick
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog

load_dotenv(Path(__file__).parent.parent / ".env")

CATALOG_PATH      = Path(__file__).parent / "catalog"
VENUE_NAME        = "BINANCE"
SYMBOL            = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"
VALUE_BAR_TYPE    = f"{INSTRUMENT_ID_STR}-50000-VALUE-LAST-INTERNAL"

SWEEP_MODE = "--sweep" in sys.argv
FULL_SWEEP = "--full"  in sys.argv

DEFAULT_BALANCE = float(os.getenv("BACKTEST_INITIAL_BALANCE", "10000.0"))
if "--balance" in sys.argv:
    idx = sys.argv.index("--balance")
    if idx + 1 < len(sys.argv):
        DEFAULT_BALANCE = float(sys.argv[idx + 1])

_DEFAULT_MODE = "hybrid"
if "--mode" in sys.argv:
    idx = sys.argv.index("--mode")
    if idx + 1 < len(sys.argv):
        _DEFAULT_MODE = sys.argv[idx + 1]


# ── Config builder ─────────────────────────────────────────────────────────────

def make_config(
    *,
    instruments: list,
    ema_fast: int = 9, ema_medium: int = 21, ema_trend: int = 50,
    rsi_period: int = 14, atr_period: int = 14,
    bb_period: int = 20, bb_std: float = 2.0, bb_squeeze_lookback: int = 60,
    vwap_period: int = 20,
    rsi_long_min: float = 45.0, rsi_long_max: float = 68.0,
    rsi_short_min: float = 32.0, rsi_short_max: float = 55.0,
    rvol_threshold: float = 1.3,
    min_ema_spread_pct: float = 0.0005, min_atr_pct: float = 0.001,
    entry_mode: str = _DEFAULT_MODE,
    risk_per_trade_pct: float = 0.01,
    atr_sl_multiplier: float = 2.0, atr_tp_multiplier: float = 4.0,
    trailing_activate_atr: float = 2.0, trailing_distance_atr: float = 1.0,
    cooldown_bars: int = 10, max_consecutive_losses: int = 5,
    pause_bars_after_streak: int = 60, max_bars_in_trade: int = 120,
    max_daily_trades: int = 50,
    sweep_lookback: int = 20, sweep_vol_spike_mult: float = 2.0,
    sweep_reversal_bars: int = 3,
    warmup_bars: int = 80,
    initial_balance: float = DEFAULT_BALANCE,
    run_id: str = "BACKTEST-001",
) -> BacktestRunConfig:

    return BacktestRunConfig(
        dispose_on_completion=False,
        instruments=instruments,
        venues=[
            BacktestVenueConfig(
                name=VENUE_NAME,
                oms_type=OmsType.NETTING,
                account_type=AccountType.MARGIN,
                base_currency="USDT",
                starting_balances=[f"{initial_balance} USDT"],
            )
        ],
        data=[
            BacktestDataConfig(
                catalog_path=str(CATALOG_PATH),
                data_cls=TradeTick,
                instrument_id=InstrumentId.from_str(INSTRUMENT_ID_STR),
            )
        ],
        engine=BacktestEngineConfig(
            trader_id=run_id,
            bar_aggregators=[
                BarAggregatorConfig(bar_type=BarType.from_str(VALUE_BAR_TYPE))
            ],
            strategies=[
                ImportableStrategyConfig(
                    strategy_path="strategy:LiveStrategy",
                    config_path="strategy:LiveStrategyConfig",
                    config={
                        "instrument_id": INSTRUMENT_ID_STR,
                        "bar_type": VALUE_BAR_TYPE,
                        "ema_fast": ema_fast, "ema_medium": ema_medium, "ema_trend": ema_trend,
                        "rsi_period": rsi_period, "atr_period": atr_period,
                        "bb_period": bb_period, "bb_std": bb_std,
                        "bb_squeeze_lookback": bb_squeeze_lookback,
                        "vwap_period": vwap_period,
                        "rsi_long_min": rsi_long_min, "rsi_long_max": rsi_long_max,
                        "rsi_short_min": rsi_short_min, "rsi_short_max": rsi_short_max,
                        "rvol_threshold": rvol_threshold,
                        "min_ema_spread_pct": min_ema_spread_pct, "min_atr_pct": min_atr_pct,
                        "entry_mode": entry_mode,
                        "risk_per_trade_pct": risk_per_trade_pct,
                        "atr_sl_multiplier": atr_sl_multiplier,
                        "atr_tp_multiplier": atr_tp_multiplier,
                        "trailing_activate_atr": trailing_activate_atr,
                        "trailing_distance_atr": trailing_distance_atr,
                        "cooldown_bars": cooldown_bars,
                        "max_consecutive_losses": max_consecutive_losses,
                        "pause_bars_after_streak": pause_bars_after_streak,
                        "max_bars_in_trade": max_bars_in_trade,
                        "max_daily_trades": max_daily_trades,
                        "sweep_lookback": sweep_lookback,
                        "sweep_vol_spike_mult": sweep_vol_spike_mult,
                        "sweep_reversal_bars": sweep_reversal_bars,
                        "warmup_bars": warmup_bars,
                    },
                )
            ],
            logging=LoggingConfig(log_level="INFO"),
        ),
    )


# ── Sweep configs ──────────────────────────────────────────────────────────────

def make_quick_sweep(instruments: list) -> list[BacktestRunConfig]:
    return [
        make_config(instruments=instruments, run_id="LIVE-DEFAULT"),
        make_config(instruments=instruments, atr_sl_multiplier=2.0, atr_tp_multiplier=6.0, run_id="RR-3:1"),
        make_config(instruments=instruments, entry_mode="breakout", atr_sl_multiplier=1.5,
                    atr_tp_multiplier=3.0, bb_squeeze_lookback=40,
                    cooldown_bars=5, run_id="BREAKOUT-FAST"),
        make_config(instruments=instruments, atr_sl_multiplier=2.5, atr_tp_multiplier=5.0,
                    cooldown_bars=20, rvol_threshold=1.5, run_id="CONSERVATIVE"),
        make_config(instruments=instruments, entry_mode="mean_rev", atr_sl_multiplier=1.5,
                    atr_tp_multiplier=3.0, cooldown_bars=5, run_id="MEAN-REV"),
    ]


def make_full_sweep(instruments: list) -> list[BacktestRunConfig]:
    configs = make_quick_sweep(instruments)

    for mode in ["breakout", "mean_rev"]:
        configs.append(make_config(instruments=instruments, entry_mode=mode,
                                   run_id=f"MODE-{mode.upper()}"))

    for sl, tp, name in [(1.5, 3.0, "SL1.5-TP3"), (2.0, 6.0, "SL2-TP6"),
                          (2.5, 5.0, "SL2.5-TP5"), (3.0, 6.0, "SL3-TP6"), (1.0, 3.0, "SL1-TP3")]:
        configs.append(make_config(instruments=instruments, atr_sl_multiplier=sl,
                                   atr_tp_multiplier=tp, run_id=f"ATR-{name}"))

    for cd in [5, 15, 30]:
        configs.append(make_config(instruments=instruments, cooldown_bars=cd, run_id=f"CD-{cd}"))

    for lmin, lmax, smin, smax, name in [
        (40, 70, 30, 60, "RSI-WIDE"), (50, 65, 35, 50, "RSI-NARROW"),
        (35, 75, 25, 65, "RSI-ULTRA-WIDE"),
    ]:
        configs.append(make_config(instruments=instruments, rsi_long_min=lmin, rsi_long_max=lmax,
                                   rsi_short_min=smin, rsi_short_max=smax, run_id=name))

    for period, std, name in [(14, 2.0, "BB14"), (20, 1.5, "BB-TIGHT"), (20, 2.5, "BB-WIDE")]:
        configs.append(make_config(instruments=instruments, bb_period=period, bb_std=std,
                                   run_id=name))

    for fast, med, trend, name in [
        (5, 13, 50, "EMA5-13-50"), (9, 21, 100, "EMA9-21-100"), (12, 26, 50, "EMA12-26-50"),
    ]:
        configs.append(make_config(instruments=instruments, ema_fast=fast, ema_medium=med,
                                   ema_trend=trend, run_id=name))

    for ml, name in [(3, "CB-STRICT"), (5, "CB-DEFAULT"), (8, "CB-LOOSE")]:
        configs.append(make_config(instruments=instruments, max_consecutive_losses=ml,
                                   run_id=name))

    return configs


# ── Reports ────────────────────────────────────────────────────────────────────

REPORTS_DIR = Path(__file__).parent / "reports"


def save_reports(node: BacktestNode, results: list) -> None:
    import json
    from datetime import datetime, timezone

    if not results:
        return

    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    try:
        engines = node.get_engines()
    except Exception:
        engines = []

    for i, result in enumerate(results):
        run_id = (result.run_config_id or f"run_{i + 1}")[:20]
        prefix = REPORTS_DIR / f"{ts}_{run_id}"

        stats_out: dict = {}
        if result.stats_pnls:
            stats_out["stats_pnls"] = result.stats_pnls
        if result.stats_returns:
            stats_out["stats_returns"] = result.stats_returns
        if result.backtest_start and result.backtest_end:
            stats_out["backtest_start_ns"] = result.backtest_start
            stats_out["backtest_end_ns"]   = result.backtest_end

        with open(f"{prefix}_stats.json", "w", encoding="utf-8") as f:
            json.dump(stats_out, f, indent=2, default=str)

        try:
            engine = engines[i] if i < len(engines) else engines[0]

            orders_df = engine.trader.generate_orders_report()
            if orders_df is not None and len(orders_df) > 0:
                orders_df.to_csv(f"{prefix}_orders.csv", index=True)

            positions_df = engine.trader.generate_positions_report()
            if positions_df is not None and len(positions_df) > 0:
                positions_df.to_csv(f"{prefix}_positions.csv", index=True)

            account_df = engine.trader.generate_account_report(Venue(VENUE_NAME))
            if account_df is not None and len(account_df) > 0:
                account_df.to_csv(f"{prefix}_account.csv", index=True)

        except Exception as e:
            print(f"[WARN] save_reports: {e}")

        print(f"  [Saved] reports/{ts}_{run_id}_*.csv / _stats.json")


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    if not CATALOG_PATH.exists():
        print("[ERROR] Catalog not found. Run: python fetch.py")
        return

    catalog = ParquetDataCatalog(str(CATALOG_PATH))
    instruments = catalog.instruments()
    if not instruments:
        print("[ERROR] No instruments in catalog. Run: python fetch.py")
        return

    try:
        ticks = catalog.trade_ticks(instrument_ids=[INSTRUMENT_ID_STR])
        tick_count = len(ticks) if ticks is not None else 0
    except Exception:
        tick_count = 0

    if tick_count == 0:
        print("[ERROR] No TradeTick data. Run: python fetch.py --days 30")
        return

    W = 60
    print("=" * W)
    mode_label = "FULL SWEEP" if FULL_SWEEP else ("SWEEP" if SWEEP_MODE else "SINGLE")
    print(f"  Backtest — {mode_label}".center(W))
    print("=" * W)
    print(f"  Pair      : {instruments[0].id}")
    print(f"  TradeTick : {tick_count:,}")
    print(f"  Bar type  : ValueBar $50k (INTERNAL)")
    print(f"  Balance   : {DEFAULT_BALANCE:,.2f} USDT")
    print(f"  Mode      : {_DEFAULT_MODE}")

    if SWEEP_MODE:
        configs = make_full_sweep(instruments) if FULL_SWEEP else make_quick_sweep(instruments)
    else:
        configs = [make_config(instruments=instruments, run_id="BACKTEST-SINGLE")]

    print(f"  Configs   : {len(configs)}")
    print(f"\n  Running...\n")

    node = BacktestNode(configs=configs)
    results = node.run()
    save_reports(node, results)


if __name__ == "__main__":
    run()
