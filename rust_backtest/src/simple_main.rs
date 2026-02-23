/// main.rs — Simple Backtest Runner
///
/// A simplified backtest runner that works with the MFT engine
/// without NautilusTrader dependencies.

use std::path::PathBuf;
use anyhow::{Result, anyhow};
use chrono::{Utc, TimeZone};
use clap::{Parser, Subcommand};
use tracing::{info, error};
use tracing_subscriber;

use rust_backtest::simple_backtest::{SimpleBacktestEngine, SimpleBacktestConfig, generate_text_report};
use mft_engine::data::Kline;
use polars::prelude::*;

#[derive(Parser)]
#[command(name = "simple_backtest")]
#[command(about = "MFT Simple Backtest System - Works with MFT engine directly")]
#[command(version)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Run a backtest
    Run {
        /// Configuration file path
        #[arg(short, long, default_value = "config.toml")]
        config: PathBuf,
        
        /// Trading symbol (e.g., BTCUSDT)
        #[arg(short, long)]
        symbol: String,
        
        /// Data file path (parquet)
        #[arg(short, long)]
        data_file: PathBuf,
        
        /// Initial capital in USDT
        #[arg(short, long, default_value = "100000")]
        initial_capital: f64,
        
        /// Output directory for reports
        #[arg(short, long, default_value = "./reports")]
        output_dir: PathBuf,
        
        /// Enable verbose logging
        #[arg(short, long)]
        verbose: bool,
    },
}

/// Main application
pub struct SimpleBacktestApp {
    cli: Cli,
}

impl SimpleBacktestApp {
    pub fn new(cli: Cli) -> Self {
        Self { cli }
    }
    
    /// Run the application
    pub async fn run(&self) -> Result<()> {
        match &self.cli.command {
            Commands::Run {
                config,
                symbol,
                data_file,
                initial_capital,
                output_dir,
                verbose,
            } => {
                self.run_backtest(
                    config,
                    symbol,
                    data_file,
                    *initial_capital,
                    output_dir,
                    *verbose,
                ).await
            }
        }
    }
    
    /// Run a backtest
    async fn run_backtest(
        &self,
        _config_path: &PathBuf,
        symbol: &str,
        data_file: &PathBuf,
        initial_capital: f64,
        output_dir: &PathBuf,
        _verbose: bool,
    ) -> Result<()> {
        info!("Starting simple backtest run...");
        info!("Symbol: {}", symbol);
        info!("Data file: {}", data_file.display());
        info!("Initial Capital: ${:.2}", initial_capital);
        
        // Validate data file exists
        if !data_file.exists() {
            return Err(anyhow!("Data file not found: {}", data_file.display()));
        }
        
        // Load data from parquet file
        let klines = self.load_parquet_data(data_file)?;
        info!("Loaded {} klines from data file", klines.len());
        
        if klines.is_empty() {
            return Err(anyhow!("No data found in file"));
        }
        
        // Create backtest configuration
        let backtest_config = SimpleBacktestConfig {
            mft_config: mft_engine::config::AppConfig::from_env().unwrap_or_else(|_| {
                // Fallback config
                mft_engine::config::AppConfig {
                    api_key: "".to_string(),
                    api_secret: "".to_string(),
                    use_testnet: true,
                    rest_url: "".to_string(),
                    ws_url: "".to_string(),
                    trading_pairs: vec!["BTCUSDT".to_string()],
                    initial_capital: 100_000.0,
                    risk_per_trade: 0.02,
                    max_leverage: 10,
                    maker_fee: 0.0002,
                    taker_fee: 0.0005,
                    slippage: 0.0003,
                    garch_omega: 0.00001,
                    garch_alpha: 0.1,
                    garch_beta: 0.85,
                    ou_entry_z: 2.0,
                    ou_exit_z: 0.5,
                    ou_window: 100,
                    vpin_bucket_size: 1000,
                    vpin_n_buckets: 50,
                    vpin_threshold: 0.025,
                    min_ev: 0.001,
                    min_p_win: 0.55,
                    stop_loss_frac: 0.02,
                    exit_prob_threshold: 0.3,
                    max_hold_bars: 1000,
                    kline_interval: "1m".to_string(),
                    backtest_symbol: "BTCUSDT".to_string(),
                    backtest_limit: 10000,
                }
            }),
            initial_capital,
            commission_rate: 0.001,
            slippage_bps: 5.0,
        };
        
        // Create and run backtest engine
        let mut engine = SimpleBacktestEngine::new(backtest_config)?;
        
        info!("Running backtest...");
        let results = engine.run(&klines)?;
        
        // Generate and save report
        let report = generate_text_report(&results);
        
        // Create output directory
        std::fs::create_dir_all(output_dir)?;
        
        // Save report to file
        let timestamp = Utc::now().format("%Y%m%d_%H%M%S");
        let timestamp_str = timestamp.to_string();
        let report_file = output_dir.join(format!("backtest_report_{}_{}.txt", symbol, timestamp_str));
        
        std::fs::write(&report_file, report)?;
        info!("Report saved to: {}", report_file.display());
        
        // Also save equity curve as CSV
        self.save_equity_curve_csv(&results, output_dir, symbol, &timestamp_str)?;
        
        // Print summary
        self.print_summary(&results);
        
        info!("Backtest completed successfully!");
        
        Ok(())
    }
    
    /// Load data from parquet file
    fn load_parquet_data(&self, data_file: &PathBuf) -> Result<Vec<Kline>> {
        info!("Reading parquet file: {}", data_file.display());
        
        let df = polars::prelude::LazyFrame::scan_parquet(data_file, Default::default())?
            .collect()?;
        
        // Convert DataFrame to Kline objects
        let mut klines = Vec::new();
        
        // Get column vectors
        let open_times = df.column("open_time")?.i64()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;
        
        for i in 0..df.height() {
            let open_time = open_times.get(i).unwrap();
            let open = opens.get(i).unwrap();
            let high = highs.get(i).unwrap();
            let low = lows.get(i).unwrap();
            let close = closes.get(i).unwrap();
            let volume = volumes.get(i).unwrap();
            
            let kline = Kline {
                open_time,
                open,
                high,
                low,
                close,
                volume,
                close_time: open_time + 60_000, // 1 minute later
                quote_vol: volume * close, // Approximate
                n_trades: 0,
                taker_buy_base_vol: volume * 0.5, // Estimate
            };
            
            klines.push(kline);
        }
        
        // Sort by timestamp
        klines.sort_by_key(|k| k.open_time);
        
        Ok(klines)
    }
    
    /// Save equity curve as CSV
    fn save_equity_curve_csv(
        &self,
        results: &rust_backtest::simple_backtest::BacktestResults,
        output_dir: &PathBuf,
        symbol: &str,
        timestamp: &str,
    ) -> Result<()> {
        let equity_file = output_dir.join(format!("equity_curve_{}_{}.csv", symbol, timestamp));
        
        let mut csv_content = "timestamp,equity,returns,drawdown\n".to_string();
        
        for point in &results.equity_curve {
            csv_content.push_str(&format!(
                "{},{:.6},{:.6},{:.6}\n",
                point.timestamp.format("%Y-%m-%d %H:%M:%S"),
                point.equity,
                point.returns,
                point.drawdown
            ));
        }
        
        std::fs::write(&equity_file, csv_content)?;
        info!("Equity curve saved to: {}", equity_file.display());
        
        Ok(())
    }
    
    /// Print summary to console
    fn print_summary(&self, results: &rust_backtest::simple_backtest::BacktestResults) {
        println!("\n{}", "=".repeat(60));
        println!("MFT SIMPLE BACKTEST SUMMARY");
        println!("{}", "=".repeat(60));
        println!("Initial Capital: ${:.2}", 100_000.0); // Would be from config
        println!("Final Capital: ${:.2}", results.final_capital);
        println!("Total Return: {:.2}%", results.total_return * 100.0);
        println!();
        
        println!("PERFORMANCE:");
        println!("  Sharpe Ratio: {:.2}", results.sharpe_ratio);
        println!("  Max Drawdown: {:.2}%", results.max_drawdown * 100.0);
        println!("  Win Rate: {:.1}%", results.performance_metrics.win_rate * 100.0);
        println!("  Profit Factor: {:.2}", results.performance_metrics.profit_factor);
        println!();
        
        println!("TRADES:");
        println!("  Total Trades: {}", results.performance_metrics.n_trades);
        println!("  Sharpe Ratio: {:.2}", results.performance_metrics.sharpe);
        println!("  Sortino Ratio: {:.2}", results.performance_metrics.sortino);
        println!("{}", "=".repeat(60));
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .with_target(false)
        .init();
    
    // Parse command line arguments
    let cli = Cli::parse();
    
    // Create and run application
    let app = SimpleBacktestApp::new(cli);
    
    if let Err(e) = app.run().await {
        error!("Application error: {}", e);
        std::process::exit(1);
    }
    
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::Parser;

    #[test]
    fn test_cli_parsing() {
        let args = vec![
            "simple_backtest",
            "run",
            "--symbol", "BTCUSDT",
            "--data-file", "data/BTCUSDT/BTCUSDT_20240101.parquet",
            "--initial-capital", "100000",
        ];
        
        let cli = Cli::try_parse_from(args).unwrap();
        
        if let Commands::Run { symbol, initial_capital, .. } = cli.command {
            assert_eq!(symbol, "BTCUSDT");
            assert_eq!(initial_capital, 100000.0);
        } else {
            panic!("Expected Run command");
        }
    }
}
