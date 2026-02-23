# Rust Backtest System

## Overview
This is a Rust-based backtesting system using Nautilus for realistic trading simulations, **fully integrated with the MFT ENGINE configuration**.

## Setup

### 1. Install Rust
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### 2. Environment Configuration
The system uses the **main MFT ENGINE `.env` file** in the project root directory (`C:\Users\aphsx\Documents\GitHub\TradingShortTerm\.env`).

No additional configuration needed - it automatically uses:
- `BACKTEST_SYMBOL` - Trading pair to backtest (default: BTCUSDT)
- `TRADING_PAIRS` - Symbols to download data for (default: BTCUSDT,ETHUSDT,SOLUSDT)
- `BINANCE_FUTURES_REST_URL` - API endpoint (default: testnet)
- `KLINE_INTERVAL` - Timeframe (default: 1m)
- `BACKTEST_LIMIT` - Number of bars to fetch (default: 43200)

## Usage

### 1. Fetch Data (if needed)
```bash
cargo run --bin fetch_data
```
Downloads data according to MFT ENGINE settings (interval, limit, symbols).

### 2. Run Backtest
```bash
cargo run --bin backtest
```
Runs backtest using the configured symbol and MFT ENGINE parameters.

## Features
- **Realistic Backtesting**: Uses Nautilus backtest engine for professional-grade simulations
- **EMA Cross Strategy**: Includes an example EMA crossover strategy
- **OHLCV Data**: Processes parquet files with Open, High, Low, Close, Volume data
- **Multiple Timeframes**: Supports 1-minute kline data
- **Multiple Symbols**: Can backtest BTCUSDT, ETHUSDT, SOLUSDT simultaneously

## Data Structure
The system expects parquet files with the following columns:
- `timestamp`: Human-readable timestamp
- `open`: Opening price
- `high`: Highest price
- `low`: Lowest price  
- `close`: Closing price
- `volume`: Trading volume
- `open_time`: Unix timestamp in milliseconds

## Output
The backtest will:
1. Load and validate market data
2. Convert OHLCV data to Nautilus QuoteTick and TradeTick events
3. Run the EMA crossover strategy
4. Display results and performance metrics

## Troubleshooting
- Ensure Rust is installed and in your PATH
- Check that data files exist in `data/{SYMBOL}/` directory
- Verify `.env` file is properly configured
- Make sure you have internet connection for data fetching
