/// live_main.rs — Live Trading Entry Point
///
/// Runs the strategy in paper/live trading mode against Binance Futures.
///
/// FLOW:
///   1. Load config from .env (reads BINANCE_API_KEY, BINANCE_API_SECRET, etc.)
///   2. Warm up models by fetching recent klines from REST API
///   3. Poll new klines at interval cadence
///   4. On signal: place MARKET order via Binance Futures REST
///   5. Monitor position every tick against exit conditions
///   6. On exit signal: place opposite MARKET order to close
///
/// NOTE: Polling interval cadence is used (not WebSocket) for simplicity.
///       For production: consider WebSocket kline stream to reduce latency.

mod config;
mod data;
mod models;
mod risk;
mod strategy;
mod backtest;
mod metrics;
mod live;

use anyhow::Result;
use tokio::time::{sleep, Duration};
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;

use config::AppConfig;
use data::BinanceDataClient;
use live::LiveOrderClient;
use risk::position_size;
use strategy::{ExitReason, StrategyEngine};

/// Interval cadence to sleep between polls (in seconds).
/// For 1m bars: poll every 60s. We poll slightly earlier to fetch fresh bar.
fn poll_seconds(interval: &str) -> u64 {
    match interval {
        "1m"  => 58,
        "3m"  => 178,
        "5m"  => 298,
        "15m" => 898,
        "30m" => 1798,
        _     => 58,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    info!("╔══════════════════════════════════════════════╗");
    info!("║       MFT ENGINE  —  LIVE TRADING MODE      ║");
    info!("║                                              ║");
    info!("║  ⚠  TESTNET active — no real funds at risk  ║");
    info!("╚══════════════════════════════════════════════╝");

    let cfg = AppConfig::from_env()?;
    if !cfg.use_testnet {
        warn!("⚠️  LIVE MODE — REAL MONEY — ensure all parameters are correct!");
    }

    let symbol   = cfg.backtest_symbol.clone();
    let interval = cfg.kline_interval.clone();
    let rest_url = cfg.rest_url.clone();

    let data_client = BinanceDataClient::new(&rest_url);
    let order_client = LiveOrderClient::new(
        &cfg.api_key,
        &cfg.api_secret,
        &rest_url,
    );

    // ── Warm up: fetch recent bars to fill model buffers ─────────────────
    let warmup_bars = (cfg.ou_window + 50).max(200) as u64;
    info!("Warming up with {} bars of {} {}...", warmup_bars, interval, symbol);
    let warmup_klines = data_client.fetch_klines(&symbol, &interval, warmup_bars).await?;

    info!("Setting leverage {}x on {}...", cfg.max_leverage, symbol);
    order_client.set_leverage(&symbol, cfg.max_leverage).await?;

    // ── Initialise strategy engine and warm up ────────────────────────────
    let mut engine = StrategyEngine::new(cfg.clone());

    // Feed warmup bars WITHOUT placing orders
    for (i, bar) in warmup_klines.iter().enumerate() {
        if i == 0 { continue; }
        let prev_close = warmup_klines[i - 1].close;
        let log_return = if prev_close > 0.0 { (bar.close / prev_close).ln() } else { 0.0 };
        let tick = bar.to_tick();
        // Call on_bar but discard signals during warmup
        let _ = engine.on_bar(bar.close, log_return, &tick);
    }
    info!("Warmup complete.  Last price: {:.2}", warmup_klines.last().map_or(0.0, |k| k.close));

    // ── Live polling loop ─────────────────────────────────────────────────
    let poll_secs = poll_seconds(&interval);
    info!("Entering live loop — polling every {}s...", poll_secs);

    loop {
        sleep(Duration::from_secs(poll_secs)).await;

        // Fetch 2 most recent bars to get a closed bar
        let recent = match data_client.fetch_klines(&symbol, &interval, 3).await {
            Ok(k) => k,
            Err(e) => {
                error!("Failed to fetch klines: {e}");
                continue;
            }
        };

        if recent.len() < 2 {
            warn!("Not enough bars returned");
            continue;
        }

        // Use the SECOND-to-last bar (fully closed)
        let bar = &recent[recent.len() - 2];
        let prev = &recent[recent.len() - 3.min(recent.len() - 1)];

        let log_return = if prev.close > 0.0 {
            (bar.close / prev.close).ln()
        } else {
            0.0
        };

        let tick = bar.to_tick();
        let current_price = bar.close;

        // ── Strategy evaluation ───────────────────────────────────────────
        if let Some(signal) = engine.on_bar(current_price, log_return, &tick) {
            let side = if signal.direction == 1 { "BUY" } else { "SELL" };
            let qty  = position_size(
                engine.equity,
                signal.size_frac,
                cfg.max_leverage,
                current_price,
            );

            if qty < 0.001 {
                warn!("Computed quantity {qty:.4} below minimum — skipping order");
                continue;
            }

            info!(
                "▶ SIGNAL: {} {} qty={:.4} Z={:.3} EV={:.5}",
                side, symbol, qty, signal.z_score, signal.ev
            );

            match order_client.market_order(&symbol, side, qty).await {
                Ok(resp) => {
                    info!("✔ Order placed: {:?}", resp);
                    engine.open_position(signal);
                }
                Err(e) => {
                    error!("✘ Order failed: {e}");
                }
            }
        }

        // ── Check exit for open position ──────────────────────────────────
        if let Some(ref pos) = engine.position {
            let bars_held = pos.bars_held;
            let z = engine.ou.z_score(current_price).unwrap_or(0.0);
            if let Some(reason) = engine.check_exit(current_price, z, bars_held) {
                let close_side = if pos.signal.direction == 1 { "SELL" } else { "BUY" };
                let qty = position_size(
                    engine.equity,
                    pos.signal.size_frac,
                    cfg.max_leverage,
                    pos.signal.entry_price,
                );

                info!("◀ EXIT ({:?}): {} {} qty={:.4}", reason, close_side, symbol, qty);
                match order_client.market_order(&symbol, close_side, qty).await {
                    Ok(resp) => {
                        info!("✔ Close order: {:?}", resp);
                        engine.close_position(current_price, reason);
                    }
                    Err(e) => {
                        error!("✘ Close order failed: {e}");
                    }
                }
            }
        }

        info!(
            "Equity: ${:.2}  Open pos: {}",
            engine.equity,
            if engine.position.is_some() { "YES" } else { "NO" }
        );
    }
}
