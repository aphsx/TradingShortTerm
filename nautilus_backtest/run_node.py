"""
run_node.py — Nautilus Trader BacktestNode (High-Level API)
===========================================================
ใช้ Nautilus default reports 100% — ไม่มีการคำนวณเองเลย

Reports ที่แสดง (ผ่าน Nautilus API โดยตรง):
  [1] BacktestResult  — engine.get_result()
  [2] PnL Stats       — result.stats_pnls
  [3] Return Stats    — result.stats_returns
  [4] Order Fills     — engine.trader.generate_order_fills_report()
  [5] Positions       — engine.trader.generate_positions_report()
  [6] Account         — engine.trader.generate_account_report(venue)

วิธีใช้:
    python run_node.py           # single run
    python run_node.py --sweep   # parameter sweep
"""

import sys
from pathlib import Path

from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    ImportableStrategyConfig,
    ImportableFeeModelConfig,
    ImportableFillModelConfig,
    LoggingConfig,
)
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog

CATALOG_PATH      = Path(__file__).parent / "catalog"
VENUE_NAME        = "BINANCE"
SYMBOL            = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"
SWEEP_MODE        = "--sweep" in sys.argv


# ─────────────────────────────────────────────────────────────────────────────
# Config builder
# ─────────────────────────────────────────────────────────────────────────────
def make_run_config(
    *,
    ema_fast: int = 9,
    ema_medium: int = 21,
    ema_slow: int = 200,
    rsi_long_min: float = 50.0,
    rvol_threshold: float = 1.5,
    stop_loss_pct: float = 0.005,
    take_profit_pct: float = 0.010,
    slippage_prob: float = 0.5,
    run_id: str = "BACKTESTER-DEFAULT",
) -> BacktestRunConfig:
    bar_type_str = f"{INSTRUMENT_ID_STR}-1-MINUTE-LAST-EXTERNAL"

    return BacktestRunConfig(
        # สำคัญ: False → engine ยังคงอยู่หลัง run เพื่อให้ generate_*_report() ทำงานได้
        dispose_on_completion=False,

        venues=[
            BacktestVenueConfig(
                name=VENUE_NAME,
                oms_type=OmsType.NETTING,
                account_type=AccountType.MARGIN,
                base_currency="USDT",
                starting_balances=["1000 USDT"],
                fee_model=ImportableFeeModelConfig(
                    fee_model_path="nautilus_trader.backtest.models.fee:MakerTakerFeeModel",
                    config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
                    config={},
                ),
                fill_model=ImportableFillModelConfig(
                    fill_model_path="nautilus_trader.backtest.models.fill:FillModel",
                    config_path="nautilus_trader.backtest.config:FillModelConfig",
                    config={
                        "prob_fill_on_limit": 0.2,
                        "prob_slippage": slippage_prob,
                        "random_seed": 42,
                    },
                ),
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


def make_sweep_configs() -> list[BacktestRunConfig]:
    combos = [
        (9,  21, 1.5, 0.005, 0.010, "EMA9-21_RVOL1.5"),
        (9,  21, 2.0, 0.005, 0.010, "EMA9-21_RVOL2.0"),
        (9,  21, 1.5, 0.003, 0.006, "EMA9-21_SL0.3"),
        (5,  13, 1.5, 0.005, 0.010, "EMA5-13_RVOL1.5"),
        (12, 26, 1.5, 0.005, 0.010, "EMA12-26_RVOL1.5"),
    ]
    return [
        make_run_config(
            ema_fast=f, ema_medium=m, rvol_threshold=r,
            stop_loss_pct=sl, take_profit_pct=tp, run_id=rid,
        )
        for f, m, r, sl, tp, rid in combos
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Nautilus Default Reports — กระชับ ไม่ซ้ำซาก
# ─────────────────────────────────────────────────────────────────────────────
def print_nautilus_reports(node: BacktestNode, results: list) -> None:
    """
    แสดงรายงานจาก Nautilus Trader โดยตรง (ไม่มีการคำนวณเอง)
    """
    if not results:
        print("\n[WARN] No results to report.")
        return

    W = 100
    print("\n" + "=" * W)
    print(" BACKTEST PERFORMANCE SUMMARY ".center(W, "="))
    print("=" * W)

    for i, result in enumerate(results, 1):
        if len(results) > 1:
            print(f"\n+-- CONFIG #{i}: {result.run_config_id[:50]}...")
        else:
            print(f"\n+-- BACKTEST RESULT")
        print("|")

        # ใช้ข้อมูลจาก Nautilus โดยตรง
        if result.stats_pnls:
            pnl = result.stats_pnls.get('USDT', {})
            ret = result.stats_returns

            # คำนวณ Total Fees จาก positions
            total_fees = 0.0
            try:
                engine = node.get_engines()[0]
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

            print(f"| Total PnL         : {total_pnl:>12.2f} USDT ({pnl.get('PnL% (total)', 0):>6.2f}%)")
            print(f"| Total Fees        : {total_fees:>12.2f} USDT")
            print(f"| Net PnL (w/ fees) : {total_pnl - total_fees:>12.2f} USDT")
            print(f"| Win Rate          : {pnl.get('Win Rate', 0) * 100:>12.2f}%")
            print(f"| Profit Factor     : {ret.get('Profit Factor', 0):>12.4f}")
            print(f"| Sharpe Ratio      : {ret.get('Sharpe Ratio (252 days)', 0):>12.4f}")
            print(f"| Sortino Ratio     : {ret.get('Sortino Ratio (252 days)', 0):>12.4f}")
            print(f"| Max Winner        : {pnl.get('Max Winner', 0):>12.2f} USDT")
            print(f"| Max Loser         : {pnl.get('Max Loser', 0):>12.2f} USDT")
            print(f"| Avg Winner        : {pnl.get('Avg Winner', 0):>12.2f} USDT")
            print(f"| Avg Loser         : {pnl.get('Avg Loser', 0):>12.2f} USDT")
        else:
            print("| (No statistics available)")

        print("|")
        print("+-- TRADE SUMMARY")
        print("|")

        try:
            engine = node.get_engines()[0]

            # Orders
            orders = engine.trader.generate_orders_report()
            order_count = len(orders) if orders is not None and hasattr(orders, '__len__') else 0
            print(f"| Total Orders      : {order_count:>12}")

            # Positions
            positions = engine.trader.generate_positions_report()
            if positions is not None and hasattr(positions, '__len__'):
                pos_count = len(positions)
                print(f"| Total Positions   : {pos_count:>12}")

                if pos_count > 0 and 'realized_pnl' in positions.columns:
                    sorted_pos = positions.sort_values('realized_pnl', ascending=False)
                    print("|")
                    print("| Top 5 Best Trades:")
                    for idx, row in sorted_pos.head(5).iterrows():
                        pnl_str = str(row.get('realized_pnl', 'N/A'))
                        price_str = str(row.get('avg_px_open', 'N/A'))[:10]
                        print(f"|    {pnl_str:>20} @ {price_str}")

                    print("|")
                    print("| Top 5 Worst Trades:")
                    for idx, row in sorted_pos.tail(5).iterrows():
                        pnl_str = str(row.get('realized_pnl', 'N/A'))
                        price_str = str(row.get('avg_px_open', 'N/A'))[:10]
                        print(f"|    {pnl_str:>20} @ {price_str}")
            else:
                print(f"| Total Positions   : {0:>12}")

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
        print("+" + "-" * (W - 1))

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

    W = 72
    print("=" * W)
    mode = "SWEEP MODE" if SWEEP_MODE else "SINGLE RUN"
    print(f"  Nautilus BacktestNode — {mode}".center(W))
    print("=" * W)
    print(f"  Catalog    : {CATALOG_PATH.resolve()}")
    print(f"  Instrument : {instruments[0].id}")

    configs = make_sweep_configs() if SWEEP_MODE else [make_run_config(run_id="BACKTESTER-SINGLE")]
    print(f"  Configs    : {len(configs)}")

    print(f"\nRunning {len(configs)} backtest(s)...\n")
    node = BacktestNode(configs=configs)
    results = node.run()

    print_nautilus_reports(node, results)

    print("=" * W)
    print("  [DONE] All Nautilus default reports shown".center(W))
    print("=" * W)


if __name__ == "__main__":
    run()
