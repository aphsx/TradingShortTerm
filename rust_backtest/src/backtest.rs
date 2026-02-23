use polars::prelude::*;
use glob::glob;

// Import Nautilus for realistic backtest
use nautilus_backtest::engine::BacktestEngine;
use nautilus_backtest::config::BacktestEngineConfig;
use nautilus_core::nanos::UnixNanos;
use nautilus_model::{
    enums::{OmsType, AggressorSide, AccountType, BookType},
    identifiers::{InstrumentId, Symbol, Venue, TradeId},
    instruments::{InstrumentAny, CryptoPerpetual},
    types::{Price, Quantity, Currency},
    data::{QuoteTick, TradeTick, Data},
};
use nautilus_execution::models::fee::FeeModelAny;
use nautilus_execution::models::fill::FillModelAny;
use nautilus_trading::{
    examples::strategies::ema_cross::EmaCross,
};
use anyhow::Result;
use ahash::AHashMap;

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Offline Backtest ---");

    // 1. Configuration - Read from root .env
    dotenvy::from_filename("../.env").ok();

    let symbol_str = std::env::var("BACKTEST_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_string());
    println!("Running backtest for: {}", symbol_str);
    
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
    
    // 4. Setup Nautilus backtest engine
    let config = BacktestEngineConfig::default();
    let mut engine = BacktestEngine::new(config)?;

    // Add Venue with 0.53.0 required 28 arguments
    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Hedging,
        AccountType::Cash,
        BookType::L1_MBP, // Correct variant for 0.53.0
        vec![],
        None,
        None,
        AHashMap::new(),
        vec![],
        FillModelAny::default(),
        FeeModelAny::default(),
        None,
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
    )?;

    // Create a basic instrument with 0.53.0 required 25 arguments
    let instrument = CryptoPerpetual::new_checked(
        instrument_id.clone(),
        Symbol::from(symbol_str.as_str()),
        Currency::from("BTC"),
        Currency::from("USDT"),
        Currency::from("USDT"),
        false, 8, 8,
        Price::from("0.1"), 
        Quantity::from("0.001"),
        None, None, None, None, None, None, None, None, None, None, None, None, None,
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
                let bid_str = format!("{:.8}", price - spread / 2.0);
                let ask_str = format!("{:.8}", price + spread / 2.0);
                let price_str = format!("{:.8}", price);
                let size_str = format!("{:.8}", volume / 8.0);
                
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
                    Quantity::from(format!("{:.8}", volume / 4.0)),
                    if idx == 1 { AggressorSide::Buyer } else { AggressorSide::Seller },
                    TradeId::new("1"), // Fixed instantiation
                    ts_event,
                    ts_event,
                );
                engine.add_data(vec![Data::from(trade)], None, false, false);
                total_events += 2;
            }
        }
    }
    
    println!("Loaded {} market events.", total_events);
    
    println!("Running backtest...");
    engine.run(None, None, None, false)?;
    println!("Backtest completed successfully!");
    
    Ok(())
}
