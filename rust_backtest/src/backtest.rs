use polars::prelude::*;
use glob::glob;

// Import Nautilus for realistic backtest
use nautilus_backtest::engine::BacktestEngine;
use nautilus_backtest::config::BacktestEngineConfig;
use nautilus_core::nanos::UnixNanos;
use nautilus_model::{
    enums::{OmsType, AggressorSide, AccountType, BookType, AggregationSource, BarAggregation, PriceType},
    identifiers::{InstrumentId, Symbol, Venue, TradeId},
    instruments::{InstrumentAny, CryptoPerpetual},
    types::{Price, Quantity, Currency, Money},
    data::{QuoteTick, TradeTick, Bar, BarType, BarSpecification, Data},
};
use nautilus_execution::models::fee::{FeeModelAny, MakerTakerFeeModel};
use nautilus_execution::models::fill::FillModelAny;
use nautilus_trading::{
    examples::strategies::ema_cross::EmaCross,
};
use anyhow::Result;
use ahash::AHashMap;
use rust_decimal::Decimal;
use log::LevelFilter;
use std::str::FromStr;

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Offline Backtest ---");

    // 1. Configuration - Read from root .env
    dotenvy::from_filename("../.env").ok();

    let symbol_str = std::env::var("BACKTEST_SYMBOL").unwrap_or_else(|_| "SOLUSDT".to_string());
    println!("Running backtest for: {}", symbol_str);
    
    // Extract base/quote (assuming USDT for now)
    let base_currency = if symbol_str.ends_with("USDT") {
        &symbol_str[..symbol_str.len()-4]
    } else {
        "BTC"
    };
    println!("Base currency: {}, Quote: USDT", base_currency);
    
    // 2. Load Local Data (Parquet)
    let data_path = format!("data/{}/*.parquet", symbol_str);
    let mut files: Vec<_> = glob(&data_path)?.filter_map(Result::ok).collect();
    files.sort();
    
    if files.is_empty() {
        return Err(anyhow::anyhow!("No data found in {}. Please run 'cargo run --bin fetch_data' first.", data_path));
    }

    println!("Loading {} data files...", files.len());
    
    // 3. Setup a working strategy (using EmaCross example)
    let instrument_id = InstrumentId::new(
        Symbol::from(symbol_str.as_ref()),
        Venue::from("SIM")
    );
    
    let ema_strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("0.001"), // min trade size
        10, // fast ema period
        20, // slow ema period
    );
    
    let initial_cash = std::env::var("BACKTEST_INITIAL_CASH").unwrap_or_else(|_| "100000".to_string());
    let currency_str = std::env::var("BACKTEST_CURRENCY").unwrap_or_else(|_| "USDT".to_string());
    let initial_cash_f64: f64 = initial_cash.parse().unwrap_or(100000.0);
    
    // 4. Setup Nautilus backtest engine
    let mut config = BacktestEngineConfig::default();
    config.logging.stdout_level = LevelFilter::Info; // Enable info logging to stdout
    let mut engine = BacktestEngine::new(config)?;

    // Add Venue with 0.53.0 required 28 arguments
    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Netting, // Change to Netting for realistic one-way position management
        AccountType::Margin,
        BookType::L1_MBP, // Correct variant for 0.53.0
        vec![Money::new(initial_cash_f64, Currency::from(currency_str.as_str()))],
        None,

        None,
        AHashMap::new(),
        vec![],
        FillModelAny::default(),
        FeeModelAny::MakerTaker(MakerTakerFeeModel), // Use maker/taker fees from instrument
        None,
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
    )?;

    // Create a basic instrument with 0.53.0 required 25 arguments
    let instrument = CryptoPerpetual::new_checked(
        instrument_id.clone(),
        Symbol::from(symbol_str.as_str()),
        Currency::from(base_currency),
        Currency::from("USDT"),
        Currency::from("USDT"),
        false, 1, 3,
        Price::from("0.1"), 
        Quantity::from("0.001"),
        None, None, None, None, None, None, None, None, None, None,
        Some(Decimal::from_str("0.0002").unwrap()), // maker_fee 0.02%
        Some(Decimal::from_str("0.0004").unwrap()), // taker_fee 0.04%
        None,
        UnixNanos::default(), // ts_event
        UnixNanos::default(), // ts_init
    )?;

    engine.add_instrument(InstrumentAny::from(instrument))?;
    engine.add_strategy(ema_strategy)?;

    println!("Backtest setup completed successfully!");
    
    // 5. Load data and run backtest
    println!("Loading market data...");
    let mut total_events = 0;
    
    for file_path in files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?
            .collect()?;
        
        println!("Processing file with {} rows...", df.height());
        
        let timestamps = df.column("open_time")?.i64()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;
        
        for i in 0..df.height() {
            let ts_ms = timestamps.get(i).unwrap_or(0);
            let open = opens.get(i).unwrap_or(0.0);
            let high = highs.get(i).unwrap_or(0.0);
            let low = lows.get(i).unwrap_or(0.0);
            let close = closes.get(i).unwrap_or(0.0);
            let volume = volumes.get(i).unwrap_or(0.0);
            
            let prices = [open, high, low, close];
            let sub_step_ns = 15_000_000_000;

            for (idx, &price) in prices.iter().enumerate() {
                let ts_event = UnixNanos::from(((ts_ms * 1_000_000) + (idx as i64 * sub_step_ns)) as u64);
                
                let spread = price * 0.0001; 
                let bid_str = format!("{:.1}", price - spread / 2.0);
                let ask_str = format!("{:.1}", price + spread / 2.0);
                let price_str = format!("{:.1}", price);
                let size_str = format!("{:.3}", volume / 8.0);
                
                let quote = QuoteTick::new(
                    instrument_id.clone(),
                    Price::from(bid_str), 
                    Price::from(ask_str),
                    Quantity::from(size_str.clone()),
                    Quantity::from(size_str),
                    ts_event,
                    ts_event,
                );
                engine.add_data(vec![Data::from(quote)], None, false, false);

                let trade = TradeTick::new(
                    instrument_id.clone(),
                    Price::from(price_str),
                    Quantity::from(format!("{:.3}", volume / 4.0)),
                    if idx == 1 { AggressorSide::Buyer } else { AggressorSide::Seller },
                    TradeId::new("1"), // Fixed instantiation
                    ts_event,
                    ts_event,
                );
                engine.add_data(vec![Data::from(trade)], None, false, false);
                total_events += 2;
            }

            // Add Bar data (required for EmaCross strategy)
            // A bar ending at T should have a timestamp of T + 60s
            let bar_ts = UnixNanos::from(((ts_ms + 60_000) * 1_000_000) as u64);
            let bar_type = BarType::new(
                instrument_id.clone(),
                BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
                AggregationSource::External,
            );
            let bar = Bar::new(
                bar_type,
                Price::from(format!("{:.1}", open)),
                Price::from(format!("{:.1}", high)),
                Price::from(format!("{:.1}", low)),
                Price::from(format!("{:.1}", close)),
                Quantity::from(format!("{:.3}", volume)),
                bar_ts, // ts_event
                bar_ts, // ts_init
            );
            engine.add_data(vec![Data::from(bar)], None, false, false);
            total_events += 1;
        }
    }
    
    println!("Loaded {} market events.", total_events);
    
    println!("Running backtest engine...");
    engine.run(None, None, None, false)?;
    println!("Backtest execution finished.");
    
    // 6. Report results
    // 6. Report results
    let result = engine.get_result();
    println!("Backtest Result Summary:");
    println!("Total Events: {}", result.total_events);
    println!("Total Orders: {}", result.total_orders);
    println!("Total Positions: {}", result.total_positions);
    
    for (trader_id, pnls) in &result.stats_pnls {
        println!("Trader: {}", trader_id);
        for (venue, pnl) in pnls {
            println!("  Venue: {}, PnL: {}", venue, pnl);
        }
    }
    
    println!("Backtest completed successfully!");
    
    Ok(())
}
