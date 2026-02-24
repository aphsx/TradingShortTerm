"""
run_node.py — Nautilus Trader BacktestNode (AMS Scalper v2)
============================================================
วิธีใช้:
    python run_node.py                   # single run
    python run_node.py --sweep           # parameter sweep (5 configs)
    python run_node.py --sweep --full    # full sweep (20+ configs)
    python run_node.py --balance 5000    # override balance
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
    ImportableStrategyConfig,
    LoggingConfig,
)
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog

# Load .env
load_dotenv(Path(__file__).parent.parent / ".env")

CATALOG_PATH      = Path(__file__).parent / "catalog"
VENUE_NAME        = "BINANCE"
SYMBOL            = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"
SWEEP_MODE        = "--sweep" in sys.argv
FULL_SWEEP        = "--full" in sys.argv

DEFAULT_BALANCE = float(os.getenv("BACKTEST_INITIAL_BALANCE", "10000.0"))
if "--balance" in sys.argv:
    idx = sys.argv.index("--balance")
    if idx + 1 < len(sys.argv):
        DEFAULT_BALANCE = float(sys.argv[idx + 1])


# ─────────────────────────────────────────────────────────────────────────────
# Config Builder
# ─────────────────────────────────────────────────────────────────────────────
def make_config(
    *,
    ema_trend: int = 50,
    ema_fast: int = 9,
    ema_medium: int = 21,
    vwap_period: int = 20,
    bb_period: int = 20,
    bb_std: float = 2.0,
    bb_squeeze_lookback: int = 60,
    rsi_period: int = 14,
    rsi_long_min: float = 45.0,
    rsi_long_max: float = 68.0,
    rsi_short_min: float = 32.0,
    rsi_short_max: float = 55.0,
    rvol_threshold: float = 1.3,
    min_ema_spread_pct: float = 0.0005,
    min_atr_pct: float = 0.001,
    atr_period: int = 14,
    atr_sl_multiplier: float = 2.0,
    atr_tp_multiplier: float = 4.0,
    trailing_activate_atr: float = 2.0,
    trailing_distance_atr: float = 1.0,
    trade_size: float = 0.001,
    cooldown_bars: int = 10,
    max_loss_streak: int = 3,
    pause_bars_after_streak: int = 60,
    max_bars_in_trade: int = 120,
    warmup_bars: int = 80,
    entry_mode: str = "hybrid",
    initial_balance: float = DEFAULT_BALANCE,
    run_id: str = "AMS-DEFAULT",
) -> BacktestRunConfig:
    bar_type_str = f"{INSTRUMENT_ID_STR}-1-MINUTE-LAST-EXTERNAL"

    return BacktestRunConfig(
        dispose_on_completion=False,
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
                data_cls=Bar,
                instrument_id=InstrumentId.from_str(INSTRUMENT_ID_STR),
                bar_spec=bar_type_str,
            )
        ],
        engine=BacktestEngineConfig(
            trader_id=run_id,
            strategies=[
                ImportableStrategyConfig(
                    strategy_path="strategies.ams_scalper:AMSScalper",
                    config_path="strategies.ams_scalper:AMSConfig",
                    config={
                        "instrument_id": INSTRUMENT_ID_STR,
                        "bar_type": bar_type_str,
                        "ema_trend": ema_trend,
                        "ema_fast": ema_fast,
                        "ema_medium": ema_medium,
                        "vwap_period": vwap_period,
                        "bb_period": bb_period,
                        "bb_std": bb_std,
                        "bb_squeeze_lookback": bb_squeeze_lookback,
                        "rsi_period": rsi_period,
                        "rsi_long_min": rsi_long_min,
                        "rsi_long_max": rsi_long_max,
                        "rsi_short_min": rsi_short_min,
                        "rsi_short_max": rsi_short_max,
                        "rvol_threshold": rvol_threshold,
                        "min_ema_spread_pct": min_ema_spread_pct,
                        "min_atr_pct": min_atr_pct,
                        "atr_period": atr_period,
                        "atr_sl_multiplier": atr_sl_multiplier,
                        "atr_tp_multiplier": atr_tp_multiplier,
                        "trailing_activate_atr": trailing_activate_atr,
                        "trailing_distance_atr": trailing_distance_atr,
                        "trade_size": trade_size,
                        "cooldown_bars": cooldown_bars,
                        "max_loss_streak": max_loss_streak,
                        "pause_bars_after_streak": pause_bars_after_streak,
                        "max_bars_in_trade": max_bars_in_trade,
                        "warmup_bars": warmup_bars,
                        "entry_mode": entry_mode,
                    },
                )
            ],
            logging=LoggingConfig(log_level="INFO"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sweep Configs
# ─────────────────────────────────────────────────────────────────────────────
def make_quick_sweep() -> list[BacktestRunConfig]:
    """Quick sweep — 5 key configs"""
    return [
        make_config(run_id="DEFAULT"),
        # Better R:R
        make_config(atr_sl_multiplier=2.0, atr_tp_multiplier=6.0,
                    run_id="RR-3:1"),
        # Tight breakout
        make_config(entry_mode="breakout", atr_sl_multiplier=1.5,
                    atr_tp_multiplier=3.0, bb_squeeze_lookback=40,
                    cooldown_bars=5, run_id="BREAKOUT-FAST"),
        # Conservative
        make_config(atr_sl_multiplier=2.5, atr_tp_multiplier=5.0,
                    cooldown_bars=20, rvol_threshold=1.5,
                    run_id="CONSERVATIVE"),
        # Aggressive mean reversion
        make_config(entry_mode="mean_rev", atr_sl_multiplier=1.5,
                    atr_tp_multiplier=3.0, cooldown_bars=5,
                    run_id="MEAN-REV"),
    ]


def make_full_sweep() -> list[BacktestRunConfig]:
    """Full sweep — 20+ configs"""
    configs = make_quick_sweep()

    # Entry modes
    for mode in ["breakout", "mean_rev"]:
        configs.append(make_config(entry_mode=mode, run_id=f"MODE-{mode.upper()}"))

    # ATR SL/TP combos
    for sl, tp, name in [
        (1.5, 3.0, "SL1.5-TP3"),
        (2.0, 6.0, "SL2-TP6"),
        (2.5, 5.0, "SL2.5-TP5"),
        (3.0, 6.0, "SL3-TP6"),
        (1.0, 3.0, "SL1-TP3"),
    ]:
        configs.append(make_config(
            atr_sl_multiplier=sl, atr_tp_multiplier=tp, run_id=f"ATR-{name}"))

    # Cooldown
    for cd in [5, 15, 30]:
        configs.append(make_config(cooldown_bars=cd, run_id=f"CD-{cd}"))

    # RSI ranges
    for lmin, lmax, smin, smax, name in [
        (40, 70, 30, 60, "RSI-WIDE"),
        (50, 65, 35, 50, "RSI-NARROW"),
        (35, 75, 25, 65, "RSI-ULTRA-WIDE"),
    ]:
        configs.append(make_config(
            rsi_long_min=lmin, rsi_long_max=lmax,
            rsi_short_min=smin, rsi_short_max=smax, run_id=name))

    # BB settings
    for period, std, name in [
        (14, 2.0, "BB14"),
        (20, 1.5, "BB-TIGHT"),
        (20, 2.5, "BB-WIDE"),
    ]:
        configs.append(make_config(bb_period=period, bb_std=std, run_id=name))

    # EMA combos
    for fast, med, trend, name in [
        (5, 13, 50, "EMA5-13-50"),
        (9, 21, 100, "EMA9-21-100"),
        (12, 26, 50, "EMA12-26-50"),
    ]:
        configs.append(make_config(
            ema_fast=fast, ema_medium=med, ema_trend=trend, run_id=name))

    return configs


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────
REPORTS_DIR = Path(__file__).parent / "reports"

def save_reports(node: BacktestNode, results: list) -> None:
    """บันทึก orders/positions/account/stats ลงไฟล์ใน reports/ (ไม่แสดง terminal)"""
    import json
    import pandas as pd
    from datetime import datetime, timezone

    if not results:
        return

    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    engines = node.get_engines()

    for i, result in enumerate(results):
        run_id = (result.run_config_id or f"run_{i+1}")[:20]
        prefix = REPORTS_DIR / f"{ts}_{run_id}"

        # ── 1. stats_pnls + stats_returns → JSON ──────────────────────────────
        stats_out: dict = {}
        if result.stats_pnls:
            stats_out["stats_pnls"] = result.stats_pnls
        if result.stats_returns:
            stats_out["stats_returns"] = result.stats_returns
        if result.backtest_start and result.backtest_end:
            stats_out["backtest_start_ns"] = result.backtest_start
            stats_out["backtest_end_ns"]   = result.backtest_end

        stats_file = Path(f"{prefix}_stats.json")
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats_out, f, indent=2, default=str)

        # ── 2. orders / positions / account → CSV ─────────────────────────────
        try:
            engine = engines[i] if i < len(engines) else engines[0]

            orders_df = engine.trader.generate_orders_report()
            if orders_df is not None and len(orders_df) > 0:
                orders_df.to_csv(f"{prefix}_orders.csv", index=True)

            positions_df = engine.trader.generate_positions_report()
            if positions_df is not None and len(positions_df) > 0:
                positions_df.to_csv(f"{prefix}_positions.csv", index=True)

            venue = Venue(VENUE_NAME)
            account_df = engine.trader.generate_account_report(venue)
            if account_df is not None and len(account_df) > 0:
                account_df.to_csv(f"{prefix}_account.csv", index=True)

        except Exception as e:
            print(f"[WARN] save_reports error: {e}")

        print(f"\n  [Saved] reports/{ts}_{run_id}_*.csv / _stats.json")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def run():
    if not CATALOG_PATH.exists():
        print("[ERROR] Catalog not found! Run: python fetch_data.py")
        return

    catalog = ParquetDataCatalog(str(CATALOG_PATH))
    instruments = catalog.instruments()
    if not instruments:
        print("[ERROR] No instruments. Re-run: python fetch_data.py")
        return

    W = 72
    print("=" * W)
    mode = "FULL SWEEP" if FULL_SWEEP else ("SWEEP" if SWEEP_MODE else "SINGLE")
    print(f"  AMS Scalper v2 — {mode}".center(W))
    print("=" * W)
    print(f"  Catalog  : {CATALOG_PATH.resolve()}")
    print(f"  Pair     : {instruments[0].id}")
    print(f"  Balance  : {DEFAULT_BALANCE:,.2f} USDT")

    if SWEEP_MODE:
        configs = make_full_sweep() if FULL_SWEEP else make_quick_sweep()
    else:
        configs = [make_config(run_id="AMS-SINGLE")]

    print(f"  Configs  : {len(configs)}")
    print(f"\n  Running {len(configs)} backtest(s)...\n")

    node = BacktestNode(configs=configs)
    results = node.run()
    save_reports(node, results)


if __name__ == "__main__":
    run()
