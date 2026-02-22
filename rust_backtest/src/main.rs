mod data;

use ahash::AHashMap;
use anyhow::Result;
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    data::Data,
    enums::{AccountType, BookType, OmsType},
    identifiers::{InstrumentId, Venue},
    instruments::{Instrument, InstrumentAny, stubs::audusd_sim},
    types::{Money, Quantity},
};
use nautilus_trading::examples::strategies::EmaCross;
use std::path::Path;
use chrono::Utc;
use data::BinanceDownloader;

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Rust Backtester ---");

    // 1. Setup Data
    let symbol = "BTCUSDT";
    let data_path = Path::new("data_cache_agg.parquet");
    let mut data = Vec::new();

    if !data_path.exists() {
        println!("Data not found, downloading from Binance...");
        let downloader = BinanceDownloader::new();
        let end_time = Utc::now().timestamp_millis();
        let start_time = end_time - (3600 * 1000); // 1 hour ago
        
        data = downloader.download_agg_trades(symbol, start_time, end_time).await?;
        downloader.save_to_parquet(&data, data_path)?;
        println!("Downloaded {} ticks and saved to {:?}", data.len(), data_path);
    } else {
        println!("Loading data from cache: {:?}", data_path);
        // (In a full implementation, you'd load from Parquet back to Data objects)
        // For now, let's re-download to ensure we have fresh Data objects for the engine
        // until we implement the Parquet -> Data loader.
        let downloader = BinanceDownloader::new();
        let end_time = Utc::now().timestamp_millis();
        let start_time = end_time - (3600 * 1000); 
        data = downloader.download_agg_trades(symbol, start_time, end_time).await?;
    }

    // 2. Initialize Engine
    let mut engine = BacktestEngine::new(BacktestEngineConfig::default())?;

    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Hedging,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::from("1_000_000 USD")],
        None,            // base_currency
        None,            // default_leverage
        AHashMap::new(), // leverages
        vec![],          // modules
        FillModelAny::default(),
        FeeModelAny::default(),
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
    )?;

    // We use AUDUSD sim for now as a placeholder instrument, in real use you'd define BTCUSDT properly
    let instrument = InstrumentAny::CurrencyPair(audusd_sim());
    let instrument_id = instrument.id();
    engine.add_instrument(instrument)?;

    // 3. Add Strategy
    let strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("1"),
        10,
        20,
    );
    engine.add_strategy(strategy)?;

    // 4. Run with real data
    println!("Feeding {} ticks into engine...", data.len());
    engine.add_data(data, None, true, true);

    println!("Starting simulation...");
    engine.run(None, None, None, false);

    let result = engine.get_result();
    println!("--- Backtest Complete ---");
    println!("Result: {:?}", result);

    Ok(())
}
