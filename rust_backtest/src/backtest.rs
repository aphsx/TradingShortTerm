use anyhow::Result;
use polars::prelude::*;
use std::path::Path;
use glob::glob;

// Import Nautilus for realistic backtest
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    data::{Data, QuoteTick, TradeTick},
    enums::{AccountType, BookType, OmsType, AggressorSide},
    identifiers::{InstrumentId, Symbol, Venue, TradeId},
    instruments::{InstrumentAny, CurrencyPair},
    types::{Money, Price, Quantity, Currency},
};

// Import MFT strategy
use mft_engine::{
    config::AppConfig,
    data::Kline,
    strategy::{StrategyEngine, TradeSignal},
};

// Import Nautilus trading traits
use nautilus_trading::strategy::Strategy;

// Bridge between MFT strategy and Nautilus engine
struct MftStrategyWrapper {
    mft_engine: StrategyEngine,
    instrument_id: InstrumentId,
    klines: Vec<Kline>,
    current_index: usize,
}

impl MftStrategyWrapper {
    fn new(mft_engine: StrategyEngine, instrument_id: InstrumentId) -> Self {
        Self {
            mft_engine,
            instrument_id,
            klines: Vec::new(),
            current_index: 0,
        }
    }
    
    fn add_klines(&mut self, klines: Vec<Kline>) {
        self.klines = klines;
        self.current_index = 0;
    }
    
    fn process_next_bar(&mut self) -> Option<TradeSignal> {
        if self.current_index >= self.klines.len() {
            return None;
        }
        
        let current_bar = &self.klines[self.current_index];
        let prev_close = if self.current_index > 0 {
            self.klines[self.current_index - 1].close
        } else {
            current_bar.open
        };
        
        let log_return = if prev_close > 0.0 {
            (current_bar.close / prev_close).ln()
        } else {
            0.0
        };
        
        let tick = current_bar.to_tick();
        let signal = self.mft_engine.on_bar(current_bar.close, log_return, &tick);
        
        self.current_index += 1;
        signal
    }
}

// Implement Nautilus Strategy trait (simplified)
impl Strategy for MftStrategyWrapper {
    // This is a simplified implementation - you'd need to implement all required methods
    // For now, we'll use a basic approach
}

#[tokio::main]
async fn main() -> Result<()> {
    println!("--- VORTEX-7 Offline Backtest ---");

    // 1. Configuration - Read from .env
    dotenvy::dotenv().ok();

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
    
    // Convert all data to Kline structs
    let mut all_klines = Vec::new();

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
            let open_time = open_times.get(i).unwrap_or(0);

            // Create Kline struct for mft_engine
            let kline = Kline {
                open_time,
                open,
                high,
                low,
                close,
                volume,
                close_time: open_time + 59_999, // Approximate close time (1min - 1ms)
                quote_vol: close * volume,
                n_trades: 1, // Not available from kline data
                taker_buy_base_vol: volume * 0.5, // Assume 50% taker buy
            };
            all_klines.push(kline);
        }
    }

    println!("Loaded {} klines.", all_klines.len());

    // 3. Setup MFT strategy engine
    let mut config = AppConfig::from_env()?;
    config.trading_pairs = vec![symbol_str.clone()];
    
    let mut mft_strategy = StrategyEngine::new(config);
    
    // 4. Setup Nautilus backtest engine
    let mut engine = BacktestEngine::new(BacktestEngineConfig::default())?;

    engine.add_venue(
        Venue::from("SIM"),
        OmsType::Hedging,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::from("1_000 USD")],
        None, None, std::collections::HashMap::new(), vec![], 
        FillModelAny::default(), FeeModelAny::default(),
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
    )?;

    // Create a basic currency pair instrument  
    let instrument_id = InstrumentId::new(
        Symbol::from(symbol_str.as_ref()),
        Venue::from("SIM")
    );
    
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

    // 5. Create custom strategy wrapper for MFT
    let mft_wrapper = MftStrategyWrapper::new(mft_strategy, instrument_id.clone());
    engine.add_strategy(Box::new(mft_wrapper))?;

    Ok(())
}
