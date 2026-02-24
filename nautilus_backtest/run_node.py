"""
run_node.py — Nautilus Trader BacktestNode (High-Level API)
===========================================================
High-level approach: ใช้ Config objects ล้วน
- ไม่ต้อง setup venue / instrument / data ด้วยตัวเอง
- BacktestNode จัดการทุกอย่างอัตโนมัติจาก catalog
- รองรับ run หลาย config พร้อมกัน (parameter sweep)

ต้องรัน setup_catalog.py ก่อน 1 ครั้ง

วิธีใช้:
    python run_node.py

Parameter sweep (ทดสอบหลาย config พร้อมกัน):
    python run_node.py --sweep
"""

import sys
from pathlib import Path
from decimal import Decimal

# Nautilus High-Level imports
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    ImportableStrategyConfig,
    LoggingConfig,
)
from nautilus_trader.backtest.models import FillModel, MakerTakerFeeModel
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

CATALOG_PATH = Path(__file__).parent / "catalog"
VENUE_NAME   = "BINANCE"
SYMBOL       = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"
SWEEP_MODE   = "--sweep" in sys.argv


# ---------------------------------------------------------------------------
# สร้าง BacktestRunConfig 1 ชุด
# ---------------------------------------------------------------------------
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
    run_id: str = "default",
) -> BacktestRunConfig:
    """
    สร้าง BacktestRunConfig 1 ชุด
    ทุกอย่าง declarative — BacktestNode จัดการ run เอง
    """
    bar_type_str = f"{INSTRUMENT_ID_STR}-1-MINUTE-LAST-EXTERNAL"

    return BacktestRunConfig(
        # ---- Venue: จำลองสภาพแวดล้อม Exchange ----
        venues=[
            BacktestVenueConfig(
                name=VENUE_NAME,
                oms_type=OmsType.NETTING,           # Futures-style
                account_type=AccountType.MARGIN,
                base_currency="USDT",
                starting_balances=["10000 USDT"],
                # Commission: Binance VIP0
                fee_model=MakerTakerFeeModel(),
                # Slippage simulation
                fill_model=FillModel(
                    prob_fill_on_limit=0.2,
                    prob_slippage=slippage_prob,
                    random_seed=42,
                ),
            )
        ],

        # ---- Data: ดึงจาก catalog อัตโนมัติ ----
        data=[
            BacktestDataConfig(
                catalog_path=str(CATALOG_PATH),
                data_cls=Bar,
                instrument_id=InstrumentId.from_str(INSTRUMENT_ID_STR),
                bar_spec=bar_type_str,
            )
        ],

        # ---- Engine config ----
        engine=BacktestEngineConfig(
            logging=LoggingConfig(
                log_level="WARNING",     # เปลี่ยนเป็น INFO ถ้าอยากดู detail
            ),
        ),

        # ---- Strategy: อ้างอิง class path + config ----
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

        # run_id ใช้แยก result เวลา sweep
        run_id=run_id,
    )


# ---------------------------------------------------------------------------
# Parameter Sweep: ทดสอบหลาย config พร้อมกัน
# ---------------------------------------------------------------------------
def make_sweep_configs() -> list[BacktestRunConfig]:
    """
    ทดลอง parameter combinations ต่างๆ
    BacktestNode จะรันทุก config ใน list นี้
    """
    configs = []
    combos = [
        # (ema_fast, ema_medium, rvol_threshold, sl_pct, tp_pct, run_id)
        (9,  21, 1.5, 0.005, 0.010, "EMA9-21_RVOL1.5"),
        (9,  21, 2.0, 0.005, 0.010, "EMA9-21_RVOL2.0"),    # RVOL filter เข้มขึ้น
        (9,  21, 1.5, 0.003, 0.006, "EMA9-21_SL0.3"),       # SL/TP แคบลง
        (5,  13, 1.5, 0.005, 0.010, "EMA5-13_RVOL1.5"),     # EMA เร็วขึ้น
        (12, 26, 1.5, 0.005, 0.010, "EMA12-26_RVOL1.5"),    # EMA ช้าลง (MACD style)
    ]
    for ema_f, ema_m, rvol, sl, tp, rid in combos:
        configs.append(make_run_config(
            ema_fast=ema_f,
            ema_medium=ema_m,
            rvol_threshold=rvol,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            run_id=rid,
        ))
    return configs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    # ตรวจสอบ catalog
    if not CATALOG_PATH.exists():
        print("[ERROR] Catalog not found!")
        print("        Please run first: python setup_catalog.py")
        return

    # โหลด catalog
    catalog = ParquetDataCatalog(str(CATALOG_PATH))
    instruments = catalog.instruments()
    if not instruments:
        print("[ERROR] No instruments in catalog. Re-run setup_catalog.py")
        return

    print("=" * 60)
    mode = "SWEEP MODE" if SWEEP_MODE else "SINGLE RUN"
    print(f"  Nautilus BacktestNode — {mode}")
    print("=" * 60)
    print(f"  Catalog     : {CATALOG_PATH.resolve()}")
    print(f"  Instrument  : {instruments[0].id}")

    # สร้าง configs
    if SWEEP_MODE:
        configs = make_sweep_configs()
        print(f"  Configs     : {len(configs)} parameter combinations")
    else:
        configs = [make_run_config(run_id="single")]
        print("  Configs     : 1 (single run)")

    # สร้าง BacktestNode
    node = BacktestNode(configs=configs)

    # Run ทุก config
    print(f"\nRunning {len(configs)} backtest(s)...\n")
    results = node.run()

    # แสดง results
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)

    for i, result in enumerate(results):
        run_id = configs[i].run_id
        print(f"\n  [{i+1}] Run ID: {run_id}")
        print("-" * 40)
        try:
            # Account report
            for venue_result in result.backtest_engine.trader.generate_account_report(
                result.instance_id
            ):
                print(venue_result)
        except Exception:
            pass

        try:
            orders = result.backtest_engine.trader.generate_order_fills_report()
            positions = result.backtest_engine.trader.generate_positions_report()
            print(f"  Orders    : {len(orders)}")
            print(f"  Positions : {len(positions)}")

            # Win rate
            if "realized_pnl" in positions.columns and not positions.empty:
                import pandas as pd
                pnl = pd.to_numeric(
                    positions["realized_pnl"].astype(str).str.extract(r"([-\d.]+)")[0],
                    errors="coerce",
                ).dropna()
                wins = (pnl > 0).sum()
                total = len(pnl)
                profit_factor = (
                    pnl[pnl > 0].sum() / abs(pnl[pnl <= 0].sum())
                    if pnl[pnl <= 0].sum() != 0 else float("inf")
                )
                print(f"  Total PnL : {pnl.sum():.4f} USDT")
                print(f"  Win Rate  : {wins/total*100:.1f}% ({wins}/{total})")
                print(f"  Profit Factor: {profit_factor:.2f}")
        except Exception as e:
            print(f"  [stats error] {e}")

    print("\n[DONE] All backtests complete")


if __name__ == "__main__":
    run()
