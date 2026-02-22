use ahash::AHashMap;
use nautilus_backtest::{config::BacktestEngineConfig, engine::BacktestEngine};
use nautilus_execution::models::{fee::FeeModelAny, fill::FillModelAny};
use nautilus_model::{
    data::{Data, QuoteTick},
    enums::{AccountType, BookType, OmsType},
    identifiers::{InstrumentId, Venue},
    instruments::{Instrument, InstrumentAny, stubs::audusd_sim},
    types::{Money, Price, Quantity},
};
use nautilus_trading::examples::strategies::EmaCross;

fn quote(instrument_id: InstrumentId, bid: &str, ask: &str, ts: u64) -> Data {
    Data::Quote(QuoteTick::new(
        instrument_id,
        Price::from(bid),
        Price::from(ask),
        Quantity::from("100000"),
        Quantity::from("100000"),
        ts.into(),
        ts.into(),
    ))
}

fn generate_quotes(instrument_id: InstrumentId) -> Vec<Data> {
    let spread = 0.00020;
    let base_ts: u64 = 1_735_689_600_000_000_000; // 2025-01-01T00:00:00Z
    let interval: u64 = 1_000_000_000;
    let mut quotes = Vec::new();
    let mut tick: u64 = 0;

    let mut add = |mid: f64| {
        let bid = format!("{mid:.5}");
        let ask = format!("{:.5}", mid + spread);
        quotes.push(quote(instrument_id.clone(), &bid, &ask, base_ts + tick * interval));
        tick += 1;
    };

    // Flat initialization
    for _ in 0..25 {
        add(0.65000);
    }

    // Cycles
    let cycles = 2;
    for cycle in 0..cycles {
        let base = 0.65000 + (cycle as f64 * 0.00100);
        for i in 0..20 {
            add(base + (i as f64 * 0.00050));
        }
        for i in 0..40 {
            let peak = base + 19.0 * 0.00050;
            add(peak - (i as f64 * 0.00050));
        }
    }

    quotes
}

fn main() -> anyhow::Result<()> {
    println!("Initializing Nautilus Trader Backtest Engine...");
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
        None, // latency
        None, // routing
        None, // reject_stop
        None, // support_gtd
        None, // support_contingent
        None, // use_position_ids
        None, // use_random_ids
        None, // use_reduce_only
        None, // use_message_queue
        None, // use_market_order_acks
        None, // bar_execution
        None, // bar_adaptive
        None, // trade_execution
        None, // liquidity
        None, // allow_cash
        None, // frozen
        None, // price_protection
    )?;

    let instrument = InstrumentAny::CurrencyPair(audusd_sim());
    let instrument_id = instrument.id();
    engine.add_instrument(instrument)?;

    let strategy = EmaCross::new(
        instrument_id.clone(),
        Quantity::from("10000"),
        10,
        20,
    );
    engine.add_strategy(strategy)?;

    println!("Generating synthetic data...");
    let quotes = generate_quotes(instrument_id);
    engine.add_data(quotes, None, true, true);

    println!("Running backtest...");
    engine.run(None, None, None, false);

    println!("Backtest complete. Generating report...");
    let result = engine.get_result();
    println!("Backtest Result: {:?}", result);

    Ok(())
}
