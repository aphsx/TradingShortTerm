mod complete_data;

use ahash::AHashMap;
use anyhow::Result;
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    enums::{AccountType, BookType, OmsType},
    identifiers::{InstrumentId, Venue},
    instruments::{Instrument, InstrumentAny, stubs::audusd_sim},
    types::{Money, Quantity},
};
use nautilus_trading::examples::strategies::EmaCross;
use std::path::Path;
use chrono::Utc;
use complete_data::CompleteDataCollector;

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Complete Backtester (Live Bot Data Alignment) ---");

    // 1. Setup Data - Same as Live Bot
    let symbol = "BTCUSDT";
    let data_path = Path::new("complete_data_cache");
    std::fs::create_dir_all(data_path)?;

    let end_time = Utc::now().timestamp_millis();
    let start_time = end_time - (2 * 3600 * 1000); // 2 hours for complete dataset

    // Check if we have cached complete data
    let trades_path = data_path.join("trades.parquet");
    let orderbooks_path = data_path.join("orderbooks.parquet");
    let klines_1m_path = data_path.join("klines_1m.parquet");
    let klines_15m_path = data_path.join("klines_15m.parquet");
    let sentiment_path = data_path.join("sentiment.parquet");

    if !trades_path.exists() || !orderbooks_path.exists() || !klines_1m_path.exists() {
        println!("Downloading complete dataset matching live bot data sources...");
        let collector = CompleteDataCollector::new();
        let dataset = collector.download_complete_dataset(symbol, start_time, end_time).await?;
        collector.save_complete_dataset(&dataset, data_path)?;
        println!("Complete dataset downloaded and saved!");
    } else {
        println!("Using cached complete dataset from: {:?}", data_path);
    }

    // 2. Initialize Engine with same configuration as live bot
    let mut engine = BacktestEngine::new(BacktestEngineConfig::default())?;

    engine.add_venue(
        Venue::from("BINANCE"),
        OmsType::Hedging,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::from("10_000 USD")], // Same as BASE_BALANCE in config
        None,            // base_currency
        None,            // default_leverage
        AHashMap::new(), // leverages
        vec![],          // modules
        FillModelAny::default(),
        FeeModelAny::default(),
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
    )?;

    // Use AUDUSD sim for now (will replace with proper BTCUSDT later)
    let instrument = InstrumentAny::CurrencyPair(audusd_sim());
    let instrument_id = instrument.id();
    engine.add_instrument(instrument)?;

    // 3. Add EmaCross strategy for now (will replace with VortexStrategy later)
    let strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("1"),
        10,
        20,
    );
    engine.add_strategy(strategy)?;

    // 4. For now, use simple aggregated trades data to test the engine
    println!("Loading basic trade data for testing...");
    let collector = CompleteDataCollector::new();
    let basic_trades = collector.download_agg_trades(symbol, start_time, end_time).await?;
    
    // Convert QuoteTick to Data enum
    let basic_data: Vec<nautilus_model::data::Data> = basic_trades
        .into_iter()
        .map(nautilus_model::data::Data::Quote)
        .collect();
    
    println!("Running backtest with basic quote data...");
    println!("Note: This is a simplified version to test the engine setup.");
    println!("The complete version with all 5 engines will be implemented next.");
    
    engine.add_data(basic_data, None, true, true);

    println!("Starting simulation...");
    engine.run(None, None, None, false);

    let result = engine.get_result();
    println!("--- Basic Backtest Results ---");
    println!("Result: {:?}", result);

    println!("\n✅ Engine setup successful!");
    println!("🔄 Next: Implement complete VortexStrategy with all 5 engines");

    Ok(())
}
