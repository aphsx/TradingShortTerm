# MFT Simple Backtest System

A simplified backtest implementation that works with the MFT engine without the complexity of NautilusTrader integration. This provides a working backtest system that can be easily extended.

## Features

- **Direct MFT Engine Integration**: Uses the same engine as your trading bot
- **Parquet Data Support**: Reads historical market data from parquet files
- **Comprehensive Reporting**: Generates detailed performance reports
- **CLI Interface**: Easy-to-use command-line interface
- **Risk Management**: Built-in position sizing and risk controls

## Quick Start

### Build

```bash
cargo build --bin simple_backtest --release
```

### Run a Backtest

```bash
# Basic usage
./target/release/simple_backtest.exe run \
    --symbol BTCUSDT \
    --data-file data/BTCUSDT/BTCUSDT_20240101.parquet \
    --initial-capital 100000 \
    --output-dir ./reports

# With verbose logging
./target/release/simple_backtest.exe run \
    --symbol BTCUSDT \
    --data-file data/BTCUSDT/BTCUSDT_20240101.parquet \
    --initial-capital 100000 \
    --output-dir ./reports \
    --verbose
```

## Architecture

The simple backtest system consists of:

1. **SimpleBacktestEngine**: Core backtest execution engine
2. **MFT Engine Integration**: Direct use of your existing strategy logic
3. **Data Loading**: Parquet file reader for historical data
4. **Performance Metrics**: Comprehensive performance analysis
5. **Report Generation**: Text and CSV output formats

## Data Format

Expected parquet columns:
- `open_time`: Timestamp (milliseconds)
- `open`: Open price
- `high`: High price
- `low`: Low price
- `close`: Close price
- `volume`: Trading volume

## Output Files

The system generates:

1. **Text Report**: `backtest_report_{symbol}_{timestamp}.txt`
   - Performance summary
   - Trade analysis
   - Risk metrics

2. **Equity Curve**: `equity_curve_{symbol}_{timestamp}.csv`
   - Timestamp, equity, returns, drawdown

## Performance Metrics

- Total Return
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Win Rate
- Profit Factor
- Average Win/Loss

## Configuration

The system uses MFT engine configuration with fallback defaults:

```rust
// GARCH parameters
garch_omega: 0.00001,
garch_alpha: 0.1,
garch_beta: 0.85,

// Ornstein-Uhlenbeck
ou_window: 100,
ou_entry_z: 2.0,
ou_exit_z: 0.5,

// VPIN settings
vpin_bucket_size: 1000,
vpin_n_buckets: 50,
vpin_threshold: 0.025,

// Risk management
risk_per_trade: 0.02,
stop_loss_frac: 0.02,
max_hold_bars: 1000,
```

## Example Output

```
============================================================
MFT SIMPLE BACKTEST SUMMARY
============================================================
Initial Capital: $100000.00
Final Capital: $112345.67
Total Return: 12.35%

PERFORMANCE:
  Sharpe Ratio: 1.45
  Max Drawdown: 3.21%
  Win Rate: 58.3%
  Profit Factor: 1.67

TRADES:
  Total Trades: 24
  Sharpe Ratio: 1.45
  Sortino Ratio: 2.01
============================================================
```

## Advantages

1. **Simplicity**: No complex NautilusTrader dependencies
2. **Performance**: Fast execution with minimal overhead
3. **Flexibility**: Easy to modify and extend
4. **Reliability**: Uses proven MFT engine components
5. **Portability**: Self-contained binary

## Limitations

1. **Simplified Market Simulation**: No order book modeling
2. **Basic Fill Logic**: Market orders with simple slippage
3. **No Latency Modeling**: Instant execution assumed
4. **Limited Market Types**: Optimized for crypto spot/futures

## Future Enhancements

1. **Advanced Order Types**: Limit orders, stop orders
2. **Portfolio Management**: Multi-asset support
3. **Live Trading**: Real-time execution mode
4. **Web Interface**: Browser-based reporting
5. **Machine Learning**: Strategy optimization

## Troubleshooting

### Common Issues

1. **Data Loading Errors**
   - Check parquet file format
   - Verify column names
   - Ensure file permissions

2. **Compilation Errors**
   - Update Rust dependencies
   - Check workspace configuration
   - Verify MFT engine path

3. **Performance Issues**
   - Use release builds
   - Optimize data loading
   - Reduce log verbosity

### Debug Mode

```bash
RUST_LOG=debug ./target/release/simple_backtest.exe run \
    --symbol BTCUSDT \
    --data-file data/BTCUSDT/BTCUSDT_20240101.parquet
```

## Integration with Existing Systems

The simple backtest can be easily integrated:

1. **Data Pipeline**: Connect to your data sources
2. **Strategy Development**: Test new MFT strategies
3. **Risk Analysis**: Evaluate risk parameters
4. **Performance Monitoring**: Track strategy performance

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the code documentation
3. Examine the test cases
4. Validate data formats

This simple backtest system provides a solid foundation for testing your MFT trading strategies while maintaining the same engine logic used in live trading.
