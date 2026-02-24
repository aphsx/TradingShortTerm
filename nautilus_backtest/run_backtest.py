"""
run_backtest.py — Nautilus Trader Backtest Runner
==================================================

วิธีใช้:
    python run_backtest.py

ปรับพารามิเตอร์ได้ใน MFTConfig ด้านล่าง
"""

from pathlib import Path
from decimal import Decimal

import pandas as pd

# Nautilus imports
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FeeModel, MakerTakerFeeModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.model.data import BarType, Bar, BarSpecification
from nautilus_trader.model.enums import (
    AccountType,
    AggregationSource,
    BarAggregation,
    OmsType,
    PriceType,
)
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity

from strategies.mft_strategy import MFTConfig, MFTStrategy
from data_loader import load_parquet_as_bars_df


# ---------------------------------------------------------------------------
# Config — ปรับที่นี่
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).parent.parent / "data" / "BTCUSDT" / "BTCUSDT_20260223_145530.parquet"

VENUE_NAME = "BINANCE"
SYMBOL = "BTCUSDT-PERP"
INSTRUMENT_ID_STR = f"{SYMBOL}.{VENUE_NAME}"

INITIAL_BALANCE_USDT = 10_000.0

STRATEGY_CONFIG = MFTConfig(
    instrument_id=INSTRUMENT_ID_STR,
    bar_type=f"{INSTRUMENT_ID_STR}-1-MINUTE-LAST-EXTERNAL",
    # ปรับ EMA
    ema_fast=9,
    ema_medium=21,
    ema_slow=200,
    # ปรับ RSI
    rsi_period=14,
    rsi_long_min=50.0,
    rsi_long_max=65.0,
    rsi_short_min=35.0,
    rsi_short_max=50.0,
    # ปรับ Volume
    rvol_period=20,
    rvol_threshold=1.5,
    # ปรับ Risk
    trade_size=0.001,
    stop_loss_pct=0.005,
    take_profit_pct=0.010,
    warmup_bars=210,
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_instrument(venue: Venue) -> CryptoPerpetual:
    """สร้าง CryptoPerpetual instrument สำหรับ Nautilus"""
    return CryptoPerpetual(
        instrument_id=InstrumentId(Symbol(SYMBOL), venue),
        raw_symbol=Symbol(SYMBOL),
        base_currency=BTC,
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=2,
        size_precision=3,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.001"),
        max_quantity=Quantity.from_str("100.0"),
        min_quantity=Quantity.from_str("0.001"),
        max_notional=None,
        min_notional=Money(10, USDT),
        max_price=Price.from_str("10000000.0"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0.05"),
        margin_maint=Decimal("0.025"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0004"),
        ts_event=0,
        ts_init=0,
    )


def df_to_nautilus_bars(df: pd.DataFrame, bar_type: BarType, instrument: CryptoPerpetual) -> list[Bar]:
    """แปลง DataFrame → list of Nautilus Bar objects"""
    bars = []
    for ts, row in df.iterrows():
        ts_ns = int(pd.Timestamp(ts).value)  # nanoseconds
        bar = Bar(
            bar_type=bar_type,
            open=Price(float(row["open"]), precision=instrument.price_precision),
            high=Price(float(row["high"]), precision=instrument.price_precision),
            low=Price(float(row["low"]), precision=instrument.price_precision),
            close=Price(float(row["close"]), precision=instrument.price_precision),
            volume=Quantity(float(row["volume"]), precision=instrument.size_precision),
            ts_event=ts_ns,
            ts_init=ts_ns,
        )
        bars.append(bar)
    return bars


def run():
    print("=" * 60)
    print("  MFT Strategy — Nautilus Backtest")
    print("=" * 60)

    # 1. Load data
    print(f"\n[1] Loading data from: {DATA_PATH}")
    df = load_parquet_as_bars_df(DATA_PATH)

    # 2. Setup engine
    print("\n[2] Setting up backtest engine...")
    engine_config = BacktestEngineConfig(
        logging=LoggingConfig(log_level="INFO"),
    )
    engine = BacktestEngine(config=engine_config)

    # 3. Add venue
    venue = Venue(VENUE_NAME)
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(INITIAL_BALANCE_USDT, USDT)],
        fee_model=MakerTakerFeeModel(),
    )

    # 4. Add instrument
    instrument = build_instrument(venue)
    engine.add_instrument(instrument)

    # 5. Add bar data
    print(f"\n[3] Converting {len(df)} rows to Bar objects...")
    bar_type = BarType.from_str(STRATEGY_CONFIG.bar_type)
    bars = df_to_nautilus_bars(df, bar_type, instrument)
    engine.add_data(bars)
    print(f"    [OK] {len(bars)} bars added")

    # 6. Add strategy
    print("\n[4] Adding strategy...")
    strategy = MFTStrategy(config=STRATEGY_CONFIG)
    engine.add_strategy(strategy=strategy)

    # 7. Run!
    print("\n[5] Running backtest...")
    engine.run()

    # 8. Results
    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    try:
        stats = engine.trader.generate_account_report(venue)
        print(stats.to_string())
    except Exception:
        pass

    try:
        orders = engine.trader.generate_order_fills_report()
        print(f"\nTotal order fills: {len(orders)}")
        if not orders.empty:
            print(orders.tail(20).to_string())
    except Exception:
        pass

    try:
        positions = engine.trader.generate_positions_report()
        print(f"\nTotal positions: {len(positions)}")
        if not positions.empty:
            print(positions.tail(20).to_string())
    except Exception:
        pass

    engine.dispose()
    print("\n[DONE] Backtest complete")


if __name__ == "__main__":
    run()
