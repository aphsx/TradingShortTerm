/// main.rs — Backtesting Entry Point
///
/// Runs the MFT Engine backtest:
///   1. Load config from .env
///   2. Fetch kline data from Binance Futures (testnet or mainnet)
///   3. Run event-driven backtest loop
///   4. Print performance metrics

mod config;
mod data;
mod models;
mod risk;
mod strategy;
mod backtest;
mod metrics;

use anyhow::Result;
use tracing::info;
use tracing_subscriber::{fmt, EnvFilter};

use backtest::{BacktestConfig, run_backtest, print_trade_log};
use config::AppConfig;
use data::BinanceDataClient;

#[tokio::main]
async fn main() -> Result<()> {
    // ── Logging ──────────────────────────────────────────────────────────
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    info!("╔══════════════════════════════════════════════╗");
    info!("║      MFT ENGINE  —  BACKTEST MODE           ║");
    info!("║  GARCH(1,1) + OU Process + OFI/VPIN        ║");
    info!("╚══════════════════════════════════════════════╝");

    // ── Config ───────────────────────────────────────────────────────────
    let cfg = AppConfig::from_env()?;
    info!(
        "Config: symbol={} interval={} limit={} testnet={}",
        cfg.backtest_symbol, cfg.kline_interval,
        cfg.backtest_limit, cfg.use_testnet
    );
    info!(
        "GARCH: ω={:.2e} α={:.2} β={:.2}",
        cfg.garch_omega, cfg.garch_alpha, cfg.garch_beta
    );
    info!(
        "OU:    entry_z={:.1} exit_z={:.1} window={}",
        cfg.ou_entry_z, cfg.ou_exit_z, cfg.ou_window
    );
    info!(
        "Fees:  taker={:.4}% slippage={:.4}%",
        cfg.taker_fee * 100.0, cfg.slippage * 100.0
    );

    // ── Fetch Data ───────────────────────────────────────────────────────
    let data_client = BinanceDataClient::new(&cfg.rest_url);
    let symbol   = cfg.backtest_symbol.clone();
    let interval = cfg.kline_interval.clone();
    let limit    = cfg.backtest_limit;

    info!("Fetching {} {} klines from {}...", limit, interval, &cfg.rest_url);
    let klines = data_client
        .fetch_klines(&symbol, &interval, limit)
        .await?;

    if klines.is_empty() {
        anyhow::bail!("No kline data received.  Check symbol, interval, and connectivity.");
    }
    info!("Loaded {} bars  ({} → {})",
        klines.len(),
        klines.first().map(|k| k.open_time).unwrap_or(0),
        klines.last().map(|k| k.open_time).unwrap_or(0)
    );

    // ── Bars per year (for Sharpe annualisation) ─────────────────────────
    let bars_per_year = match interval.as_str() {
        "1m"  => 525_600.0,
        "3m"  => 175_200.0,
        "5m"  => 105_120.0,
        "15m" => 35_040.0,
        "30m" => 17_520.0,
        "1h"  => 8_760.0,
        "4h"  => 2_190.0,
        "1d"  => 365.0,
        _     => 525_600.0,
    };

    // ── Run Backtest ──────────────────────────────────────────────────────
    let bt_cfg = BacktestConfig { verbose: true, bars_per_year };
    let report = run_backtest(&klines, cfg, bt_cfg);

    // ── Print Report ──────────────────────────────────────────────────────
    println!("\n{}", report);

    Ok(())
}
