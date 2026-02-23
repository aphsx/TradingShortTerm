use anyhow::Result;
use chrono::{DateTime, TimeZone, Utc};
use polars::prelude::*;
use reqwest::Client;
use serde::Deserialize;
use std::fs;
use std::path::{Path, PathBuf};
use tokio::time::{sleep, Duration};

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
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
}

#[tokio::main]
async fn main() -> Result<()> {
    // 1. Load .env from root directory
    dotenvy::from_filename("../.env").ok();

    // 2. Get Trading Pairs & URL from MFT ENGINE config
    let trading_pairs_str = std::env::var("TRADING_PAIRS").unwrap_or_else(|_| "BTCUSDT".to_string());
    let symbols: Vec<&str> = trading_pairs_str.split(',').collect();
    
    let base_url = std::env::var("BINANCE_FUTURES_REST_URL")
        .unwrap_or_else(|_| "https://testnet.binancefuture.com".to_string());
    
    // Use MFT ENGINE interval settings
    let interval = std::env::var("KLINE_INTERVAL").unwrap_or_else(|_| "1m".to_string());
    let backtest_limit = std::env::var("BACKTEST_LIMIT").unwrap_or_else(|_| "43200".to_string());
    let limit_bars: i32 = backtest_limit.parse().unwrap_or(43200);
    
    // Calculate duration based on interval
    let duration_hours = match interval.as_str() {
        "1m" => limit_bars / 60,
        "3m" => limit_bars * 3 / 60,
        "5m" => limit_bars * 5 / 60,
        "15m" => limit_bars * 15 / 60,
        "30m" => limit_bars * 30 / 60,
        "1h" => limit_bars,
        _ => 24, // default to 24 hours if unknown interval
    };
    
    // 3. Setup Config
    let client = Client::new();
    let end_time = Utc::now().timestamp_millis();
    let start_time = end_time - (duration_hours * 3600 * 1000);

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

        // Get raw response text for debugging
        let response_text = response.text().await?;
        let klines_raw: Vec<Vec<serde_json::Value>> = serde_json::from_str(&response_text)
            .map_err(|e| {
                println!("Debug - Raw response: {}", &response_text[..response_text.len().min(200)]);
                anyhow::anyhow!("Failed to parse klines: {}", e)
            })?;
        let count = klines_raw.len();
        
        if count > 0 {
            let klines: Vec<BinanceKline> = klines_raw.into_iter().map(|arr| BinanceKline {
                open_time: arr[0].as_i64().unwrap_or(0),
                open: arr[1].as_str().unwrap_or("0").to_string(),
                high: arr[2].as_str().unwrap_or("0").to_string(),
                low: arr[3].as_str().unwrap_or("0").to_string(),
                close: arr[4].as_str().unwrap_or("0").to_string(),
                volume: arr[5].as_str().unwrap_or("0").to_string(),
            }).collect();
            
            let last_time = klines.last().unwrap().open_time;
            all_klines.extend(klines);
            
            if count == 1000 {
                // If we got max results, resume from the last kline open time
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
        "open_time" => open_times
    )?;

    Ok(df)
}
