use ahash::AHashMap;
use anyhow::Result;
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    data::{Data, QuoteTick, TradeTick},
    enums::{AccountType, BookType, OmsType, AggressorSide},
    identifiers::{InstrumentId, Symbol, Venue, TradeId},
    instruments::{InstrumentAny, CurrencyPair},
    types::{Money, Price, Quantity, Currency},
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
    
    let mut all_trades = Vec::new();
    let instrument_id = InstrumentId::new(
        Symbol::from(symbol_str.as_ref()),
        Venue::from("SIM")
    );

    for file_path in files {
        let df = LazyFrame::scan_parquet(file_path, Default::default())?
            .collect()?;
        
        let timestamps = df.column("timestamp")?.str()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;
        let open_times = df.column("open_time")?.i64()?;

        for i in 0..df.height() {
            let timestamp = timestamps.get(i).unwrap_or("");
            let open = opens.get(i).unwrap_or(0.0);
            let high = highs.get(i).unwrap_or(0.0);
            let low = lows.get(i).unwrap_or(0.0);
            let close = closes.get(i).unwrap_or(0.0);
            let volume = volumes.get(i).unwrap_or(0.0);
            let t = open_times.get(i).unwrap_or(0);

            // Nautilus expects Nanoseconds
            let ts_ns = (t as u64) * 1_000_000;
            
            // Create synthetic trade ticks from OHLCV data
            // Use close price as trade price and volume as trade size
            let price = Price::from(&format!("{:.2}", close));
            let qty = Quantity::from(&format!("{:.8}", volume));
            let trade_id = TradeId::new(format!("trade_{}", i).as_str());
            
            let trade = TradeTick::new(
                instrument_id.clone(),
                price,
                qty,
                AggressorSide::Buyer, // Assume buyer aggressor
                trade_id,
                ts_ns.into(),
                ts_ns.into(),
            );
            all_trades.push(Data::Trade(trade));
        }
    }

    println!("Loaded {} trade ticks.", all_trades.len());

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

    // Create a basic currency pair instrument  
    let instrument = InstrumentAny::CurrencyPair(
        CurrencyPair::new(
            instrument_id.clone(),
            Symbol::from(symbol_str.as_str()),
            Currency::from("BTC"),
            Currency::from("USDT"),
            8,  // price_precision
            8,  // quantity_precision
            Price::from("0.01"),         // price_increment
            Quantity::from("0.000001"),  // size_increment
            Some(Quantity::from("1.0")), // multiplier
            None,                        // lot_size
            Some(Quantity::from("0.0001")), // min_quantity
            None,                        // max_quantity
            Some(Money::from("1 USD")),   // min_notional
            None,                        // max_notional
            None,                        // min_price
            None,                        // max_price
            None,                        // margin_init
            None,                        // margin_maint
            None,                        // margin_buy
            None,                        // margin_sell
            None,                        // params
            0.into(),                    // ts_event
            0.into(),                    // ts_init
        )
    );

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
    engine.add_data(all_trades, None, true, true);
    engine.run(None, None, None, false)?;

    let result = engine.get_result();
    println!("--- Results ---");
    println!("Result: {:?}", result);

    Ok(())
}
