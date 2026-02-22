use ahash::AHashMap;
use anyhow::Result;
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    data::{Data, QuoteTick},
    enums::{AccountType, BookType, OmsType},
    identifiers::{InstrumentId, Symbol, Venue},
    instruments::{Instrument, InstrumentAny, CurrencyPair},
    types::{Money, Price, Quantity},
};
use nautilus_trading::examples::strategies::EmaCross;
use polars::prelude::*;
use std::path::Path;
use glob::glob;

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Offline Backtest ---");

    // 1. Configuration - Read from .env if possible, or use defaults
    let env_path = Path::new("..").join("mft_engine").join(".env");
    dotenvy::from_path(env_path).ok();

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
    
    let mut all_quotes = Vec::new();
    let instrument_id = InstrumentId::new(
        Symbol::from(symbol_str.as_ref()),
        Venue::from("SIM")
    );

    for file_path in files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?
            .collect()?;
        
        let prices = df.column("price")?.f64()?;
        let qtys = df.column("qty")?.f64()?;
        let times = df.column("time")?.i64()?;

        for i in 0..df.height() {
            let p = prices.get(i).unwrap_or(0.0);
            let q = qtys.get(i).unwrap_or(0.0);
            let t = times.get(i).unwrap_or(0);

            // Nautilus expects Nanoseconds
            let ts_ns = (t as u64) * 1_000_000;
            
            let price = Price::from(&format!("{:.5}", p));
            let qty = Quantity::from(&format!("{:.8}", q));

            let quote = QuoteTick::new(
                instrument_id.clone(),
                price, // Bid Price
                price, // Ask Price  
                qty,   // Bid Size
                qty,   // Ask Size
                ts_ns.into(),
                ts_ns.into(),
            );
            all_quotes.push(Data::Quote(quote));
        }
    }

    println!("Loaded {} quotes.", all_quotes.len());

    // 3. Setup backtest engine
    let mut engine = BacktestEngine::new(BacktestEngineConfig::default())?;

    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Hedging,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::from("10_000 USD")],
        None, None, AHashMap::new(), vec![], 
        FillModelAny::default(), FeeModelAny::default(),
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
    )?;

    // Create a CurrencyPair manually with specific ID
    let instrument = InstrumentAny::CurrencyPair(CurrencyPair::new(
        instrument_id.clone(),
        Price::from("0.01"),         // price_precision
        Quantity::from("0.000001"),  // quantity_precision
        Quantity::from("0.0001"),    // min_quantity
        None,                        // max_quantity
        None,                        // margin_requirement
        Money::from("0 USD"),        // min_notional
    )?);

    engine.add_instrument(instrument)?;

    let strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("0.1"), // BTC size
        10,
        20,
    );
    engine.add_strategy(strategy)?;

    // 4. Run backtest
    println!("Running backtest engine...");
    engine.add_data(all_quotes, None, true, true);
    engine.run(None, None, None, false);

    let result = engine.get_result();
    println!("--- Results ---");
    println!("Result: {:?}", result);

    Ok(())
}
