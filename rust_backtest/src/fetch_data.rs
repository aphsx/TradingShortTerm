use anyhow::{Context, Result};
use chrono::Utc;
use polars::prelude::*;
use reqwest::Client;
use serde::Deserialize;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
struct BinanceAggTrade {
    #[serde(rename = "a")]
    agg_id: i64,
    #[serde(rename = "p")]
    price: String,
    #[serde(rename = "q")]
    qty: String,
    #[serde(rename = "T")]
    time: i64,
    #[serde(rename = "m")]
    is_buyer_maker: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    // 1. Load .env from mft_engine directory
    let env_path = Path::new("..").join("mft_engine").join(".env");
    println!("Loading .env from: {:?}", env_path);
    dotenvy::from_path(env_path).ok();

    // 2. Get Trading Pairs
    let trading_pairs_str = std::env::var("TRADING_PAIRS").unwrap_or_else(|_| "BTCUSDT".to_string());
    let symbols: Vec<&str> = trading_pairs_str.split(',').collect();
    
    // 3. Setup Config
    let base_url = "https://fapi.binance.com";
    let client = Client::new();
    let duration_hours = 24; // Download last 24 hours of data
    let end_time = Utc::now().timestamp_millis();
    let start_time = end_time - (duration_hours * 3600 * 1000);

    println!("Target Symbols: {:?}", symbols);
    println!("Fetching last {} hours of data...", duration_hours);

    for symbol in symbols {
        let symbol = symbol.trim();
        if symbol.is_empty() { continue; }

        println!("--- Processing {} ---", symbol);
        
        // Create directory
        let dir_path = PathBuf::from("data").join(symbol);
        fs::create_dir_all(&dir_path)?;

        let trades = download_agg_trades(&client, base_url, symbol, start_time, end_time).await?;
        
        if trades.is_empty() {
            println!("No trades found for {}", symbol);
            continue;
        }

        // Convert to Polars DataFrame
        let mut df = trades_to_dataframe(trades)?;
        
        // Save as Parquet
        let file_name = format!("{}_{}.parquet", symbol, Utc::now().format("%Y%m%d_%H%M%S"));
        let file_path = dir_path.join(file_name);
        
        println!("Saving {} rows to {:?}", df.height(), file_path);
        
        let mut file = std::fs::File::create(&file_path)?;
        ParquetWriter::new(&mut file).finish(&mut df)?;
    }

    Ok(())
}

async fn download_agg_trades(
    client: &Client,
    base_url: &str,
    symbol: &str,
    start_time: i64,
    end_time: i64,
) -> Result<Vec<BinanceAggTrade>> {
    let mut all_trades = Vec::new();
    let mut current_start = start_time;
    const BATCH_TIME: i64 = 60 * 60 * 1000; // 1 hour per batch

    while current_start < end_time {
        let batch_end = std::cmp::min(current_start + BATCH_TIME, end_time);
        
        let url = format!(
            "{}/fapi/v1/aggTrades?symbol={}&startTime={}&endTime={}&limit=1000",
            base_url, symbol, current_start, batch_end
        );

        let response = client.get(&url).send().await?;
        if !response.status().is_success() {
            println!("  [!] Error fetching {} at {}: {}", symbol, current_start, response.status());
            current_start = batch_end;
            continue;
        }

        let trades: Vec<BinanceAggTrade> = response.json().await?;
        let count = trades.len();
        
        if count > 0 {
            let last_time = trades.last().unwrap().time;
            all_trades.extend(trades);
            
            if count == 1000 {
                current_start = last_time + 1;
            } else {
                current_start = batch_end;
            }
        } else {
            current_start = batch_end;
        }

        print!("\r  Fetched {} trades for {}...", all_trades.len(), symbol);
        use std::io::Write;
        std::io::stdout().flush().ok();
        
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }
    println!();

    Ok(all_trades)
}

fn trades_to_dataframe(trades: Vec<BinanceAggTrade>) -> Result<DataFrame> {
    let agg_ids: Vec<i64> = trades.iter().map(|t| t.agg_id).collect();
    let prices: Vec<f64> = trades.iter().map(|t| t.price.parse::<f64>().unwrap_or(0.0)).collect();
    let qtys: Vec<f64> = trades.iter().map(|t| t.qty.parse::<f64>().unwrap_or(0.0)).collect();
    let times: Vec<i64> = trades.iter().map(|t| t.time).collect();
    let is_buyer_maker: Vec<bool> = trades.iter().map(|t| t.is_buyer_maker).collect();

    let df = df!(
        "agg_id" => agg_ids,
        "price" => prices,
        "qty" => qtys,
        "time" => times,
        "is_buyer_maker" => is_buyer_maker
    )?;

    Ok(df)
}
