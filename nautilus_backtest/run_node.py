"""
run_node.py — Nautilus Trader BacktestNode (AMS Scalper)
========================================================
รัน AMS Scalper (Adaptive Multi-Signal Scalper) บน Nautilus BacktestNode

Reports:
  [1] BacktestResult  — engine.get_result()
  [2] PnL Stats       — result.stats_pnls
  [3] Return Stats    — result.stats_returns
  [4] Order Fills     — engine.trader.generate_order_fills_report()
  [5] Positions       — engine.trader.generate_positions_report()
  [6] Account         — engine.trader.generate_account_report(venue)

วิธีใช้:
    python run_node.py                   # single run (AMS Scalper)
    python run_node.py --sweep           # parameter sweep
    python run_node.py --balance 5000    # override balance
    python run_node.py --legacy          # ใช้ MFT Strategy เดิม (เปรียบเทียบ)
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

# Load .env file
load_dotenv(Path(__file__).parent.parent / ".env")

CATALOG_PATH      = Path(__file__).parent / "catalog"
VENUE_NAME        = "BINANCE"
SYMBOL            = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"
SWEEP_MODE        = "--sweep" in sys.argv
LEGACY_MODE       = "--legacy" in sys.argv

# Get initial balance from .env or default
DEFAULT_BALANCE = float(os.getenv("BACKTEST_INITIAL_BALANCE", "1000.0"))

# Check for --balance override
if "--balance" in sys.argv:
    idx = sys.argv.index("--balance")
    if idx + 1 < len(sys.argv):
        DEFAULT_BALANCE = float(sys.argv[idx + 1])


# ─────────────────────────────────────────────────────────────────────────────
# AMS Scalper Config Builder
# ─────────────────────────────────────────────────────────────────────────────
def make_ams_config(
    *,
    # Layer 1: Trend
    ema_trend: int = 50,
    ema_fast: int = 9,
    ema_medium: int = 21,
    vwap_period: int = 20,
    # Layer 2: Entry
    bb_period: int = 20,
    bb_std: float = 2.0,
    bb_squeeze_lookback: int = 50,
    rsi_period: int = 14,
    rsi_long_min: float = 40.0,
    rsi_long_max: float = 70.0,
    rsi_short_min: float = 30.0,
    rsi_short_max: float = 60.0,
    rvol_threshold: float = 1.2,
    entry_mode: str = "hybrid",
    # Layer 3: Risk
    atr_period: int = 14,
    atr_sl_multiplier: float = 1.5,
    atr_tp_multiplier: float = 2.0,
    trailing_activate_pct: float = 0.003,
    trailing_step_pct: float = 0.001,
    trade_size: float = 0.001,
    cooldown_bars: int = 5,
    max_loss_streak: int = 3,
    pause_bars_after_streak: int = 30,
    warmup_bars: int = 60,
    # Account
    initial_balance: float = DEFAULT_BALANCE,
    run_id: str = "AMS-DEFAULT",
) -> BacktestRunConfig:
    """สร้าง BacktestRunConfig สำหรับ AMS Scalper"""
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
                        "atr_period": atr_period,
                        "atr_sl_multiplier": atr_sl_multiplier,
                        "atr_tp_multiplier": atr_tp_multiplier,
                        "trailing_activate_pct": trailing_activate_pct,
                        "trailing_step_pct": trailing_step_pct,
                        "trade_size": trade_size,
                        "cooldown_bars": cooldown_bars,
                        "max_loss_streak": max_loss_streak,
                        "pause_bars_after_streak": pause_bars_after_streak,
                        "warmup_bars": warmup_bars,
                        "entry_mode": entry_mode,
                    },
                )
            ],
            logging=LoggingConfig(log_level="WARNING"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Legacy MFT Config Builder (backward-compatible)
# ─────────────────────────────────────────────────────────────────────────────
def make_legacy_config(
    *,
    ema_fast: int = 9,
    ema_medium: int = 21,
    ema_slow: int = 200,
    rsi_long_min: float = 50.0,
    rvol_threshold: float = 1.5,
    stop_loss_pct: float = 0.005,
    take_profit_pct: float = 0.010,
    initial_balance: float = DEFAULT_BALANCE,
    run_id: str = "MFT-LEGACY",
) -> BacktestRunConfig:
    """Legacy MFT strategy config (เพื่อเปรียบเทียบ)"""
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
                    strategy_path="strategies.mft_strategy:MFTStrategy",
                    config_path="strategies.mft_strategy:MFTConfig",
                    config={
                        "instrument_id": INSTRUMENT_ID_STR,
                        "bar_type": bar_type_str,
                        "ema_fast": ema_fast,
                        "ema_medium": ema_medium,
                        "ema_slow": ema_slow,
                        "rsi_period": 14,
                        "rsi_long_min": rsi_long_min,
                        "rsi_long_max": rsi_long_min + 15.0,
                        "rsi_short_min": (100 - rsi_long_min) - 15.0,
                        "rsi_short_max": 100 - rsi_long_min,
                        "rvol_period": 20,
                        "rvol_threshold": rvol_threshold,
                        "trade_size": 0.001,
                        "stop_loss_pct": stop_loss_pct,
                        "take_profit_pct": take_profit_pct,
                        "warmup_bars": ema_slow + 10,
                    },
                )
            ],
            logging=LoggingConfig(log_level="WARNING"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sweep Configs — ทดสอบหลายพารามิเตอร์
# ─────────────────────────────────────────────────────────────────────────────
def make_sweep_configs() -> list[BacktestRunConfig]:
    """
    Parameter sweep สำหรับ AMS Scalper
    ทดสอบหลายชุดเพื่อหาค่าที่ดีที่สุด
    """
    configs = []

    # ═══ Group 1: Entry Mode Comparison ═══
    for mode in ["breakout", "mean_rev", "hybrid"]:
        configs.append(make_ams_config(
            entry_mode=mode,
            run_id=f"AMS-MODE-{mode.upper()}",
        ))

    # ═══ Group 2: ATR Multiplier Variations ═══
    atr_combos = [
        (1.0, 1.5, "ATR_SL1.0_TP1.5"),   # Tight SL, Moderate TP
        (1.5, 2.0, "ATR_SL1.5_TP2.0"),   # Default
        (1.5, 3.0, "ATR_SL1.5_TP3.0"),   # Wide TP (R:R = 2:1)
        (2.0, 3.0, "ATR_SL2.0_TP3.0"),   # Loose SL, Wide TP
        (1.0, 2.0, "ATR_SL1.0_TP2.0"),   # Tight SL, R:R = 2:1
    ]
    for sl, tp, name in atr_combos:
        configs.append(make_ams_config(
            atr_sl_multiplier=sl,
            atr_tp_multiplier=tp,
            run_id=f"AMS-{name}",
        ))

    # ═══ Group 3: BB + Squeeze Settings ═══
    bb_combos = [
        (20, 2.0, 50, "BB20_STD2_SQ50"),   # Default
        (20, 1.5, 50, "BB20_STD1.5_SQ50"),  # Tighter BB
        (14, 2.0, 30, "BB14_STD2_SQ30"),    # Faster BB
        (20, 2.5, 50, "BB20_STD2.5_SQ50"),  # Wider BB
    ]
    for period, std, sq, name in bb_combos:
        configs.append(make_ams_config(
            bb_period=period,
            bb_std=std,
            bb_squeeze_lookback=sq,
            run_id=f"AMS-{name}",
        ))

    # ═══ Group 4: Trailing Stop Variations ═══
    trail_combos = [
        (0.002, 0.001, "TRAIL_0.2%_0.1%"),   # Tight trailing
        (0.003, 0.001, "TRAIL_0.3%_0.1%"),   # Default
        (0.005, 0.002, "TRAIL_0.5%_0.2%"),   # Loose trailing
        (0.004, 0.0015, "TRAIL_0.4%_0.15%"), # Medium
    ]
    for activate, step, name in trail_combos:
        configs.append(make_ams_config(
            trailing_activate_pct=activate,
            trailing_step_pct=step,
            run_id=f"AMS-{name}",
        ))

    # ═══ Group 5: Cooldown & Loss Streak ═══
    cd_combos = [
        (3,  3, 20, "CD3_LS3_P20"),    # Aggressive
        (5,  3, 30, "CD5_LS3_P30"),    # Default
        (10, 5, 60, "CD10_LS5_P60"),   # Conservative
    ]
    for cd, ls, pause, name in cd_combos:
        configs.append(make_ams_config(
            cooldown_bars=cd,
            max_loss_streak=ls,
            pause_bars_after_streak=pause,
            run_id=f"AMS-{name}",
        ))

    # ═══ Group 6: RSI Range Variations ═══
    rsi_combos = [
        (40, 70, 30, 60, "RSI_40-70_30-60"),  # Default (wide)
        (45, 65, 35, 55, "RSI_45-65_35-55"),  # Medium
        (35, 75, 25, 65, "RSI_35-75_25-65"),  # Very wide
        (50, 65, 35, 50, "RSI_ORIG"),          # Original MFT range
    ]
    for lmin, lmax, smin, smax, name in rsi_combos:
        configs.append(make_ams_config(
            rsi_long_min=lmin,
            rsi_long_max=lmax,
            rsi_short_min=smin,
            rsi_short_max=smax,
            run_id=f"AMS-{name}",
        ))

    # ═══ Group 7: vs Legacy MFT (comparison) ═══
    configs.append(make_legacy_config(run_id="LEGACY-MFT-DEFAULT"))

    return configs


def make_quick_sweep_configs() -> list[BacktestRunConfig]:
    """Quick sweep — เฉพาะ configs สำคัญ (เร็วกว่า full sweep)"""
    return [
        # AMS defaults
        make_ams_config(run_id="AMS-DEFAULT"),
        # Best candidates
        make_ams_config(
            entry_mode="hybrid",
            atr_sl_multiplier=1.5,
            atr_tp_multiplier=3.0,
            trailing_activate_pct=0.003,
            run_id="AMS-BEST-RR",
        ),
        make_ams_config(
            entry_mode="breakout",
            atr_sl_multiplier=1.0,
            atr_tp_multiplier=2.0,
            bb_squeeze_lookback=30,
            run_id="AMS-TIGHT-BREAKOUT",
        ),
        make_ams_config(
            entry_mode="mean_rev",
            atr_sl_multiplier=2.0,
            atr_tp_multiplier=3.0,
            cooldown_bars=3,
            run_id="AMS-MEAN-REV-LOOSE",
        ),
        # Legacy comparison
        make_legacy_config(run_id="LEGACY-MFT"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────
def print_reports(node: BacktestNode, results: list) -> None:
    """แสดงรายงานจาก Nautilus Trader"""
    if not results:
        print("\n[WARN] No results to report.")
        return

    W = 100
    print("\n" + "=" * W)
    print(" BACKTEST PERFORMANCE SUMMARY ".center(W, "="))
    print("=" * W)

    summary_data = []

    for i, result in enumerate(results, 1):
        run_id = result.run_config_id[:60] if result.run_config_id else f"Config #{i}"

        if len(results) > 1:
            print(f"\n{'─' * W}")
            print(f"  CONFIG #{i}: {run_id}")
            print(f"{'─' * W}")
        else:
            print(f"\n+-- BACKTEST RESULT: {run_id}")

        print("|")

        # Period info
        if result.backtest_start and result.backtest_end:
            from datetime import datetime, timezone
            start_dt = datetime.fromtimestamp(
                result.backtest_start / 1_000_000_000, tz=timezone.utc
            )
            end_dt = datetime.fromtimestamp(
                result.backtest_end / 1_000_000_000, tz=timezone.utc
            )
            days = (result.backtest_end - result.backtest_start) / 1_000_000_000 / 86400
            print(f"| Period            : {start_dt.strftime('%Y-%m-%d')} → {end_dt.strftime('%Y-%m-%d')} ({days:.1f} days)")
            print("|")

        # PnL Stats
        total_pnl = 0.0
        total_fees = 0.0
        win_rate = 0.0
        sharpe = 0.0
        sortino = 0.0
        profit_factor = 0.0
        max_dd = 0.0

        if result.stats_pnls:
            pnl = result.stats_pnls.get('USDT', {})
            ret = result.stats_returns

            # Fees
            try:
                engine = node.get_engines()[0] if i == 1 else node.get_engines()[i - 1]
                positions = engine.trader.generate_positions_report()
                if positions is not None and hasattr(positions, '__len__') and len(positions) > 0:
                    if 'commissions' in positions.columns:
                        import re
                        for comm in positions['commissions']:
                            if comm and str(comm) != 'nan':
                                match = re.search(r'([\d.]+)\s*USDT', str(comm))
                                if match:
                                    total_fees += float(match.group(1))
            except:
                pass

            total_pnl = pnl.get('PnL (total)', 0)
            win_rate = pnl.get('Win Rate', 0) * 100
            profit_factor = ret.get('Profit Factor', 0)
            sharpe = ret.get('Sharpe Ratio (252 days)', 0)
            sortino = ret.get('Sortino Ratio (252 days)', 0)
            max_dd = ret.get('Max Drawdown', 0) * 100

            net_pnl = total_pnl - total_fees

            # ═══ Performance Metrics ═══
            print(f"| {'─── Performance ───':^40}")
            print(f"| Total PnL         : {total_pnl:>12.2f} USDT ({pnl.get('PnL% (total)', 0):>6.2f}%)")
            print(f"| Total Fees        : {total_fees:>12.2f} USDT")
            print(f"| Net PnL (w/ fees) : {net_pnl:>12.2f} USDT")
            print(f"|")
            print(f"| {'─── Risk Metrics ───':^40}")
            print(f"| Win Rate          : {win_rate:>12.2f}%")
            print(f"| Profit Factor     : {profit_factor:>12.4f}")
            print(f"| Sharpe Ratio      : {sharpe:>12.4f}")
            print(f"| Sortino Ratio     : {sortino:>12.4f}")
            print(f"| Max Drawdown      : {max_dd:>12.2f}%")
            print(f"|")
            print(f"| {'─── Trade Stats ───':^40}")
            print(f"| Max Winner        : {pnl.get('Max Winner', 0):>12.2f} USDT")
            print(f"| Max Loser         : {pnl.get('Max Loser', 0):>12.2f} USDT")
            print(f"| Avg Winner        : {pnl.get('Avg Winner', 0):>12.2f} USDT")
            print(f"| Avg Loser         : {pnl.get('Avg Loser', 0):>12.2f} USDT")

            # Calculate Avg Win / Avg Loss ratio
            avg_win = abs(pnl.get('Avg Winner', 0))
            avg_loss = abs(pnl.get('Avg Loser', 0))
            if avg_loss > 0:
                rr_ratio = avg_win / avg_loss
                print(f"| Avg Win/Loss Ratio: {rr_ratio:>12.2f}x")

            summary_data.append({
                'id': run_id,
                'net_pnl': net_pnl,
                'win_rate': win_rate,
                'sharpe': sharpe,
                'profit_factor': profit_factor,
                'max_dd': max_dd,
            })
        else:
            print("| (No statistics available)")

        print("|")
        print(f"| {'─── Trade Summary ───':^40}")
        print("|")

        try:
            engine = node.get_engines()[0] if i == 1 else node.get_engines()[i - 1]

            orders = engine.trader.generate_orders_report()
            order_count = len(orders) if orders is not None and hasattr(orders, '__len__') else 0
            print(f"| Total Orders      : {order_count:>12}")

            positions = engine.trader.generate_positions_report()
            if positions is not None and hasattr(positions, '__len__'):
                pos_count = len(positions)
                print(f"| Total Positions   : {pos_count:>12}")

                if pos_count > 0 and 'realized_pnl' in positions.columns:
                    sorted_pos = positions.sort_values('realized_pnl', ascending=False)
                    print("|")
                    print("| Top 5 Best Trades:")
                    for _, row in sorted_pos.head(5).iterrows():
                        pnl_str = str(row.get('realized_pnl', 'N/A'))
                        price_str = str(row.get('avg_px_open', 'N/A'))[:10]
                        print(f"|    {pnl_str:>20} @ {price_str}")

                    print("|")
                    print("| Top 5 Worst Trades:")
                    for _, row in sorted_pos.tail(5).iterrows():
                        pnl_str = str(row.get('realized_pnl', 'N/A'))
                        price_str = str(row.get('avg_px_open', 'N/A'))[:10]
                        print(f"|    {pnl_str:>20} @ {price_str}")

            # Account Balance
            venue = Venue(VENUE_NAME)
            account = engine.trader.generate_account_report(venue)
            if account is not None and hasattr(account, '__len__') and len(account) > 0:
                final_balance = account.iloc[-1]['total']
                initial_balance = account.iloc[0]['total']
                print("|")
                print(f"| Initial Balance   : {initial_balance:>12.2f} USDT")
                print(f"| Final Balance     : {final_balance:>12.2f} USDT")
                print(f"| Net Change        : {final_balance - initial_balance:>12.2f} USDT")

        except Exception as e:
            print(f"| (Error: {e})")

        print("|")
        print("+" + "─" * (W - 1))

    # ═══ Comparison Table (for sweep mode) ═══
    if len(summary_data) > 1:
        print("\n" + "=" * W)
        print(" COMPARISON TABLE ".center(W, "="))
        print("=" * W)
        print(f"{'Config':<35} {'Net PnL':>10} {'Win%':>7} {'Sharpe':>8} {'PF':>8} {'MaxDD%':>8}")
        print("─" * W)

        # Sort by Net PnL descending
        summary_data.sort(key=lambda x: x['net_pnl'], reverse=True)

        for d in summary_data:
            short_id = d['id'][:33]
            pnl_color = "+" if d['net_pnl'] > 0 else ""
            print(
                f"{short_id:<35} "
                f"{pnl_color}{d['net_pnl']:>9.2f} "
                f"{d['win_rate']:>6.1f}% "
                f"{d['sharpe']:>8.4f} "
                f"{d['profit_factor']:>8.4f} "
                f"{d['max_dd']:>7.2f}%"
            )

        # Best config
        best = summary_data[0]
        print(f"\n{'─' * W}")
        print(f"  🏆 BEST CONFIG: {best['id']}")
        print(f"     Net PnL: {best['net_pnl']:+.2f} USDT | Win Rate: {best['win_rate']:.1f}% | Sharpe: {best['sharpe']:.4f}")
        print(f"{'─' * W}")

    print("=" * W)


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
        print("[ERROR] No instruments in catalog. Re-run: python fetch_data.py")
        return

    W = 80
    print("=" * W)
    strategy_name = "MFT (Legacy)" if LEGACY_MODE else "AMS Scalper"
    mode = "SWEEP" if SWEEP_MODE else "SINGLE RUN"
    print(f"  Nautilus BacktestNode — {strategy_name} [{mode}]".center(W))
    print("=" * W)
    print(f"  Catalog    : {CATALOG_PATH.resolve()}")
    print(f"  Instrument : {instruments[0].id}")
    print(f"  Balance    : {DEFAULT_BALANCE:,.2f} USDT")
    print(f"  Strategy   : {strategy_name}")

    if LEGACY_MODE:
        configs = [make_legacy_config(run_id="LEGACY-SINGLE")]
    elif SWEEP_MODE:
        if "--full" in sys.argv:
            configs = make_sweep_configs()
        else:
            configs = make_quick_sweep_configs()
    else:
        configs = [make_ams_config(run_id="AMS-SINGLE")]

    print(f"  Configs    : {len(configs)}")

    print(f"\nRunning {len(configs)} backtest(s)...\n")
    node = BacktestNode(configs=configs)
    results = node.run()

    print_reports(node, results)

    print("=" * W)
    print("  [DONE] Backtest complete".center(W))
    print("=" * W)


if __name__ == "__main__":
    run()
