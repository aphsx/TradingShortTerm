# VORTEX-7: Advanced Binance Futures Scalping Bot 🚀

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Trading](https://img.shields.io/badge/Market-Binance%20Futures-orange)](https://www.binance.com/)

**VORTEX-7** is a high-frequency, low-latency trading engine designed for **Binance USDT-M Futures**. It utilizes a multi-engine architecture to analyze order flow, tick momentum, technical indicators, and market sentiment in real-time.

---

## 🌟 Key Features | คุณสมบัติหลัก

- **Multi-Engine Analysis**: 5 specialized engines (Order Flow, Tick, Technical, Sentiment, Regime) working in parallel.
- **Ultra-Low Latency**: Built with `ccxt.pro` for async WebSocket connections, achieving sub-10ms pipeline processing.
- **Smart Risk Management**: Dynamic position sizing, ATR-based stop-loss/take-profit, and fee-aware strategy filtering.
- **Regime-Adaptive**: Automatically adjusts weights and strategies based on market volatility (Low, Normal, High, Extreme).
- **Comprehensive Logging**: Granular trade tracking via `orders.log` and **Supabase** for performance analytics.

---

## 🏗 System Architecture | สถาปัตยกรรมระบบ

The system is divided into modular components for maximum reliability:

1.  **Data Hub (`DataStorage`)**: Uses Redis for high-speed state management and kline caching.
2.  **Analysis Engines (`engines.py`)**:
    - **E1 Order Flow**: Real-time Orderbook imbalance & Micro-price.
    - **E2 Tick Momentum**: Trade velocity & Aggressor ratios.
    - **E3 Technicals**: RSI, Bollinger Bands, and ATR.
    - **E4 Sentiment**: L/S Ratios, Funding Rates, and Top Trader positioning.
    - **E5 Regime**: Volatility-based filters and dynamic weight overrides.
3.  **Core Logic (`core.py`)**:
    - **Decision Engine**: Combines engine signals into a weighted final score.
    - **Risk Manager**: Calculates leverage (10x-30x), position size, and SL/TP distances.
    - **Executor**: Manages order placement via CCXT with automatic retries and error handling.

---

## ⚡ Quick Start | เริ่มต้นใช้งาน

### 1. Requirements
- Python 3.10+
- Redis Server (local or managed)
- Supabase Account (SQL Logging)
- Binance API Keys (with Futures enabled)

### 2. Setup
```bash
git clone https://github.com/aphsx/TradingShortTerm.git
cd TradingShortTerm
pip install -r requirements.txt
```

### 3. Configuration
Rename `.env.example` to `.env` and fill in your credentials:
```env
BINANCE_API_KEY=your_apiKey
BINANCE_API_SECRET=your_secret
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
TRADING_PAIRS=BTCUSDT,ETHUSDT,SOLUSDT
```

### 4. Run the Bot
```bash
python main.py
```

### 5. Rust Backtester 🦀
For high-performance backtesting using the **Nautilus Trader Rust SDK**, use the `rust_backtest` module:
```bash
cd rust_backtest
cargo run
```
This will automatically:
- Download historical `aggTrades` from Binance.
- Cache them as **Parquet** files for ultra-fast loading.
- Run a simulation using the Nautilus event-driven engine.

---

## 📄 Documentation | เอกสารประกอบ

For a deep dive into the mathematical formulas, engine logic, and detailed strategy descriptions, please refer to:
- [**Detailed Technical Documentation**](./TECHNICAL_DOCUMENTATION.md) — สำหรับรายละเอียดเชิงลึกของระบบ
- [**Original Blueprint**](./ORIGINAL_README_BLUEPRINT.md) — The initial design document.

---

## ⚠️ Disclaimer
Trading futures involves significant risk. This software is for educational purposes only. Always test thoroughly on Testnet before going live.

---
*Developed with ❤️ by Antigravity*
