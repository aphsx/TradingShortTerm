use ahash::AHashMap;
use anyhow::Result;
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    data::{Data, QuoteTick},
    enums::{AccountType, BookType, OmsType},
    identifiers::{InstrumentId, Symbol, Venue},
    instruments::{Instrument, InstrumentAny, stubs::audusd_sim},
    types::{Money, Price, Quantity},
};
use nautilus_trading::examples::strategies::EmaCross;
use reqwest::Client;
use serde::Deserialize;
use chrono::Utc;

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
    println!("--- VORTEX-7 Backtest ---");

    // Configuration
    let symbol = "BTCUSDT";
    let duration_hours = 1;
    let end_time = Utc::now().timestamp_millis();
    let start_time = end_time - (duration_hours * 3600 * 1000);

    // Download data
    println!("Downloading data for {}...", symbol);
    let trades = download_trades(symbol, start_time, end_time).await?;
    println!("Downloaded {} trades", trades.len());

    // Setup backtest engine
    let mut engine = BacktestEngine::new(BacktestEngineConfig::default())?;

    engine.add_venue(
        Venue::from("BINANCE"),
        OmsType::Hedging,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::from("10_000 USD")],
        None, None, AHashMap::new(), vec![], 
        FillModelAny::default(), FeeModelAny::default(),
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
    )?;

    let instrument = InstrumentAny::CurrencyPair(audusd_sim());
    let instrument_id = instrument.id();
    
    // Create proper BTCUSDT instrument with BINANCE venue
    let btc_instrument = create_btcusdt_instrument();
    engine.add_instrument(btc_instrument)?;

    let strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("1"),
        10,
        20,
    );
    engine.add_strategy(strategy)?;

    // Run backtest
    let data: Vec<Data> = trades.into_iter().map(Data::Quote).collect();
    println!("Running backtest with {} data points...", data.len());
    
    engine.add_data(data, None, true, true);
    engine.run(None, None, None, false);

    let result = engine.get_result();
    println!("--- Results ---");
    println!("Result: {:?}", result);

    Ok(())
}

async fn download_trades(symbol: &str, start_time: i64, end_time: i64) -> Result<Vec<QuoteTick>> {
    let client = Client::new();
    let mut all_trades = Vec::new();
    let mut current_start = start_time;
    const BATCH_SIZE: i64 = 1000;
    const BATCH_TIME: i64 = 60 * 1000;

    while current_start < end_time {
        let batch_end = std::cmp::min(current_start + BATCH_TIME, end_time);
        
        let url = format!(
            "https://fapi.binance.com/fapi/v1/aggTrades?symbol={}&startTime={}&endTime={}&limit={}",
            symbol, current_start, batch_end, BATCH_SIZE
        );

        let response = client.get(&url).send().await?;
        if response.status().is_server_error() || response.status().is_client_error() {
            println!("API error for batch {}: {}", current_start, response.status());
            current_start = batch_end;
            continue;
        }
        
        let response_text = response.text().await?;
        if response_text.trim().is_empty() || response_text.trim() == "null" {
            println!("Empty response for batch {}, skipping", current_start);
            current_start = batch_end;
            continue;
        }
        
        let trades: Vec<BinanceAggTrade> = serde_json::from_str(&response_text)?;
        let trades_count = trades.len();
        println!("Downloaded {} trades for batch {}", trades_count, current_start);
        
        let instrument_id = InstrumentId::new(
            Symbol::from(format!("{}.BINANCE", symbol)),
            Venue::from("BINANCE")
        );

        for trade in trades {
            let price = Price::from(trade.price.as_str());
            let qty = Quantity::from(trade.qty.as_str());
            
            let quote = QuoteTick::new(
                instrument_id.clone(),
                price, // Bid Price
                price, // Ask Price  
                qty,   // Bid Size
                qty,   // Ask Size
                (trade.time as u64).into(),
                (trade.time as u64).into(),
            );
            all_trades.push(quote);
        }

        current_start = batch_end;
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }

    Ok(all_trades)
}
