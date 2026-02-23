use anyhow::Result;
use dotenv::dotenv;
use log::info;
use mft_engine::engine::TradingEngine;

#[tokio::main]
async fn main() -> Result<()> {
    dotenv().ok();
    env_logger::init();

    println!("=== Starting Binance Futures Trading Bot ===");
    info!("Starting Binance Futures Trading Bot...");

    println!("Creating trading engine...");
    let mut engine = TradingEngine::new().await?;
    
    println!("Running trading engine...");
    engine.run().await?;
    
    println!("=== Trading bot completed successfully ===");

    Ok(())
}
