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
            logging=LoggingConfig(log_level="WARNING"),
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
def print_reports(node: BacktestNode, results: list) -> None:
    if not results:
        print("\n[WARN] No results.")
        return

    W = 100
    print("\n" + "=" * W)
    print(" BACKTEST PERFORMANCE SUMMARY ".center(W, "="))
    print("=" * W)

    summary_data = []
    engines = node.get_engines()

    for i, result in enumerate(results):
        run_id = result.run_config_id[:60] if result.run_config_id else f"#{i+1}"

        print(f"\n{'─' * W}")
        print(f"  [{i+1}] {run_id}")
        print(f"{'─' * W}")

        # Period
        if result.backtest_start and result.backtest_end:
            from datetime import datetime, timezone
            s = datetime.fromtimestamp(result.backtest_start / 1e9, tz=timezone.utc)
            e = datetime.fromtimestamp(result.backtest_end / 1e9, tz=timezone.utc)
            days = (result.backtest_end - result.backtest_start) / 1e9 / 86400
            print(f"  Period : {s.strftime('%Y-%m-%d')} → {e.strftime('%Y-%m-%d')} ({days:.0f} days)")

        total_pnl = 0.0
        total_fees = 0.0
        win_rate = 0.0
        sharpe = 0.0
        sortino = 0.0
        pf = 0.0

        if result.stats_pnls:
            pnl_stats = result.stats_pnls.get('USDT', {})
            ret_stats = result.stats_returns or {}

            total_pnl = pnl_stats.get('PnL (total)', 0)
            win_rate = pnl_stats.get('Win Rate', 0) * 100
            pf = ret_stats.get('Profit Factor', 0)
            sharpe = ret_stats.get('Sharpe Ratio (252 days)', 0)
            sortino = ret_stats.get('Sortino Ratio (252 days)', 0)

            # Fees
            try:
                engine = engines[i] if i < len(engines) else engines[0]
                positions = engine.trader.generate_positions_report()
                if positions is not None and len(positions) > 0:
                    if 'commissions' in positions.columns:
                        import re
                        for comm in positions['commissions']:
                            if comm and str(comm) != 'nan':
                                match = re.search(r'([\d.]+)\s*USDT', str(comm))
                                if match:
                                    total_fees += float(match.group(1))
            except Exception:
                pass

            net = total_pnl - total_fees
            pnl_pct = pnl_stats.get('PnL% (total)', 0)

            avg_w = pnl_stats.get('Avg Winner', 0)
            avg_l = abs(pnl_stats.get('Avg Loser', 0))
            rr = avg_w / avg_l if avg_l > 0 else 0

            print(f"  PnL    : {total_pnl:>+10.2f} USDT ({pnl_pct:>+.2f}%)")
            print(f"  Fees   : {total_fees:>10.2f} USDT")
            print(f"  Net    : {net:>+10.2f} USDT")
            print(f"  WinRate: {win_rate:>6.1f}%  |  PF: {pf:.3f}  |  R:R: {rr:.2f}x")
            print(f"  Sharpe : {sharpe:>+.4f}  |  Sortino: {sortino:>+.4f}")
            print(f"  AvgWin : {avg_w:>+.2f}  |  AvgLoss: {pnl_stats.get('Avg Loser', 0):>+.2f}")
            print(f"  MaxWin : {pnl_stats.get('Max Winner', 0):>+.2f}  |  MaxLoss: {pnl_stats.get('Max Loser', 0):>+.2f}")

            summary_data.append({
                'id': run_id, 'net': net, 'wr': win_rate,
                'sharpe': sharpe, 'pf': pf, 'rr': rr,
            })

        # Trade count + balance
        try:
            engine = engines[i] if i < len(engines) else engines[0]
            orders = engine.trader.generate_orders_report()
            positions = engine.trader.generate_positions_report()
            n_ord = len(orders) if orders is not None else 0
            n_pos = len(positions) if positions is not None else 0
            print(f"  Orders : {n_ord}  |  Positions: {n_pos}")

            venue = Venue(VENUE_NAME)
            account = engine.trader.generate_account_report(venue)
            if account is not None and len(account) > 0:
                try:
                    final_val = account.iloc[-1]['total']
                    init_val = account.iloc[0]['total']
                    # Handle both numeric and string types
                    if isinstance(final_val, str):
                        final_bal = float(final_val.replace(',', ''))
                    else:
                        final_bal = float(final_val)
                    if isinstance(init_val, str):
                        init_bal = float(init_val.replace(',', ''))
                    else:
                        init_bal = float(init_val)
                    print(f"  Balance: {init_bal:,.2f} → {final_bal:,.2f} USDT ({final_bal - init_bal:>+.2f})")
                except Exception:
                    pass
        except Exception as e:
            print(f"  (Report error: {e})")

    # Comparison table
    if len(summary_data) > 1:
        print(f"\n{'=' * W}")
        print(" RANKING ".center(W, "="))
        print(f"{'=' * W}")
        print(f"  {'#':<3} {'Config':<30} {'Net PnL':>10} {'Win%':>7} {'Sharpe':>8} {'PF':>7} {'R:R':>6}")
        print(f"  {'─'*3} {'─'*30} {'─'*10} {'─'*7} {'─'*8} {'─'*7} {'─'*6}")

        summary_data.sort(key=lambda x: x['net'], reverse=True)
        for rank, d in enumerate(summary_data, 1):
            medal = "🏆" if rank == 1 else "  "
            print(
                f"{medal}{rank:<3} {d['id'][:28]:<30} "
                f"{d['net']:>+9.2f} {d['wr']:>6.1f}% "
                f"{d['sharpe']:>+8.4f} {d['pf']:>7.3f} {d['rr']:>5.2f}x"
            )

        best = summary_data[0]
        print(f"\n  🏆 Best: {best['id']}")
        print(f"     Net: {best['net']:+.2f} | WR: {best['wr']:.1f}% | Sharpe: {best['sharpe']:+.4f} | R:R: {best['rr']:.2f}x")

    print(f"\n{'=' * W}\n")


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
    print_reports(node, results)


if __name__ == "__main__":
    run()
