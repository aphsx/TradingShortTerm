use polars::prelude::*;
use glob::glob;

// Import Nautilus for realistic backtest
use nautilus_backtest::{engine::BacktestEngine, config::BacktestEngineConfig};
use nautilus_model::{
    enums::{OmsType, AggressorSide},
    identifiers::{InstrumentId, Symbol, Venue},
    instruments::{InstrumentAny, CryptoPerpetual},
    types::{Price, Quantity, UnixNanos},
    events::{QuoteTick, TradeTick},
};
use nautilus_trading::{
    examples::strategies::ema_cross::EmaCross,
};
use anyhow::Result;
use ahash::AHashMap;
use chrono::{DateTime, Utc};

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Offline Backtest ---");

    // 1. Configuration - Read from root .env
    dotenvy::from_filename("../.env").ok();

    let symbol_str = std::env::var("BACKTEST_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_string());
    println!("Running backtest for: {}", symbol_str);
    
    // Also use the same interval and limit settings as MFT ENGINE
    let _kline_interval = std::env::var("KLINE_INTERVAL").unwrap_or_else(|_| "1m".to_string());
    let _backtest_limit = std::env::var("BACKTEST_LIMIT").unwrap_or_else(|_| "43200".to_string());

    // 2. Load Local Data (Parquet)
    let data_path = format!("data/{}/*.parquet", symbol_str);
    let mut files: Vec<_> = glob(&data_path)?.filter_map(Result::ok).collect();
    files.sort();
    
    if files.is_empty() {
        return Err(anyhow::anyhow!("No data found in {}. Please run 'cargo run --bin fetch_data' first.", data_path));
    }

    println!("Loading {} data files...", files.len());
    
    // Load and count data
    let mut total_rows = 0;
    for file_path in &files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?
            .collect()?;
        total_rows += df.height();
    }

    println!("Loaded {} klines.", total_rows);

    // 3. Setup a working strategy (using EmaCross example)
    let instrument_id = InstrumentId::new(
        Symbol::from(symbol_str.as_ref()),
        Venue::from("SIM")
    );
    
    let mut ema_strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("0.001"), // min trade size
        10, // fast ema period
        20, // slow ema period
    );
    
    // 4. Setup Nautilus backtest engine
    let config = BacktestEngineConfig::default();
    let mut engine = BacktestEngine::new(config)?;

    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Hedging,
        AHashMap::new(),
        AHashMap::new(),
        None,
        vec![],
    )?;

    // Create a basic instrument (simplified approach)
    let instrument = CryptoPerpetual::new_checked(
        instrument_id.clone(),
        Symbol::from(symbol_str.as_str()),
        "BTC".into(), // base currency as string
        "USDT".into(), // quote currency as string
        Price::from("0.01"),
        Quantity::from("0.001"),
        false, // is_inverse
        None, // lot_size
        None, // max_quantity
        None, // min_quantity
        None, // max_price
        None, // min_price
        UnixNanos::default(), // ts_event
        UnixNanos::default(), // ts_init
    )?;

    engine.add_instrument(InstrumentAny::from(instrument))?;
    engine.add_strategy(ema_strategy)?;

    println!("Backtest setup completed successfully!");
    println!("Note: Using EmaCross strategy as example. You can replace with your custom strategy.");
    
    // 5. Load data and run backtest
    println!("Loading market data...");
    let mut total_events = 0;
    
    for file_path in files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?
            .collect()?;
        
        println!("Processing file with {} rows...", df.height());
        
        // Convert DataFrame to Nautilus events
        let timestamps = df.column("open_time")?.i64()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;
        
        for i in 0..df.height() {
            let ts = timestamps.get(i).unwrap_or(0);
            let open = opens.get(i).unwrap_or(0.0);
            let high = highs.get(i).unwrap_or(0.0);
            let low = lows.get(i).unwrap_or(0.0);
            let close = closes.get(i).unwrap_or(0.0);
            let volume = volumes.get(i).unwrap_or(0.0);
            
            // Create QuoteTick from OHLC data
            let bid = Price::from(low);
            let ask = Price::from(high);
            let bid_size = Quantity::from(volume / 2.0); // Split volume
            let ask_size = Quantity::from(volume / 2.0);
            let ts_event = UnixNanos::from(ts * 1_000_000); // Convert ms to ns
            let ts_init = ts_event;
            
            let quote_tick = QuoteTick::new(
                instrument_id.clone(),
                bid,
                ask,
                bid_size,
                ask_size,
                ts_event,
                ts_init,
            )?;
            
            engine.add_quote_tick(quote_tick)?;
            
            // Create TradeTick for close price
            let trade_price = Price::from(close);
            let trade_size = Quantity::from(volume);
            let aggressor_side = if close > open { AggressorSide::Buyer } else { AggressorSide::Seller };
            
            let trade_tick = TradeTick::new(
                instrument_id.clone(),
                trade_price,
                trade_size,
                aggressor_side,
                ts_event,
                ts_init,
            )?;
            
            engine.add_trade_tick(trade_tick)?;
            total_events += 2;
        }
    }
    
    println!("Loaded {} market events.", total_events);
    
    println!("Running backtest...");
    let result = engine.run(None, None, None, false)?;
    println!("Backtest completed successfully!");
    
    Ok(())
}
