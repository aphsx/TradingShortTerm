mod complete_data;

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

    // 2. Load and process complete data
    let mut all_data = Vec::new();
    
    // Load trades (with aggressor direction - critical for Engine2)
    println!("Loading trade data with direction...");
    // TODO: Implement Parquet -> TradeTick loader
    
    // Load orderbook snapshots (critical for Engine1)
    println!("Loading orderbook snapshots...");
    // TODO: Implement Parquet -> QuoteTick loader
    
    // Load klines (for Engine3 and Engine5)
    println!("Loading 1m and 15m klines...");
    // TODO: Implement Parquet -> Kline loader
    
    // Load sentiment data (for Engine4)
    println!("Loading sentiment data...");
    // TODO: Implement Parquet -> Sentiment loader

    // 3. Initialize Engine with same configuration as live bot
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

    // Create proper BTCUSDT instrument (not AUDUSD placeholder)
    let instrument = create_btcusdt_instrument();
    let instrument_id = instrument.id();
    engine.add_instrument(instrument)?;

    // 4. Add VORTEX-7 Strategy (not EmaCross)
    // TODO: Implement VortexStrategy that uses all 5 engines like the live bot
    let strategy = VortexStrategy::new(
        instrument_id.clone(),
        Quantity::from("0.001"), // Min position size
    );
    engine.add_strategy(strategy)?;

    // 5. Run with complete data (matching live bot processing)
    println!("Running backtest with complete dataset...");
    println!("Data sources: Trades + OrderBook + Klines(1m/15m) + Sentiment");
    
    engine.add_data(all_data, None, true, true);

    println!("Starting simulation...");
    engine.run(None, None, None, false);

    let result = engine.get_result();
    println!("--- Complete Backtest Results ---");
    println!("Result: {:?}", result);

    Ok(())
}

// Create proper BTCUSDT instrument matching live bot
fn create_btcusdt_instrument() -> InstrumentAny {
    use nautilus_model::{
        enums::{AssetClass, OptionKind},
        instruments::{currency_pair::CurrencyPair, Instrument},
        identifiers::{Symbol, Venue},
        types::{Currency, Price, Quantity},
    };

    let symbol = Symbol::from("BTCUSDT");
    let venue = Venue::from("BINANCE");
    let base_currency = Currency::BTC();
    let quote_currency = Currency::USDT();
    let price_precision = 2;
    let size_precision = 8;
    let price_increment = Price::from("0.01");
    let size_increment = Quantity::from("0.00000001");
    let lot_size = Some(Quantity::from("0.00000001"));
    let max_quantity = Some(Quantity::from("1000"));
    let min_quantity = Some(Quantity::from("0.00000001"));
    let max_price = Some(Price::from("1000000"));
    let min_price = Some(Price::from("0.01"));
    let margin_init = Some(0.10); // 10% initial margin (10x leverage)
    let margin_maint = Some(0.05); // 5% maintenance margin

    let currency_pair = CurrencyPair::new(
        symbol,
        base_currency,
        quote_currency,
        price_precision,
        size_precision,
        price_increment,
        size_increment,
        lot_size,
        max_quantity,
        min_quantity,
        max_price,
        min_price,
        margin_init,
        margin_maint,
    );

    Instrument::new(
        InstrumentId::new(symbol, venue),
        currency_pair,
        Venue::from("BINANCE"),
        AssetClass::Crypto,
        Some(Currency::USDT()),
    ).into()
}

// VORTEX-7 Strategy implementation matching live bot logic
struct VortexStrategy {
    instrument_id: InstrumentId,
    position_size: Quantity,
    // Add all 5 engines like in live bot
    // engine1: Engine1OrderFlow,
    // engine2: Engine2Tick,
    // engine3: Engine3Technical,
    // engine4: Engine4Sentiment,
    // engine5: Engine5Regime,
    // decision_engine: DecisionEngine,
    // risk_manager: RiskManager,
}

impl VortexStrategy {
    fn new(instrument_id: InstrumentId, position_size: Quantity) -> Self {
        Self {
            instrument_id,
            position_size,
            // Initialize all engines with same parameters as live bot
        }
    }
}

// TODO: Implement VortexStrategy trait with all 5 engines
// This will process data exactly like the live bot:
// - Engine1: OrderBook + Ticks → OrderFlow analysis
// - Engine2: Ticks → Momentum analysis  
// - Engine3: Klines → Technical analysis
// - Engine4: Sentiment → Market positioning
// - Engine5: Klines → Regime detection
// - DecisionEngine: Combine all signals
// - RiskManager: Position sizing & risk management
