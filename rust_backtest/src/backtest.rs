use anyhow::Result;
use log::LevelFilter;
use std::str::FromStr;

use nautilus_backtest::engine::BacktestEngine;
use nautilus_backtest::config::BacktestEngineConfig;
use nautilus_common::logging::config::LoggerConfig;
use nautilus_core::nanos::UnixNanos;
use nautilus_model::{
    enums::{
        OmsType, AccountType, BookType,
        AggregationSource, BarAggregation, PriceType, AggressorSide,
    },
    identifiers::{InstrumentId, Symbol, Venue, TraderId, TradeId},
    instruments::{InstrumentAny, CryptoPerpetual},
    types::{Price, Quantity, Currency, Money},
    data::{
        Data, Bar, QuoteTick, TradeTick,
        BarType, BarSpecification,
    },
};
use nautilus_execution::models::{
    fee::{FeeModelAny, MakerTakerFeeModel},
    fill::FillModelAny,
    latency::StaticLatencyModel,
};
use nautilus_trading::examples::strategies::ema_cross::EmaCross;
use ahash::AHashMap;
use rust_decimal::Decimal;
use polars::prelude::*;
use glob::glob;

/// VORTEX-7 Professional Backtest — NautilusTrader 0.53.0 (Rust Native)
///
/// This backtest follows the correct Nautilus 0.53.0 Rust API:
/// 1. BacktestEngineConfig with LoggerConfig (not env_logger)
/// 2. StaticLatencyModel (replaces ConstantLatencyModel)
/// 3. Correct add_venue() parameter ordering
/// 4. OHLC → QuoteTick + TradeTick + Bar synthesis for high-fidelity simulation
/// 5. Engine manages all event ordering and execution internally
fn main() -> Result<()> {
    // ─── 0. Environment Setup ───────────────────────────────────────────
    dotenvy::from_filename("../.env").ok();

    // ─── 1. Configuration from .env ─────────────────────────────────────
    let symbol_str = std::env::var("BACKTEST_SYMBOL")
        .unwrap_or_else(|_| "SOLUSDT".to_string());
    let initial_cash: f64 = std::env::var("BACKTEST_INITIAL_CASH")
        .unwrap_or_else(|_| "100000".to_string())
        .parse()
        .unwrap_or(100000.0);
    let latency_ms: u64 = std::env::var("BACKTEST_LATENCY_MS")
        .unwrap_or_else(|_| "30".to_string())
        .parse()
        .unwrap_or(30);
    let spread_bps: f64 = std::env::var("BACKTEST_SPREAD_BPS")
        .unwrap_or_else(|_| "1.0".to_string())
        .parse()
        .unwrap_or(1.0);

    // ─── 2. Build BacktestEngine ────────────────────────────────────────
    //    Use Nautilus's own LoggerConfig instead of env_logger
    let logging = LoggerConfig {
        stdout_level: LevelFilter::Info,
        is_colored: true,
        ..LoggerConfig::default()
    };

    let config = BacktestEngineConfig {
        trader_id: TraderId::from("BACKTESTER-001"),
        logging,
        ..BacktestEngineConfig::default()
    };

    let mut engine = BacktestEngine::new(config)?;

    // ─── 3. Instrument & Venue Setup ────────────────────────────────────
    let venue = Venue::from("SIM");
    let instrument_id = InstrumentId::new(
        Symbol::from(symbol_str.as_str()),
        venue,
    );

    // Create StaticLatencyModel (30ms base latency = 30_000_000 nanos)
    let latency_nanos = UnixNanos::from(latency_ms * 1_000_000);
    let latency_model = StaticLatencyModel::new(
        latency_nanos,              // base_latency_nanos
        UnixNanos::from(0u64),      // insert_latency_nanos
        UnixNanos::from(0u64),      // update_latency_nanos
        UnixNanos::from(0u64),      // delete_latency_nanos
    );

    // Add venue with correct API parameter order for 0.53.0
    engine.add_venue(
        venue,
        OmsType::Netting,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::new(initial_cash, Currency::from("USDT"))],
        None,                                           // base_currency
        None,                                           // default_leverage
        AHashMap::new(),                                // leverages
        vec![],                                         // modules
        FillModelAny::default(),                              // fill_model
        FeeModelAny::MakerTaker(MakerTakerFeeModel),   // fee_model
        Some(Box::new(latency_model)),                  // latency_model
        None,                                           // routing
        None,                                           // reject_stop_orders
        None,                                           // support_gtd_orders
        None,                                           // support_contingent_orders
        None,                                           // use_position_ids
        None,                                           // use_random_ids
        None,                                           // use_reduce_only
        None,                                           // use_message_queue
        None,                                           // use_market_order_acks
        None,                                           // bar_execution
        None,                                           // bar_adaptive_high_low_ordering
        None,                                           // trade_execution
        None,                                           // liquidity_consumption
        None,                                           // allow_cash_borrowing
        None,                                           // frozen_account
        None,                                           // price_protection_points
    )?;

    // Create CryptoPerpetual Instrument
    let instrument = CryptoPerpetual::new_checked(
        instrument_id,
        Symbol::from(symbol_str.as_str()),
        Currency::from("SOL"),   // base_currency
        Currency::from("USDT"),  // quote_currency
        Currency::from("USDT"),  // settlement_currency
        false,                   // is_inverse
        1,                       // price_precision
        3,                       // size_precision
        Price::from("0.1"),      // price_increment
        Quantity::from("0.001"), // size_increment
        None, None, None, None, None, None, None, None, None, None,
        Some(Decimal::from_str("0.0002").unwrap()),  // maker_fee
        Some(Decimal::from_str("0.0004").unwrap()),  // taker_fee
        None,                                         // margin_init
        UnixNanos::default(),                         // ts_event
        UnixNanos::default(),                         // ts_init
    )?;
    engine.add_instrument(InstrumentAny::from(instrument))?;

    // ─── 4. Strategy Setup ──────────────────────────────────────────────
    //    EmaCross: built-in example strategy from Nautilus
    let strategy = EmaCross::new(
        instrument_id,
        Quantity::from("0.001"),
        10,  // fast EMA period
        20,  // slow EMA period
    );
    engine.add_strategy(strategy)?;

    // ─── 5. Data Loading ────────────────────────────────────────────────
    //    Load OHLCV from Parquet → synthesize QuoteTicks + TradeTicks + Bars
    //    Nautilus engine handles event ordering internally
    println!("Loading historical data from Parquet files...");

    // Try multiple paths: cargo run executes from workspace root
    let candidate_paths = [
        format!("rust_backtest/data/{}/*.parquet", symbol_str),  // from workspace root
        format!("data/{}/*.parquet", symbol_str),                // from rust_backtest/
    ];
    let mut files: Vec<_> = Vec::new();
    let mut used_path = String::new();
    for path in &candidate_paths {
        files = glob(path)?.filter_map(Result::ok).collect();
        if !files.is_empty() {
            used_path = path.clone();
            break;
        }
    }
    files.sort();

    if files.is_empty() {
        return Err(anyhow::anyhow!(
            "No Parquet data found for {}. Tried paths: {:?}",
            symbol_str, candidate_paths
        ));
    }
    println!("  Found data via pattern: {}", used_path);

    let mut total_events: i64 = 0;
    for file_path in &files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?.collect()?;
        println!(
            "  Processing {:?} ({} rows)...",
            file_path.file_name().unwrap_or_default(),
            df.height()
        );

        let timestamps = df.column("open_time")?.i64()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;

        // Pre-allocate: 4 quote ticks + 4 trade ticks + 1 bar per candle = 9 events
        let mut events = Vec::with_capacity(df.height() * 9);

        for i in 0..df.height() {
            let ts_ms = timestamps.get(i).unwrap_or(0);
            let o = opens.get(i).unwrap_or(0.0);
            let h = highs.get(i).unwrap_or(0.0);
            let l = lows.get(i).unwrap_or(0.0);
            let c = closes.get(i).unwrap_or(0.0);
            let v = volumes.get(i).unwrap_or(0.0);

            // Skip candles with zero volume or zero price (Nautilus requires positive Quantity)
            if v <= 0.0 || o <= 0.0 || h <= 0.0 || l <= 0.0 || c <= 0.0 {
                continue;
            }

            let ts_start_ns = ts_ms * 1_000_000; // ms → ns

            // Synthesize high-fidelity tick path from OHLC:
            //   Bullish candle: O → L → H → C
            //   Bearish candle: O → H → L → C
            let path = if c >= o {
                [o, l, h, c]
            } else {
                [o, h, l, c]
            };

            let dist = spread_bps / 10000.0 / 2.0; // half-spread as fraction

            for (idx, &price) in path.iter().enumerate() {
                let ts_event = UnixNanos::from(
                    (ts_start_ns + (idx as i64 * 15_000_000_000)) as u64,
                );
                let bid = price * (1.0 - dist);
                let ask = price * (1.0 + dist);

                // QuoteTick → feeds into L1 order book for execution
                events.push(Data::from(QuoteTick::new(
                    instrument_id,
                    Price::from(&format!("{:.8}", bid)),
                    Price::from(&format!("{:.8}", ask)),
                    Quantity::from(&format!("{:.8}", v / 8.0)),
                    Quantity::from(&format!("{:.8}", v / 8.0)),
                    ts_event,
                    ts_event,
                )));

                // TradeTick → provides last-trade price for indicators
                events.push(Data::from(TradeTick::new(
                    instrument_id,
                    Price::from(&format!("{:.8}", price)),
                    Quantity::from(&format!("{:.8}", v / 4.0)),
                    if idx % 2 == 0 {
                        AggressorSide::Buyer
                    } else {
                        AggressorSide::Seller
                    },
                    TradeId::new(&(total_events + events.len() as i64).to_string()),
                    ts_event,
                    ts_event,
                )));
            }

            // Bar → for strategy bar subscriptions
            let bar_ts = UnixNanos::from((ts_start_ns + 60_000_000_000) as u64);
            events.push(Data::from(Bar::new(
                BarType::new(
                    instrument_id,
                    BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
                    AggregationSource::External,
                ),
                Price::from(&format!("{:.8}", o)),
                Price::from(&format!("{:.8}", h)),
                Price::from(&format!("{:.8}", l)),
                Price::from(&format!("{:.8}", c)),
                Quantity::from(&format!("{:.8}", v)),
                bar_ts,
                bar_ts,
            )));
        }

        // Let Nautilus handle data sorting (sort=true)
        engine.add_data(events, None, false, true);
        total_events += df.height() as i64;
    }

    println!(
        "Loaded {} files, ~{} total candles → ~{} synthetic events",
        files.len(),
        total_events,
        total_events * 9,
    );

    // ─── 6. Run Backtest ────────────────────────────────────────────────
    //    Nautilus manages everything: event replay, order matching, fills
    println!("\nStarting NautilusTrader Backtest Engine...");
    engine.run(None, None, None, false)?;
    println!("Backtest execution complete.");

    // ─── 7. Results ─────────────────────────────────────────────────────
    let result = engine.get_result();
    println!("\n╔══════════════════════════════════════════════╗");
    println!("║    NAUTILUS BACKTEST RESULTS SUMMARY          ║");
    println!("╠══════════════════════════════════════════════╣");
    println!("║ Instrument:      {:<28}║", symbol_str);
    println!("║ Total Events:    {:<28}║", result.total_events);
    println!("║ Total Orders:    {:<28}║", result.total_orders);
    println!("║ Total Positions: {:<28}║", result.total_positions);
    println!("╠══════════════════════════════════════════════╣");

    for (trader_id, pnls) in &result.stats_pnls {
        println!("║ Trader: {:<37}║", trader_id);
        for (venue_id, pnl) in pnls {
            println!("║   {} PnL: {:<30.4}║", venue_id, pnl);
        }
    }
    println!("╚══════════════════════════════════════════════╝");

    // ─── 8. Cleanup ─────────────────────────────────────────────────────
    engine.dispose();

    Ok(())
}
