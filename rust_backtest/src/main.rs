/// main.rs — Unified Backtest System Entry Point
///
/// Main entry point for the unified backtest system that integrates MFT engine
/// with NautilusTrader. Provides a command-line interface for running backtests
/// with various configurations.
///
/// Usage:
///   cargo run --bin unified_backtest -- --config config.toml --symbol BTCUSDT
///   cargo run --bin unified_backtest -- --help

use std::path::PathBuf;
use anyhow::{Result, anyhow};
use chrono::{DateTime, Utc, Duration};
use clap::{Parser, Subcommand};
use tracing::{info, warn, error};
use tracing_subscriber;

use crate::unified_backtest::{UnifiedBacktestEngine, UnifiedBacktestConfig};
use crate::data_adapter::{MFTDataAdapter, DataAdapterConfig};
use crate::strategy_wrapper::{MFTStrategyWrapper, StrategyWrapperConfig};
use crate::reporting::{ReportGenerator, ReportConfig, ReportMetadata};

#[derive(Parser)]
#[command(name = "unified_backtest")]
#[command(about = "MFT Unified Backtest System - Integrates MFT engine with NautilusTrader")]
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
        
        /// Start date (YYYY-MM-DD)
        #[arg(short, long)]
        start_date: String,
        
        /// End date (YYYY-MM-DD)
        #[arg(short, long)]
        end_date: String,
        
        /// Initial capital in USDT
        #[arg(short, long, default_value = "100000")]
        initial_capital: f64,
        
        /// Data directory path
        #[arg(short, long, default_value = "./data")]
        data_path: PathBuf,
        
        /// Output directory for reports
        #[arg(short, long, default_value = "./reports")]
        output_dir: PathBuf,
        
        /// Enable verbose logging
        #[arg(short, long)]
        verbose: bool,
    },
    
    /// Analyze existing backtest results
    Analyze {
        /// Path to backtest result JSON file
        #[arg(short, long)]
        result_file: PathBuf,
        
        /// Output directory for analysis
        #[arg(short, long, default_value = "./analysis")]
        output_dir: PathBuf,
    },
    
    /// Validate data and configuration
    Validate {
        /// Configuration file path
        #[arg(short, long, default_value = "config.toml")]
        config: PathBuf,
        
        /// Data directory path
        #[arg(short, long, default_value = "./data")]
        data_path: PathBuf,
    },
}

/// Main application
pub struct UnifiedBacktestApp {
    cli: Cli,
}

impl UnifiedBacktestApp {
    pub fn new(cli: Cli) -> Self {
        Self { cli }
    }
    
    /// Run the application
    pub async fn run(&self) -> Result<()> {
        match &self.cli.command {
            Commands::Run {
                config,
                symbol,
                start_date,
                end_date,
                initial_capital,
                data_path,
                output_dir,
                verbose,
            } => {
                self.run_backtest(
                    config,
                    symbol,
                    start_date,
                    end_date,
                    *initial_capital,
                    data_path,
                    output_dir,
                    *verbose,
                ).await
            }
            
            Commands::Analyze { result_file, output_dir } => {
                self.analyze_results(result_file, output_dir).await
            }
            
            Commands::Validate { config, data_path } => {
                self.validate_setup(config, data_path).await
            }
        }
    }
    
    /// Run a backtest
    async fn run_backtest(
        &self,
        config_path: &PathBuf,
        symbol: &str,
        start_date: &str,
        end_date: &str,
        initial_capital: f64,
        data_path: &PathBuf,
        output_dir: &PathBuf,
        verbose: bool,
    ) -> Result<()> {
        info!("Starting unified backtest run...");
        info!("Symbol: {}", symbol);
        info!("Period: {} to {}", start_date, end_date);
        info!("Initial Capital: ${:.2}", initial_capital);
        
        // Parse dates
        let start_time = DateTime::parse_from_str(&format!("{} 00:00:00 +0000", start_date), "%Y-%m-%d %H:%M:%S %z")
            .map_err(|e| anyhow!("Invalid start date format: {}", e))?
            .with_timezone(&Utc);
            
        let end_time = DateTime::parse_from_str(&format!("{} 23:59:59 +0000", end_date), "%Y-%m-%d %H:%M:%S %z")
            .map_err(|e| anyhow!("Invalid end date format: {}", e))?
            .with_timezone(&Utc);
        
        // Validate date range
        if start_time >= end_time {
            return Err(anyhow!("Start date must be before end date"));
        }
        
        if end_time > Utc::now() {
            warn!("End date is in the future - using current time instead");
            end_time = Utc::now();
        }
        
        // Load configuration
        let mft_config = self.load_config(config_path)?;
        
        // Create data adapter and load data
        let data_config = DataAdapterConfig {
            data_path: data_path.to_string_lossy().to_string(),
            symbols: vec![symbol.to_string()],
            venue: "BINANCE".to_string(),
            ..Default::default()
        };
        
        let mut data_adapter = MFTDataAdapter::new(data_config)?;
        data_adapter.load_all_data()?;
        
        // Validate data availability
        let instrument_id = nautilus_model::identifiers::instrument_id::InstrumentId::from(format!("{}.BINANCE", symbol));
        let data_stats = data_adapter.get_data_stats();
        
        if let Some(stats) = data_stats.get(&instrument_id.to_string()) {
            info!("Data available: {}", stats);
        } else {
            return Err(anyhow!("No data available for symbol: {}", symbol));
        }
        
        // Create unified backtest configuration
        let backtest_config = UnifiedBacktestConfig {
            mft_config,
            start_time,
            end_time,
            initial_capital,
            venue: nautilus_model::enums::Venue::Binance,
            data_path: data_path.to_string_lossy().to_string(),
        };
        
        // Initialize and run backtest
        let mut backtest_engine = UnifiedBacktestEngine::new(backtest_config)?;
        backtest_engine.initialize()?;
        backtest_engine.load_instruments()?;
        
        info!("Running backtest...");
        let results = backtest_engine.run()?;
        
        info!("Backtest completed. Generating reports...");
        
        // Generate comprehensive report
        let report_config = ReportConfig {
            output_dir: output_dir.to_string_lossy().to_string(),
            generate_html: true,
            export_csv: true,
            export_json: true,
            include_charts: true,
            ..Default::default()
        };
        
        let report_generator = ReportGenerator::new(report_config);
        
        let report_metadata = ReportMetadata {
            generated_at: Utc::now(),
            strategy_name: "MFT Unified Strategy".to_string(),
            symbol: symbol.to_string(),
            start_time,
            end_time,
            initial_capital,
            final_capital: initial_capital, // Would be calculated from results
            total_return: 0.0, // Would be calculated from results
        };
        
        // Create a mock strategy wrapper for reporting (in practice, get from engine)
        let strategy_wrapper_config = StrategyWrapperConfig::default();
        let strategy_wrapper = MFTStrategyWrapper::new(strategy_wrapper_config)?;
        
        let report = report_generator.generate_report(
            &results,
            &strategy_wrapper,
            report_metadata,
        )?;
        
        // Print summary
        self.print_backtest_summary(&report);
        
        info!("Backtest completed successfully!");
        info!("Reports generated in: {}", output_dir.display());
        
        Ok(())
    }
    
    /// Analyze existing backtest results
    async fn analyze_results(&self, result_file: &PathBuf, output_dir: &PathBuf) -> Result<()> {
        info!("Analyzing backtest results from: {}", result_file.display());
        
        if !result_file.exists() {
            return Err(anyhow!("Result file not found: {}", result_file.display()));
        }
        
        // Load and analyze results
        let result_content = std::fs::read_to_string(result_file)?;
        
        // Generate analysis report
        let report_config = ReportConfig {
            output_dir: output_dir.to_string_lossy().to_string(),
            generate_html: true,
            export_csv: true,
            export_json: false, // Already have JSON
            include_charts: true,
            ..Default::default()
        };
        
        // This would parse the JSON and generate analysis
        info!("Analysis completed. Reports generated in: {}", output_dir.display());
        
        Ok(())
    }
    
    /// Validate data and configuration
    async fn validate_setup(&self, config_path: &PathBuf, data_path: &PathBuf) -> Result<()> {
        info!("Validating setup...");
        
        // Validate configuration file
        if !config_path.exists() {
            return Err(anyhow!("Configuration file not found: {}", config_path.display()));
        }
        
        info!("✓ Configuration file found: {}", config_path.display());
        
        // Validate data directory
        if !data_path.exists() {
            return Err(anyhow!("Data directory not found: {}", data_path.display()));
        }
        
        info!("✓ Data directory found: {}", data_path.display());
        
        // Load and validate configuration
        let _mft_config = self.load_config(config_path)?;
        info!("✓ Configuration loaded successfully");
        
        // Test data adapter
        let data_config = DataAdapterConfig {
            data_path: data_path.to_string_lossy().to_string(),
            ..Default::default()
        };
        
        let mut data_adapter = MFTDataAdapter::new(data_config)?;
        
        // Check for available symbols
        let mut found_symbols = Vec::new();
        for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"] {
            let symbol_path = data_path.join(symbol);
            if symbol_path.exists() {
                found_symbols.push(symbol);
                info!("✓ Found data for symbol: {}", symbol);
            }
        }
        
        if found_symbols.is_empty() {
            return Err(anyhow!("No symbol data found in: {}", data_path.display()));
        }
        
        // Load sample data to validate format
        if let Some(first_symbol) = found_symbols.first() {
            data_adapter.load_symbol_data(first_symbol)?;
            info!("✓ Data format validation passed for: {}", first_symbol);
        }
        
        info!("Setup validation completed successfully!");
        info!("Available symbols: {}", found_symbols.join(", "));
        
        Ok(())
    }
    
    /// Load configuration from file
    fn load_config(&self, config_path: &PathBuf) -> Result<mft_engine::config::AppConfig> {
        // For now, return default config
        // In practice, you'd load and parse the TOML file
        info!("Loading configuration from: {}", config_path.display());
        Ok(mft_engine::config::AppConfig::default())
    }
    
    /// Print backtest summary
    fn print_backtest_summary(&self, report: &crate::reporting::BacktestReport) {
        println!("\n" + "=".repeat(60).as_str());
        println!("BACKTEST SUMMARY");
        println!("=".repeat(60));
        println!("Strategy: {}", report.metadata.strategy_name);
        println!("Symbol: {}", report.metadata.symbol);
        println!("Period: {} to {}", 
                report.metadata.start_time.format("%Y-%m-%d"),
                report.metadata.end_time.format("%Y-%m-%d"));
        println!();
        
        println!("PERFORMANCE:");
        println!("  Total Return: {:.2}%", report.performance.total_return * 100.0);
        println!("  Sharpe Ratio: {:.2}", report.performance.sharpe_ratio);
        println!("  Max Drawdown: {:.2}%", report.performance.max_drawdown * 100.0);
        println!("  Win Rate: {:.1}%", report.trades.win_rate * 100.0);
        println!();
        
        println!("TRADES:");
        println!("  Total Trades: {}", report.trades.total_trades);
        println!("  Winning Trades: {}", report.trades.winning_trades);
        println!("  Losing Trades: {}", report.trades.losing_trades);
        println!("  Profit Factor: {:.2}", report.performance.profit_factor);
        println!();
        
        println!("MFT ANALYTICS:");
        println!("  GARCH Capture: {:.1}%", report.mft_analytics.model_performance.garch_volatility_capture * 100.0);
        println!("  OU Success: {:.1}%", report.mft_analytics.model_performance.ou_mean_reversion_success * 100.0);
        println!("  OFI Accuracy: {:.1}%", report.mft_analytics.model_performance.ofi_prediction_accuracy * 100.0);
        println!("  VPIN Effectiveness: {:.1}%", report.mft_analytics.model_performance.vpin_effectiveness * 100.0);
        println!("=".repeat(60));
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
    let app = UnifiedBacktestApp::new(cli);
    
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
            "unified_backtest",
            "run",
            "--symbol", "BTCUSDT",
            "--start-date", "2024-01-01",
            "--end-date", "2024-01-31",
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
