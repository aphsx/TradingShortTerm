use anyhow::Result;
use dotenvy::dotenv;
use log::{info, LevelFilter};
use std::path::PathBuf;
use std::str::FromStr;

use nautilus_backtest::engine::BacktestEngine;
use nautilus_backtest::config::BacktestEngineConfig;
use nautilus_core::nanos::UnixNanos;
use nautilus_model::{
    enums::{OmsType, AccountType, BookType},
    identifiers::{InstrumentId, Symbol, Venue},
    instruments::{InstrumentAny, CryptoPerpetual},
    types::{Price, Quantity, Currency, Money},
    data::{Data, Bar, QuoteTick, TradeTick, BarType, BarSpecification, AggregationSource, BarAggregation, PriceType, AggressorSide, TradeId},
};
use nautilus_execution::models::{
    fee::{FeeModelAny, MakerTakerFeeModel},
    fill::{FillModelAny, StandardFillModel},
};
use nautilus_core::models::latency::ConstantLatencyModel;
use nautilus_trading::examples::strategies::ema_cross::EmaCross;
use ahash::AHashMap;
use rust_decimal::Decimal;
use polars::prelude::*;
use glob::glob;

/// The "Professional" Nautilus Backtest Orchestrator
/// 
/// This script follows the Nautilus 0.53.0 standards:
/// 1. Uses centralized configuration via .env
/// 2. Implements high-fidelity data ingestion (OHLC -> Ticks)
/// 3. Leverages Nautilus's internal matching engine and execution models
/// 4. Organizes execution in a "Library-native" way
#[tokio::main]
async fn main() -> Result<()> {
    // 0. Environment Setup
    dotenvy::from_filename("../.env").ok();
    env_logger::builder().filter_level(LevelFilter::Info).init();
    
    info!("--- VORTEX-7 Professional Backtest (Nautilus Native) ---");

    // 1. configuration
    let symbol_str = std::env::var("BACKTEST_SYMBOL").unwrap_or_else(|_| "SOLUSDT".to_string());
    let initial_cash = std::env::var("BACKTEST_INITIAL_CASH").unwrap_or_else(|_| "100000".to_string()).parse::<f64>().unwrap_or(100000.0);
    let latency_ms = std::env::var("BACKTEST_LATENCY_MS").unwrap_or_else(|_| "30".to_string()).parse::<u64>().unwrap_or(30);
    let spread_bps = std::env::var("BACKTEST_SPREAD_BPS").unwrap_or_else(|_| "1.0".to_string()).parse::<f64>().unwrap_or(1.0);
    
    info!("Symbol: {}, Initial Cash: {}, Latency: {}ms", symbol_str, initial_cash, latency_ms);

    // 2. Instrument & Venue Setup
    let instrument_id = InstrumentId::new(Symbol::from(symbol_str.as_str()), Venue::from("SIM"));
    
    let mut config = BacktestEngineConfig::default();
    config.logging.stdout_level = LevelFilter::Info;
    let mut engine = BacktestEngine::new(config)?;

    // Add Venue with Realistic Network Latency & Default Matching
    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Netting,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::new(initial_cash, Currency::from("USDT"))],
        None,
        Some(Box::new(ConstantLatencyModel::new(latency_ms * 1_000_000))),
        AHashMap::new(),
        vec![],
        FillModelAny::Standard(StandardFillModel::default()),
        FeeModelAny::MakerTaker(MakerTakerFeeModel),
        None,
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
    )?;

    // Create Crypto Perpetual Instrument
    let instrument = CryptoPerpetual::new_checked(
        instrument_id.clone(),
        Symbol::from(symbol_str.as_str()),
        Currency::from("SOL"), // Simplified base
        Currency::from("USDT"),
        Currency::from("USDT"),
        false, 1, 3,
        Price::from("0.1"), 
        Quantity::from("0.001"),
        None, None, None, None, None, None, None, None, None, None,
        Some(Decimal::from_str("0.0002").unwrap()), 
        Some(Decimal::from_str("0.0004").unwrap()), 
        None,
        UnixNanos::default(),
        UnixNanos::default(),
    )?;
    engine.add_instrument(InstrumentAny::from(instrument))?;

    // 3. Strategy Setup
    let strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("0.001"),
        10,
        20,
    );
    engine.add_strategy(strategy)?;

    // 4. Data Loading & Ingestion
    // We let the engine manage the data once we've converted it to Data objects
    info!("Loading historical data files from Parquet...");
    let data_path = format!("data/{}/*.parquet", symbol_str);
    let mut files: Vec<_> = glob(&data_path)?.filter_map(Result::ok).collect();
    files.sort();

    if files.is_empty() {
        return Err(anyhow::anyhow!("No data found for {}", symbol_str));
    }

    let mut total_events = 0;
    for file_path in files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?.collect()?;
        info!("Processing {} ({} rows)...", symbol_str, df.height());

        let timestamps = df.column("open_time")?.i64()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;

        let mut events = Vec::with_capacity(df.height() * 9);
        
        for i in 0..df.height() {
            let ts_ms = timestamps.get(i).unwrap_or(0);
            let o = opens.get(i).unwrap_or(0.0);
            let h = highs.get(i).unwrap_or(0.0);
            let l = lows.get(i).unwrap_or(0.0);
            let c = closes.get(i).unwrap_or(0.0);
            let v = volumes.get(i).unwrap_or(0.0);

            // Time step setup
            let ts_start_ns = ts_ms * 1_000_000;
            
            // Generate High-Fidelity Ticks (O -> H/L -> C)
            let path = if c >= o { [o, l, h, c] } else { [o, h, l, c] };
            for (idx, &price) in path.iter().enumerate() {
                let ts_event = UnixNanos::from((ts_start_ns + (idx as i64 * 15_000_000_000)) as u64);
                let dist = price * (spread_bps / 10000.0) / 2.0;

                events.push(Data::from(QuoteTick::new(
                    instrument_id.clone(),
                    Price::from(price - dist),
                    Price::from(price + dist),
                    Quantity::from(v / 8.0),
                    Quantity::from(v / 8.0),
                    ts_event,
                    ts_event,
                )));

                events.push(Data::from(TradeTick::new(
                    instrument_id.clone(),
                    Price::from(price),
                    Quantity::from(v / 4.0),
                    if idx % 2 == 0 { AggressorSide::Buyer } else { AggressorSide::Seller },
                    TradeId::new(&(total_events + events.len() as i64).to_string()),
                    ts_event,
                    ts_event,
                )));
            }

            // Create Bar
            let bar_ts = UnixNanos::from((ts_start_ns + 60_000_000_000) as u64);
            events.push(Data::from(Bar::new(
                BarType::new(instrument_id.clone(), BarSpecification::new(1, BarAggregation::Minute, PriceType::Last), AggregationSource::External),
                Price::from(o), Price::from(h), Price::from(l), Price::from(c),
                Quantity::from(v),
                bar_ts, bar_ts,
            )));
        }

        engine.add_data(events, None, false, false);
        total_events += df.height() as i64;
    }

    // 5. Execution
    info!("Starting Nautilus Backtest Engine...");
    engine.run(None, None, None, false)?;
    info!("Backtest execution complete.");

    // 6. Results
    let result = engine.get_result();
    println!("\n============================================");
    println!("     NAUTILUS BACKTEST RESULTS SUMMARY");
    println!("============================================");
    println!("Instrument:       {}", symbol_str);
    println!("Total Events:     {}", result.total_events);
    println!("Total Orders:     {}", result.total_orders);
    println!("Total Positions:  {}", result.total_positions);
    
    for (trader_id, pnls) in &result.stats_pnls {
        println!("Trader:           {}", trader_id);
        for (venue, pnl) in pnls {
            println!("  Venue [{}]: PnL = {:.4}", venue, pnl);
        }
    }
    println!("============================================\n");

    Ok(())
}
