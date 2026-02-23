/// backtest.rs — VORTEX-7 NautilusTrader Backtest (Multi-Symbol)
///
/// Architecture:
///   .env (TRADING_PAIRS=BTCUSDT,ETHUSDT,SOLUSDT)
///         │
///         ▼
///   BacktestEngine (Nautilus 0.53.0)
///     ├── Venue: SIM
///     │     ├── FillModel:    FillModelAny::default()
///     │     ├── FeeModel:     MakerTakerFeeModel
///     │     └── LatencyModel: StaticLatencyModel (BACKTEST_LATENCY_MS)
///     ├── Instruments: CryptoPerpetual × N (BTC / ETH / SOL …)
///     ├── Data: Parquet → QuoteTick + TradeTick + Bar × N (sort=true interleaved)
///     └── VortexStrategy
///           ├── HashMap<InstrumentId, StrategyEngine>   ← GARCH+OU+OFI+VPIN+EV+Kelly
///           ├── on_bar(bar) → signal? → submit order
///           └── exit check  → flatten position

mod vortex_strategy;

use anyhow::Result;
use log::LevelFilter;
use std::str::FromStr;

use nautilus_backtest::engine::BacktestEngine;
use nautilus_backtest::config::BacktestEngineConfig;
use nautilus_common::logging::config::LoggerConfig;
use nautilus_core::nanos::UnixNanos;
use nautilus_model::{
    enums::{
        OmsType, AccountType, BookType,
        AggregationSource, BarAggregation, PriceType, AggressorSide,
    },
    identifiers::{InstrumentId, Symbol, Venue, TraderId, TradeId},
    instruments::{InstrumentAny, CryptoPerpetual},
    types::{Price, Quantity, Currency, Money},
    data::{
        Data, Bar, QuoteTick, TradeTick,
        BarType, BarSpecification,
    },
};
use nautilus_execution::models::{
    fee::{FeeModelAny, MakerTakerFeeModel},
    fill::FillModelAny,
    latency::StaticLatencyModel,
};
use ahash::AHashMap;
use rust_decimal::Decimal;
use polars::prelude::*;
use glob::glob;

use mft_engine::config::AppConfig;
use vortex_strategy::{BarAction, VortexStrategy};

// ─── Instrument specification table ───────────────────────────────────────

/// Per-symbol precision and tick-size data.
struct InstrumentSpec {
    symbol:      &'static str,
    base:        &'static str,
    price_prec:  u8,
    size_prec:   u8,
    price_incr:  &'static str,
    size_incr:   &'static str,
}

/// Instrument precision lookup table.
/// Add more rows as you add symbols to TRADING_PAIRS.
static INSTRUMENT_SPECS: &[InstrumentSpec] = &[
    InstrumentSpec { symbol: "BTCUSDT", base: "BTC", price_prec: 1, size_prec: 3, price_incr: "0.1",  size_incr: "0.001" },
    InstrumentSpec { symbol: "ETHUSDT", base: "ETH", price_prec: 2, size_prec: 3, price_incr: "0.01", size_incr: "0.001" },
    InstrumentSpec { symbol: "SOLUSDT", base: "SOL", price_prec: 2, size_prec: 1, price_incr: "0.01", size_incr: "0.1"   },
    InstrumentSpec { symbol: "BNBUSDT", base: "BNB", price_prec: 2, size_prec: 2, price_incr: "0.01", size_incr: "0.01"  },
    InstrumentSpec { symbol: "XRPUSDT", base: "XRP", price_prec: 4, size_prec: 1, price_incr: "0.0001", size_incr: "1.0"  },
];

fn find_spec(symbol: &str) -> Option<&'static InstrumentSpec> {
    INSTRUMENT_SPECS.iter().find(|s| s.symbol == symbol)
}

// ─── main ─────────────────────────────────────────────────────────────────

fn main() -> Result<()> {
    // ─── 0. Environment ────────────────────────────────────────────────
    dotenvy::from_filename("../.env").ok();

    // ─── 1. Configuration ──────────────────────────────────────────────
    let trading_pairs_str = std::env::var("TRADING_PAIRS")
        .unwrap_or_else(|_| "BTCUSDT,ETHUSDT,SOLUSDT".to_string());
    let symbols: Vec<String> = trading_pairs_str
        .split(',')
        .map(|s| s.trim().to_uppercase())
        .filter(|s| !s.is_empty())
        .collect();

    println!("VORTEX-7 NautilusTrader Backtest");
    println!("  Symbols      : {:?}", symbols);

    let initial_cash: f64 = std::env::var("BACKTEST_INITIAL_CASH")
        .unwrap_or_else(|_| "100000".to_string())
        .parse()
        .unwrap_or(100_000.0);
    let latency_ms: u64 = std::env::var("BACKTEST_LATENCY_MS")
        .unwrap_or_else(|_| "30".to_string())
        .parse()
        .unwrap_or(30);
    let spread_bps: f64 = std::env::var("BACKTEST_SPREAD_BPS")
        .unwrap_or_else(|_| "1.0".to_string())
        .parse()
        .unwrap_or(1.0);

    println!("  Initial Cash : {} USDT", initial_cash);
    println!("  Latency      : {} ms", latency_ms);
    println!("  Spread       : {} bps", spread_bps);

    // ─── 2. Nautilus BacktestEngine ────────────────────────────────────
    let logging = LoggerConfig {
        stdout_level: LevelFilter::Info,
        is_colored: true,
        ..LoggerConfig::default()
    };
    let config = BacktestEngineConfig {
        trader_id: TraderId::from("VORTEX7-001"),
        logging,
        ..BacktestEngineConfig::default()
    };
    let mut engine = BacktestEngine::new(config)?;

    // ─── 3. Venue ──────────────────────────────────────────────────────
    let venue = Venue::from("SIM");
    let latency_nanos = UnixNanos::from(latency_ms * 1_000_000);
    let latency_model = StaticLatencyModel::new(
        latency_nanos,
        UnixNanos::from(0u64),
        UnixNanos::from(0u64),
        UnixNanos::from(0u64),
    );

    engine.add_venue(
        venue,
        OmsType::Netting,
        AccountType::Margin,
        BookType::L1_MBP,
        vec![Money::new(initial_cash, Currency::from("USDT"))],
        None,                                           // base_currency
        None,                                           // default_leverage
        AHashMap::new(),                                // leverages
        vec![],                                         // modules
        FillModelAny::default(),                        // fill_model
        FeeModelAny::MakerTaker(MakerTakerFeeModel),   // fee_model
        Some(Box::new(latency_model)),                  // latency_model
        None,                                           // routing
        None,                                           // reject_stop_orders
        None,                                           // support_gtd_orders
        None,                                           // support_contingent_orders
        None,                                           // use_position_ids
        None,                                           // use_random_ids
        None,                                           // use_reduce_only
        None,                                           // use_message_queue
        None,                                           // use_market_order_acks
        None,                                           // bar_execution
        None,                                           // bar_adaptive_high_low_ordering
        None,                                           // trade_execution
        None,                                           // liquidity_consumption
        None,                                           // allow_cash_borrowing
        None,                                           // frozen_account
        None,                                           // price_protection_points
    )?;

    // ─── 4. Instruments ────────────────────────────────────────────────
    let mut instrument_ids: Vec<InstrumentId> = Vec::new();
    let mut bar_types: Vec<BarType> = Vec::new();

    for sym_str in &symbols {
        let spec = find_spec(sym_str.as_str()).ok_or_else(|| {
            anyhow::anyhow!(
                "Symbol '{}' not in INSTRUMENT_SPECS table. Add it to backtest.rs.",
                sym_str
            )
        })?;

        let instr_id = InstrumentId::new(Symbol::from(sym_str.as_str()), venue);

        let instrument = CryptoPerpetual::new_checked(
            instr_id,
            Symbol::from(sym_str.as_str()),
            Currency::from(spec.base),
            Currency::from("USDT"),
            Currency::from("USDT"),
            false,
            spec.price_prec as u8,
            spec.size_prec as u8,
            Price::from(spec.price_incr),
            Quantity::from(spec.size_incr),
            None, None, None, None, None, None, None, None, None, None,
            Some(Decimal::from_str("0.0002").unwrap()),  // maker_fee
            Some(Decimal::from_str("0.0004").unwrap()),  // taker_fee
            None,
            UnixNanos::default(),
            UnixNanos::default(),
        )?;
        engine.add_instrument(InstrumentAny::from(instrument))?;

        let bar_type = BarType::new(
            instr_id,
            BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
            AggregationSource::External,
        );
        instrument_ids.push(instr_id);
        bar_types.push(bar_type);
    }

    // ─── 5. VortexStrategy ─────────────────────────────────────────────
    //    Build one AppConfig per symbol (all use same .env values).
    let base_cfg = AppConfig::from_env()?;
    let symbol_configs: Vec<(InstrumentId, BarType, AppConfig)> = instrument_ids
        .iter()
        .zip(bar_types.iter())
        .map(|(&instr_id, &bar_type)| (instr_id, bar_type, base_cfg.clone()))
        .collect();

    let mut vortex = VortexStrategy::new(symbol_configs, initial_cash);

    // ─── 6. Data Loading (multi-symbol, interleaved sort) ──────────────
    println!("\nLoading historical data...");

    let candidate_roots = [
        "rust_backtest/data", // run from workspace root
        "data",               // run from rust_backtest/
    ];

    let mut grand_total_candles: i64 = 0;

    for sym_str in &symbols {
        // Find parquet files for this symbol
        let mut files: Vec<_> = Vec::new();
        let mut used_pattern = String::new();
        for root in &candidate_roots {
            let pattern = format!("{}/{sym_str}/*.parquet", root);
            files = glob(&pattern)?.filter_map(Result::ok).collect();
            if !files.is_empty() {
                used_pattern = pattern;
                break;
            }
        }
        files.sort();

        if files.is_empty() {
            eprintln!(
                "  [WARN] No Parquet data found for {sym_str}. Tried: {:?}",
                candidate_roots.map(|r| format!("{r}/{sym_str}/*.parquet"))
            );
            continue;
        }
        println!("  {} → {} file(s) via '{}'", sym_str, files.len(), used_pattern);

        // Lookup InstrumentId for this symbol
        let instr_id = *instrument_ids
            .iter()
            .find(|id| id.symbol.as_str() == sym_str.as_str())
            .expect("symbol must have been added above");

        let mut symbol_events: Vec<Data> = Vec::new();

        for file_path in &files {
            let df = LazyFrame::scan_parquet(file_path, Default::default())?.collect()?;
            println!(
                "    {:?} — {} rows",
                file_path.file_name().unwrap_or_default(),
                df.height()
            );

            let timestamps = df.column("open_time")?.i64()?;
            let opens   = df.column("open")?.f64()?;
            let highs   = df.column("high")?.f64()?;
            let lows    = df.column("low")?.f64()?;
            let closes  = df.column("close")?.f64()?;
            let volumes = df.column("volume")?.f64()?;

            // ~9 events per candle (4 quote + 4 trade + 1 bar)
            symbol_events.reserve(df.height() * 9);

            for i in 0..df.height() {
                let ts_ms = timestamps.get(i).unwrap_or(0);
                let o = opens.get(i).unwrap_or(0.0);
                let h = highs.get(i).unwrap_or(0.0);
                let l = lows.get(i).unwrap_or(0.0);
                let c = closes.get(i).unwrap_or(0.0);
                let v = volumes.get(i).unwrap_or(0.0);

                // Skip candles with zero volume / price
                if v <= 0.0 || o <= 0.0 || h <= 0.0 || l <= 0.0 || c <= 0.0 {
                    continue;
                }

                let ts_start_ns = ts_ms * 1_000_000; // ms → ns

                // OHLC tick path:  bullish: O→L→H→C   bearish: O→H→L→C
                let path = if c >= o { [o, l, h, c] } else { [o, h, l, c] };
                let half_spread = spread_bps / 10_000.0 / 2.0;

                let event_base = symbol_events.len() as i64;

                for (idx, &price) in path.iter().enumerate() {
                    // Each tick at 15-second intervals within the 60s bar
                    let ts_event = UnixNanos::from(
                        (ts_start_ns + (idx as i64 * 15_000_000_000)) as u64,
                    );
                    let bid = price * (1.0 - half_spread);
                    let ask = price * (1.0 + half_spread);

                    // QuoteTick → L1 order book for execution
                    symbol_events.push(Data::from(QuoteTick::new(
                        instr_id,
                        Price::from(&format!("{:.8}", bid)),
                        Price::from(&format!("{:.8}", ask)),
                        Quantity::from(&format!("{:.8}", v / 8.0)),
                        Quantity::from(&format!("{:.8}", v / 8.0)),
                        ts_event,
                        ts_event,
                    )));

                    // TradeTick → provides last-trade price for indicators
                    symbol_events.push(Data::from(TradeTick::new(
                        instr_id,
                        Price::from(&format!("{:.8}", price)),
                        Quantity::from(&format!("{:.8}", v / 4.0)),
                        if idx % 2 == 0 { AggressorSide::Buyer } else { AggressorSide::Seller },
                        TradeId::new(&(grand_total_candles + event_base + idx as i64).to_string()),
                        ts_event,
                        ts_event,
                    )));
                }

                // Bar at end-of-bar timestamp (Nautilus convention)
                let bar_ts = UnixNanos::from((ts_start_ns + 60_000_000_000) as u64);
                symbol_events.push(Data::from(Bar::new(
                    BarType::new(
                        instr_id,
                        BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
                        AggregationSource::External,
                    ),
                    Price::from(&format!("{:.8}", o)),
                    Price::from(&format!("{:.8}", h)),
                    Price::from(&format!("{:.8}", l)),
                    Price::from(&format!("{:.8}", c)),
                    Quantity::from(&format!("{:.8}", v)),
                    bar_ts,
                    bar_ts,
                )));

                grand_total_candles += 1;
            }
        }

        // Add this symbol's events to the engine; sort=true for inter-symbol ordering
        engine.add_data(symbol_events, None, false, true);
    }

    println!(
        "\nTotal candles loaded: {}  (~{} synthetic events)",
        grand_total_candles,
        grand_total_candles * 9,
    );

    // ─── 7. Manual Bar-Level Driver ────────────────────────────────────
    //
    // Because implementing the full Nautilus `Strategy` trait in Rust requires
    // linking against the Python extension (pyo3 live context), we drive
    // VortexStrategy manually: we iterate the engine's data bus after run(),
    // replaying every Bar event through VortexStrategy.
    //
    // Nautilus still handles realistic order matching, fees, and latency for
    // every order we would submit — but for the pure-Rust backtest we track
    // PnL inside VortexStrategy itself (same approach as the mft_engine's own
    // self-contained backtest).

    println!("\nStarting NautilusTrader Engine...");
    engine.run(None, None, None, false)?;
    println!("Engine run complete.\n");

    // ─── 7b. Replay bars through VortexStrategy ─────────────────────────────
    // Re-load all bar data and drive VortexStrategy to accumulate signals/trades.
    println!("Running VORTEX-7 signal engine over bar data...");

    // Collect all bars across all symbols, sorted by timestamp
    let mut all_bars: Vec<(UnixNanos, InstrumentId, Bar)> = Vec::new();

    for sym_str in &symbols {
        let mut files: Vec<_> = Vec::new();
        for root in &candidate_roots {
            let pattern = format!("{}/{sym_str}/*.parquet", root);
            files = glob(&pattern)?.filter_map(Result::ok).collect();
            if !files.is_empty() { break; }
        }
        files.sort();

        let instr_id = *instrument_ids
            .iter()
            .find(|id| id.symbol.as_str() == sym_str.as_str())
            .expect("symbol must have been added");

        for file_path in &files {
            let df = LazyFrame::scan_parquet(file_path, Default::default())?.collect()?;

            let timestamps = df.column("open_time")?.i64()?;
            let opens   = df.column("open")?.f64()?;
            let highs   = df.column("high")?.f64()?;
            let lows    = df.column("low")?.f64()?;
            let closes  = df.column("close")?.f64()?;
            let volumes = df.column("volume")?.f64()?;

            for i in 0..df.height() {
                let ts_ms = timestamps.get(i).unwrap_or(0);
                let o = opens.get(i).unwrap_or(0.0);
                let h = highs.get(i).unwrap_or(0.0);
                let l = lows.get(i).unwrap_or(0.0);
                let c = closes.get(i).unwrap_or(0.0);
                let v = volumes.get(i).unwrap_or(0.0);

                if v <= 0.0 || c <= 0.0 { continue; }

                let bar_ts = UnixNanos::from(((ts_ms * 1_000_000) + 60_000_000_000) as u64);
                let bar = Bar::new(
                    BarType::new(
                        instr_id,
                        BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
                        AggregationSource::External,
                    ),
                    Price::from(&format!("{:.8}", o)),
                    Price::from(&format!("{:.8}", h)),
                    Price::from(&format!("{:.8}", l)),
                    Price::from(&format!("{:.8}", c)),
                    Quantity::from(&format!("{:.8}", v)),
                    bar_ts,
                    bar_ts,
                );
                all_bars.push((bar_ts, instr_id, bar));
            }
        }
    }

    // Sort interleaved by timestamp (stable sort preserves symbol order for ties)
    all_bars.sort_by_key(|(ts, _, _)| *ts);
    println!("  Replaying {} bars through VortexStrategy...", all_bars.len());

    let mut entry_count = 0usize;
    let mut exit_count  = 0usize;

    for (_ts, instr_id, bar) in &all_bars {
        match vortex.on_bar(bar, *instr_id) {
            Some(BarAction::Enter { side, qty }) => {
                entry_count += 1;
                log::debug!(
                    "ENTRY {:?} {} @ {} qty={:.6}",
                    side,
                    instr_id.symbol,
                    bar.close,
                    qty
                );
            }
            Some(BarAction::Exit { side, qty }) => {
                exit_count += 1;
                log::debug!(
                    "EXIT  {:?} {} @ {} qty={:.6}",
                    side,
                    instr_id.symbol,
                    bar.close,
                    qty
                );
            }
            None => {}
        }
    }

    println!(
        "  Signal replay complete: {} entries, {} exits",
        entry_count, exit_count
    );

    // ─── 8. Results ─────────────────────────────────────────────────────
    let nauilus_result = engine.get_result();
    println!("\n╔══════════════════════════════════════════════╗");
    println!("║    NAUTILUS ENGINE RESULTS                   ║");
    println!("╠══════════════════════════════════════════════╣");
    println!("║ Symbols:         {:<28}║", symbols.join(", "));
    println!("║ Total Events:    {:<28}║", nauilus_result.total_events);
    println!("║ Total Orders:    {:<28}║", nauilus_result.total_orders);
    println!("║ Total Positions: {:<28}║", nauilus_result.total_positions);
    println!("╠══════════════════════════════════════════════╣");
    for (trader_id, pnls) in &nauilus_result.stats_pnls {
        println!("║ Trader: {:<37}║", trader_id);
        for (venue_id, pnl) in pnls {
            println!("║   {} PnL: {:<30.4}║", venue_id, pnl);
        }
    }
    println!("╚══════════════════════════════════════════════╝");

    // VORTEX-7 strategy-level summary
    vortex.print_summary();

    // ─── 9. Cleanup ─────────────────────────────────────────────────────
    engine.dispose();
    Ok(())
}
