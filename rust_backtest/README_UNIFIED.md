# MFT Unified Backtest System

A comprehensive backtesting system that integrates the MFT (Multi-Factor Trading) engine with NautilusTrader for professional-grade algorithmic trading strategy validation.

## Architecture

The unified backtest system combines the power of two specialized components:

### MFT Engine
- **GARCH(1,1)** volatility modeling for regime detection
- **Ornstein-Uhlenbeck** process for mean reversion signals
- **OFI/VPIN** flow analysis for informed trading detection
- **Expected Value** filter with Kelly criterion sizing

### NautilusTrader Integration
- **Event-driven backtesting** with realistic market simulation
- **Professional order matching** with configurable fill models
- **Comprehensive risk management** and portfolio tracking
- **Production-ready architecture** for seamless live deployment

## Features

- **Unified Engine**: Uses the same engine for backtesting and live trading
- **High-Fidelity Simulation**: Realistic market microstructure modeling
- **Comprehensive Analytics**: Detailed performance metrics and MFT-specific analytics
- **Multiple Output Formats**: JSON, CSV, and HTML reports with visualizations
- **CLI Interface**: Easy-to-use command-line interface for batch processing
- **Data Validation**: Built-in data integrity checks and format validation

## Quick Start

### Installation

```bash
# Build the unified backtest system
cargo build --release --bin unified_backtest
```

### Running a Backtest

```bash
# Basic backtest run
cargo run --bin unified_backtest -- run \
    --symbol BTCUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --initial-capital 100000

# With custom configuration
cargo run --bin unified_backtest -- run \
    --config config.toml \
    --symbol ETHUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-03-31 \
    --data-path ./data \
    --output-dir ./reports \
    --verbose
```

### Validation

```bash
# Validate setup and data
cargo run --bin unified_backtest -- validate \
    --config config.toml \
    --data-path ./data
```

## Configuration

### Basic Configuration

The system uses TOML configuration files. Here's an example:

```toml
[mft_engine]
# GARCH parameters
garch_omega = 0.00001
garch_alpha = 0.1
garch_beta = 0.85

# OU process parameters
ou_speed = 0.5
ou_mean = 0.0
ou_volatility = 0.02

# OFI/VPIN parameters
ofi_window = 100
vpin_window = 50
vpin_threshold = 0.025

# Risk management
max_position_size = 0.95
stop_loss_pct = 0.02
take_profit_pct = 0.04

[backtest]
venue = "BINANCE"
initial_capital = 100000.0
leverage = 10.0
commission_rate = 0.001
```

### Data Requirements

The system expects parquet files organized by symbol:

```
data/
├── BTCUSDT/
│   ├── BTCUSDT_20240101.parquet
│   ├── BTCUSDT_20240102.parquet
│   └── ...
├── ETHUSDT/
│   ├── ETHUSDT_20240101.parquet
│   └── ...
└── SOLUSDT/
    └── ...
```

Each parquet file should contain:
- `open_time`: Timestamp (datetime)
- `open`: Opening price (float)
- `high`: Highest price (float)
- `low`: Lowest price (float)
- `close`: Closing price (float)
- `volume`: Trading volume (float)

## Reports

The system generates comprehensive reports in multiple formats:

### Performance Metrics
- Total return and annualized return
- Sharpe ratio and Sortino ratio
- Maximum drawdown and recovery factor
- Win rate and profit factor

### MFT-Specific Analytics
- Signal quality metrics (Z-score distribution, accuracy)
- Model performance (GARCH capture, OU success rate)
- Flow analysis (OFI correlation, VPIN effectiveness)
- Regime analysis (volatility periods, trending/ranging)

### Risk Metrics
- Value at Risk (VaR) and Conditional VaR
- Beta and Alpha calculations
- Information ratio and tail ratio
- Kelly criterion optimal sizing

## Usage Examples

### Example 1: Basic BTCUSDT Backtest

```bash
cargo run --bin unified_backtest -- run \
    --symbol BTCUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --initial-capital 50000
```

### Example 2: Multi-Strategy Comparison

```bash
# Run with different configurations
for config in conservative.toml aggressive.toml balanced.toml; do
    cargo run --bin unified_backtest -- run \
        --config $config \
        --symbol BTCUSDT \
        --start-date 2024-01-01 \
        --end-date 2024-06-30 \
        --output-dir ./reports/$(basename $config .toml)
done
```

### Example 3: Batch Processing

```bash
#!/bin/bash
symbols=("BTCUSDT" "ETHUSDT" "SOLUSDT")
start_date="2024-01-01"
end_date="2024-03-31"

for symbol in "${symbols[@]}"; do
    echo "Processing $symbol..."
    cargo run --bin unified_backtest -- run \
        --symbol $symbol \
        --start-date $start_date \
        --end-date $end_date \
        --output-dir ./reports/$symbol \
        --verbose
done
```

## Architecture Details

### Data Flow

```
Parquet Files → MFTDataAdapter → NautilusTrader DataEngine
     ↓
MFT Strategy Engine ← Event Processing ← Market Data
     ↓
Trade Signals → Order Management → Execution Simulation
     ↓
Performance Tracking → Report Generation
```

### Key Components

1. **MFTDataAdapter**: Converts parquet data to NautilusTrader format
2. **MFTStrategyWrapper**: Integrates MFT engine with NautilusTrader framework
3. **UnifiedBacktestEngine**: Orchestrates the entire backtesting process
4. **ReportGenerator**: Creates comprehensive analysis reports

### Integration Points

- **Market Data**: Seamless conversion between MFT Kline format and NautilusTrader market data
- **Order Management**: Translation of MFT signals to NautilusTrader orders
- **Risk Management**: Unified risk checks across both systems
- **Performance Tracking**: Combined metrics from both engines

## Advanced Features

### Custom Strategy Development

```rust
use rust_backtest::prelude::*;

let mut strategy = MFTStrategyWrapper::new(config)?;
strategy.set_instrument(instrument_id);
strategy.set_execution_client(execution_client);

// Process market data
strategy.on_bar(bar)?;
strategy.on_quote_tick(quote)?;
```

### Custom Reporting

```rust
let report_config = ReportConfig {
    include_charts: true,
    generate_html: true,
    export_csv: true,
    output_dir: "./custom_reports".to_string(),
};

let generator = ReportGenerator::new(report_config);
let report = generator.generate_report(&results, &strategy, metadata)?;
```

## Troubleshooting

### Common Issues

1. **Data Loading Errors**
   ```bash
   # Validate data format
   cargo run --bin unified_backtest -- validate --data-path ./data
   ```

2. **Configuration Errors**
   ```bash
   # Check configuration syntax
   cargo run --bin unified_backtest -- validate --config config.toml
   ```

3. **Memory Issues**
   - Reduce data range for initial testing
   - Use `--release` build for better performance
   - Consider increasing system RAM for large datasets

### Performance Optimization

- Use `cargo build --release` for production runs
- Enable parallel processing for large datasets
- Consider data chunking for very long backtest periods

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions and support:
- Check the documentation in the `docs/` directory
- Review the examples in the `examples/` directory
- Open an issue on the project repository
