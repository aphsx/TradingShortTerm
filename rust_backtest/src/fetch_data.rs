use anyhow::Result;
use chrono::{DateTime, TimeZone, Utc};
use polars::prelude::*;
use reqwest::Client;
use serde::Deserialize;
use std::fs;
use std::path::{Path, PathBuf};
use tokio::time::{sleep, Duration};

#[derive(Debug, Deserialize)]
struct BinanceKline {
    #[serde(rename = "0")]
    open_time: i64,
    #[serde(rename = "1")]
    open: String,
    #[serde(rename = "2")]
    high: String,
    #[serde(rename = "3")]
    low: String,
    #[serde(rename = "4")]
    close: String,
    #[serde(rename = "5")]
    volume: String,
    #[serde(rename = "6")]
    close_time: i64,
    #[serde(rename = "7")]
    quote_asset_volume: String,
    #[serde(rename = "8")]
    number_of_trades: i64,
    #[serde(rename = "9")]
    taker_buy_base_asset_volume: String,
    #[serde(rename = "10")]
    taker_buy_quote_asset_volume: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    // 1. Load .env from mft_engine directory
    let env_path = Path::new("..").join("mft_engine").join(".env");
    println!("Loading .env from: {:?}", env_path);
    dotenvy::from_path(env_path).ok();

    // 2. Get Trading Pairs & URL
    let trading_pairs_str = std::env::var("TRADING_PAIRS").unwrap_or_else(|_| "BTCUSDT".to_string());
    let symbols: Vec<&str> = trading_pairs_str.split(',').collect();
    
    let base_url = std::env::var("BINANCE_FUTURES_REST_URL")
        .unwrap_or_else(|_| "https://fapi.binance.com".to_string());
    
    // 3. Setup Config
    let client = Client::new();
    let duration_hours = 24; // Download last 24 hours of klines
    let end_time = Utc::now().timestamp_millis();
    let start_time = end_time - (duration_hours * 3600 * 1000);
    let interval = "1m"; // 1-minute candles

    println!("Target Symbols: {:?}", symbols);
    println!("Base URL: {}", base_url);
    println!("Fetching last {} hours of {} klines...", duration_hours, interval);

    for symbol in symbols {
        let symbol = symbol.trim();
        if symbol.is_empty() { continue; }

        println!("--- Processing {} ---", symbol);
        
        let dir_path = PathBuf::from("data").join(symbol);
        fs::create_dir_all(&dir_path)?;

        let klines = download_klines(&client, &base_url, symbol, interval, start_time, end_time).await?;
        
        if klines.is_empty() {
            println!("No klines found for {}", symbol);
            continue;
        }

        let mut df = klines_to_dataframe(klines)?;
        
        let file_name = format!("{}_{}.parquet", symbol, Utc::now().format("%Y%m%d_%H%M%S"));
        let file_path = dir_path.join(file_name);
        
        println!("Saving {} rows to {:?}", df.height(), file_path);
        
        let mut file = std::fs::File::create(&file_path)?;
        ParquetWriter::new(&mut file).finish(&mut df)?;
    }

    Ok(())
}

async fn download_klines(
    client: &Client,
    base_url: &str,
    symbol: &str,
    interval: &str,
    start_time: i64,
    end_time: i64,
) -> Result<Vec<BinanceKline>> {
    let mut all_klines = Vec::new();
    let mut current_start = start_time;
    const BATCH_TIME: i64 = 60 * 60 * 1000; // 1 hour per batch (1000 * 1min candles)

    while current_start < end_time {
        let batch_end = std::cmp::min(current_start + BATCH_TIME, end_time);
        
        let url = format!(
            "{}/fapi/v1/klines?symbol={}&interval={}&startTime={}&endTime={}&limit=1000",
            base_url, symbol, interval, current_start, batch_end
        );

        let response = client.get(&url).send().await?;
        
        if response.status() == 429 {
            println!("\n  [!] Rate limited (429). Sleeping for 10 seconds...");
            sleep(Duration::from_secs(10)).await;
            continue;
        }

        if !response.status().is_success() {
            println!("\n  [!] Error fetching {} at {}: {}", symbol, current_start, response.status());
            current_start = batch_end;
            continue;
        }

        let klines_raw: Vec<Vec<String>> = response.json().await?;
        let count = klines_raw.len();
        
        if count > 0 {
            let klines: Vec<BinanceKline> = klines_raw.into_iter().map(|arr| BinanceKline {
                open_time: arr[0].parse().unwrap_or(0),
                open: arr[1].clone(),
                high: arr[2].clone(),
                low: arr[3].clone(),
                close: arr[4].clone(),
                volume: arr[5].clone(),
                close_time: arr[6].parse().unwrap_or(0),
                quote_asset_volume: arr[7].clone(),
                number_of_trades: arr[8].parse().unwrap_or(0),
                taker_buy_base_asset_volume: arr[9].clone(),
                taker_buy_quote_asset_volume: arr[10].clone(),
            }).collect();
            
            let last_time = klines.last().unwrap().close_time;
            all_klines.extend(klines);
            
            if count == 1000 {
                // If we got max results, resume from the last kline close time
                current_start = last_time + 1;
            } else {
                current_start = batch_end;
            }
        } else {
            current_start = batch_end;
        }

        print!("\r  Fetched {} klines for {}...", all_klines.len(), symbol);
        use std::io::Write;
        std::io::stdout().flush().ok();
        
        // Politeness delay
        sleep(Duration::from_millis(250)).await;
    }
    println!();

    Ok(all_klines)
}

fn klines_to_dataframe(klines: Vec<BinanceKline>) -> Result<DataFrame> {
    let open_times: Vec<i64> = klines.iter().map(|k| k.open_time).collect();
    let opens: Vec<f64> = klines.iter().map(|k| k.open.parse::<f64>().unwrap_or(0.0)).collect();
    let highs: Vec<f64> = klines.iter().map(|k| k.high.parse::<f64>().unwrap_or(0.0)).collect();
    let lows: Vec<f64> = klines.iter().map(|k| k.low.parse::<f64>().unwrap_or(0.0)).collect();
    let closes: Vec<f64> = klines.iter().map(|k| k.close.parse::<f64>().unwrap_or(0.0)).collect();
    let volumes: Vec<f64> = klines.iter().map(|k| k.volume.parse::<f64>().unwrap_or(0.0)).collect();
    let close_times: Vec<i64> = klines.iter().map(|k| k.close_time).collect();
    let quote_asset_volumes: Vec<f64> = klines.iter().map(|k| k.quote_asset_volume.parse::<f64>().unwrap_or(0.0)).collect();
    let number_of_trades: Vec<i64> = klines.iter().map(|k| k.number_of_trades).collect();
    
    // Convert timestamps to readable datetime strings
    let timestamps: Vec<String> = open_times.iter()
        .map(|&ts| {
            let dt = Utc.timestamp_millis_opt(ts).unwrap();
            dt.format("%Y-%m-%d %H:%M:%S").to_string()
        })
        .collect();

    let df = df!(
        "timestamp" => timestamps,
        "open" => opens,
        "high" => highs,
        "low" => lows,
        "close" => closes,
        "volume" => volumes,
        "open_time" => open_times,
        "close_time" => close_times,
        "quote_asset_volume" => quote_asset_volumes,
        "number_of_trades" => number_of_trades
    )?;

    Ok(df)
}
