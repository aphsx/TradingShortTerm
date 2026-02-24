# TradingShortTerm — Multi-Frame Trend (MFT) Strategy

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Nautilus Trader](https://img.shields.io/badge/Nautilus-1.200%2B-green.svg)](https://nautilustrader.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**TradingShortTerm** เป็นระบบ Backtesting และ Trading Strategy สำหรับ Cryptocurrency Futures โดยใช้ **Nautilus Trader** framework พร้อม MFT (Multi-Frame Trend) Strategy ที่วิเคราะห์ตลาดด้วย 3 Layers

---

## 🎯 กลยุทธ์หลัก: MFT Strategy

### Multi-Frame Trend (3-Layer Analysis)

1. **Layer 1: Bias Filter (EMA 200)**
   - กำหนดทิศทางใหญ่ของตลาด
   - LONG: ราคาอยู่เหนือ EMA 200
   - SHORT: ราคาอยู่ใต้ EMA 200

2. **Layer 2: Entry Signal (EMA 9/21 + RSI)**
   - **EMA Crossover**: EMA 9 ตัดผ่าน EMA 21
   - **RSI Filter**:
     - LONG: RSI 50-65 (Momentum บวกแต่ไม่ Overbought)
     - SHORT: RSI 35-50 (Momentum ลบแต่ไม่ Oversold)

3. **Layer 3: Volume Confirmation (RVOL)**
   - Relative Volume > 1.5x
   - ยืนยันว่ามี momentum จริง ไม่ใช่ noise

### Risk Management

- **Stop Loss**: 0.5% (ปรับได้)
- **Take Profit**: 1.0% (ปรับได้)
- **Position Size**: 0.001 BTC ต่อ trade
- **Market**: Binance USDT-M Perpetual Futures

---

## 📂 โครงสร้างโปรเจค

```
TradingShortTerm/
├── nautilus_backtest/          # Backtesting System (Python)
│   ├── fetch_data.py           # ดึงข้อมูลจาก Binance API
│   ├── run_node.py             # รัน Backtest ด้วย Nautilus BacktestNode
│   ├── strategies/
│   │   ├── mft_strategy.py     # MFT Strategy Implementation
│   │   └── __init__.py
│   ├── catalog/                # Parquet Data Catalog
│   └── requirements.txt        # Python dependencies
│
├── mft_engine/                 # Rust Trading Engine (In Development)
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs             # Entry point
│       ├── strategy.rs         # MFT strategy logic
│       ├── engine.rs           # Signal processing
│       ├── risk.rs             # Risk management
│       ├── executor.rs         # Order execution
│       └── data.rs             # Data handling
│
├── .env                        # API Keys (ห้ามเผยแพร่!)
├── .gitignore
└── README.md                   # คุณอยู่ที่นี่!
```

---

## ⚡ เริ่มต้นใช้งาน

### 1. Requirements

- **Python 3.10+**
- **Nautilus Trader >= 1.200.0**
- **Binance Account** (ไม่ต้องใช้ API Key สำหรับดึงข้อมูล)

### 2. ติดตั้ง Dependencies

```bash
cd nautilus_backtest
pip install -r requirements.txt
```

### 3. ดึงข้อมูลจาก Binance

```bash
# ดึงข้อมูล 30 วัน (default)
python nautilus_backtest/fetch_data.py

# ดึงข้อมูล 7 วัน
python nautilus_backtest/fetch_data.py --days 7

# ดึงข้อมูล ETHUSDT ใช้ timeframe 5 นาที
python nautilus_backtest/fetch_data.py --symbol ETHUSDT --interval 5m --days 14
```

**Intervals ที่รองรับ**: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d`

### 4. รัน Backtest

#### Single Run (1 Config)

```bash
# ใช้ค่า balance จาก .env
python nautilus_backtest/run_node.py

# หรือ override balance
python nautilus_backtest/run_node.py --balance 5000
```

#### Parameter Sweep (หลาย Configs)

```bash
python nautilus_backtest/run_node.py --sweep
```

จะทดสอบหลายชุดพารามิเตอร์พร้อมกัน:
- EMA 9/21 vs 5/13 vs 12/26
- RVOL threshold 1.5 vs 2.0
- Stop Loss 0.3% vs 0.5%

#### ⚙️ Configuration

แก้ไขใน `.env`:
```bash
# Initial account balance for backtesting
BACKTEST_INITIAL_BALANCE=1000.0
```

**หมายเหตุ**: Fee model (maker/taker), fill model, และ random seed ใช้ค่า default ของ Nautilus อัตโนมัติ
- Maker fee: 0.02% (กำหนดใน instrument)
- Taker fee: 0.04% (กำหนดใน instrument)
- Fill/slippage model: Nautilus FillModel default

---

## 📊 ผลลัพธ์ที่ได้

หลังรัน Backtest จะแสดง:

```
====================================================================================================
=================================== BACKTEST PERFORMANCE SUMMARY ===================================
====================================================================================================

+-- BACKTEST RESULT
|
| Total PnL         :       -13.85 USDT ( -1.39%)
| Total Fees        :        16.89 USDT
| Net PnL (w/ fees) :       -30.75 USDT
| Win Rate          :        34.81%
| Profit Factor     :       1.0356
| Sharpe Ratio      :       0.8805
| Sortino Ratio     :       1.2809
| Max Winner        :         2.03 USDT
| Max Loser         :        -1.43 USDT
| Avg Winner        :         0.76 USDT
| Avg Loser         :        -0.48 USDT
|
+-- TRADE SUMMARY
|
| Total Orders      :          585
| Total Positions   :          293
|
| Top 5 Best Trades:
|         2.02669972 USDT @ 77781.9
|         1.12146924 USDT @ 89372.2
|         ...
|
| Initial Balance   :      1000.00 USDT
| Final Balance     :       969.25 USDT
| Net Change        :       -30.75 USDT
```

---

## 🔧 ปรับแต่งพารามิเตอร์

แก้ไขในไฟล์ [run_node.py](nautilus_backtest/run_node.py#L48-L57):

```python
def make_run_config(
    *,
    ema_fast: int = 9,           # EMA เร็ว
    ema_medium: int = 21,        # EMA กลาง
    ema_slow: int = 200,         # EMA ช้า (Bias filter)
    rsi_long_min: float = 50.0,  # RSI ขั้นต่ำสำหรับ Long
    rvol_threshold: float = 1.5, # Relative Volume ขั้นต่ำ
    stop_loss_pct: float = 0.005,    # 0.5%
    take_profit_pct: float = 0.010,  # 1.0%
    slippage_prob: float = 0.5,      # Fill Model
    run_id: str = "BACKTESTER-DEFAULT",
) -> BacktestRunConfig:
```

---

## 🦀 Rust Engine (mft_engine)

**Status**: 🚧 Under Development

เป็น high-performance trading engine เขียนด้วย Rust สำหรับ:
- Live Trading execution
- Real-time signal processing
- WebSocket connection กับ Binance

### Build & Run

```bash
cd mft_engine
cargo build --release
cargo run
```

---

## 📖 เอกสารเพิ่มเติม

### Strategy Details

- [MFT Strategy Implementation](nautilus_backtest/strategies/mft_strategy.py)
  - 3-Layer analysis logic
  - Custom indicators (EMA, RSI, RVOL)
  - State machine design

### Data Pipeline

- [fetch_data.py](nautilus_backtest/fetch_data.py)
  - Binance Futures API integration
  - Parquet catalog management
  - Automatic batch fetching (1500 bars/request)

### Backtest Engine

- [run_node.py](nautilus_backtest/run_node.py)
  - Nautilus BacktestNode wrapper
  - Custom reports (PnL, Win Rate, Sharpe, etc.)
  - Parameter sweep support

---

## 🎓 ทำความเข้าใจกลยุทธ์

### ตัวอย่างสัญญาณ LONG

```
✅ เงื่อนไข:
1. Price > EMA 200        (Bullish bias)
2. EMA 9 > EMA 21         (Fast crosses above medium)
3. RSI = 55               (Momentum zone, not overbought)
4. RVOL = 2.1x            (High volume confirmation)

➡️  ENTRY: Market Buy 0.001 BTC
🛡️  Stop Loss:  -0.5%
🎯  Take Profit: +1.0%
```

### ตัวอย่างสัญญาณ SHORT

```
✅ เงื่อนไข:
1. Price < EMA 200        (Bearish bias)
2. EMA 9 < EMA 21         (Fast crosses below medium)
3. RSI = 42               (Momentum zone, not oversold)
4. RVOL = 1.8x            (High volume confirmation)

➡️  ENTRY: Market Sell 0.001 BTC
🛡️  Stop Loss:  +0.5%
🎯  Take Profit: -1.0%
```

---

## 🔬 Parameter Optimization

ใช้ `--sweep` mode เพื่อเปรียบเทียบพารามิเตอร์หลายชุด:

```python
# ใน run_node.py
combos = [
    (9,  21, 1.5, 0.005, 0.010, "EMA9-21_RVOL1.5"),
    (9,  21, 2.0, 0.005, 0.010, "EMA9-21_RVOL2.0"),
    (5,  13, 1.5, 0.005, 0.010, "EMA5-13_RVOL1.5"),
    (12, 26, 1.5, 0.005, 0.010, "EMA12-26_RVOL1.5"),
]
```

Backtest จะรันทั้งหมดและแสดงผลเปรียบเทียบ

---

## ⚠️ Disclaimer

การเทรด Futures มีความเสี่ยงสูง โปรเจคนี้เป็นเพียงเครื่องมือสำหรับศึกษาเท่านั้น

**คำเตือน**:
- ❌ ไม่ใช่คำแนะนำในการลงทุน
- ❌ ผู้พัฒนาไม่รับผิดชอบต่อผลกำไร/ขาดทุน
- ✅ ทดสอบบน Testnet ก่อนใช้จริงเสมอ
- ✅ เข้าใจกลยุทธ์และพารามิเตอร์ก่อนใช้งาน

---

## 📝 License

MIT License — ใช้งานอิสระ แต่ใช้งานด้วยความระมัดระวัง

---

## 🙏 Acknowledgments

- [Nautilus Trader](https://nautilustrader.io/) — High-performance trading framework
- [Binance API](https://binance-docs.github.io/apidocs/futures/en/) — Market data provider
- Community contributors

---

**Developed by Antigravity** | Last Updated: 2026-02-24
