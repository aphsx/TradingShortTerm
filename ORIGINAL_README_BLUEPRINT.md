# VORTEX-7 — เอกสารออกแบบระบบฉบับสมบูรณ์
## Binance Futures Short-Term Scalping Bot

---

# สารบัญ

1. [ภาพรวมโปรเจค](#1-ภาพรวมโปรเจค)
2. [สิ่งที่ต้องเตรียม (Requirements)](#2-สิ่งที่ต้องเตรียม)
3. [สถาปัตยกรรมระบบ](#3-สถาปัตยกรรมระบบ)
4. [E0 — Data Hub](#4-e0--data-hub)
5. [E1 — Order Flow Engine (35%)](#5-e1--order-flow-engine-35)
6. [E2 — Tick Engine (25%)](#6-e2--tick-engine-25)
7. [E3 — Technical Engine (20%)](#7-e3--technical-engine-20)
8. [E4 — Sentiment Engine (12%)](#8-e4--sentiment-engine-12)
9. [E5 — Regime Filter (8%)](#9-e5--regime-filter-8)
10. [S1 — Decision Engine](#10-s1--decision-engine)
11. [S2 — Risk Manager](#11-s2--risk-manager)
12. [S3 — Executor](#12-s3--executor)
13. [3 Trading Strategies](#13-3-trading-strategies)
14. [Data Layer (Redis + PostgreSQL)](#14-data-layer)
15. [Infrastructure & APIs](#15-infrastructure--apis)
16. [Telegram Bot & Dashboard](#16-telegram-bot--dashboard)
17. [Learning Module](#17-learning-module)
18. [โครงสร้างโปรเจค](#18-โครงสร้างโปรเจค)
19. [แผนพัฒนา 4 Phases](#19-แผนพัฒนา-4-phases)
20. [KPI & Monitoring](#20-kpi--monitoring)
21. [สูตรคณิตศาสตร์ทั้งหมด](#21-สูตรคณิตศาสตร์ทั้งหมด)

---

# 1. ภาพรวมโปรเจค

## คอนเซปต์หลัก: "Sweet Spot Scalping"

| ช่วงเวลา | ปัญหา |
|---|---|
| < 30 วินาที | กำไรน้อยกว่า fee, win rate ต้องสูงมากผิดปกติ |
| ชั่วโมง+ | Exposure นาน, overnight risk, ข่าวกระทบ |
| **30s — 15 นาที ✅** | กำไรคุ้ม fee, ไม่นานจน stress, price action พัฒนาพอ |

## สเปคโดยรวม

| หัวข้อ | ค่า |
|---|---|
| ตลาด | Binance USDT-M Perpetual Futures |
| คู่เทรดหลัก | BTCUSDT, ETHUSDT |
| คู่เทรดรอง | SOLUSDT + Top Vol Alt (ขึ้นอยู่กับ volume วันนั้น) |
| Timeframe หลัก | 1m, 3m (+ raw tick data) |
| Timeframe ประกอบ | 5m, 15m (ดู context เท่านั้น) |
| ระยะถือ | 30 วินาที — 15 นาที |
| Max Hold (บังคับปิด) | 20 นาที |
| Leverage | 5x — 12x (ปรับตาม volatility) |
| TP Target ต่อไม้ | 0.15% — 0.50% ของ position |
| SL ต่อไม้ | 0.10% — 0.30% ของ position |
| R:R Ratio | ≥ 1.3 : 1 (ไม่เข้าถ้าต่ำกว่า) |
| Entry Method | LIMIT Post-Only (Maker fee เสมอ) |
| Server Location | Singapore (latency 1-3ms ถึง Binance) |
| ข้อมูล | ฟรี 100% จาก Binance API |
| จำนวน Trades/วัน | 10 — 30 ไม้ |

## ตัวอย่างกำไร (Conservative Estimate)

```
Balance: $500 | Leverage: 10x | Position Size: $5,000

TP เฉลี่ย 0.25% ของ position  = +$12.50 gross
Fee Maker round-trip + BNB     = $5,000 × 0.036% = $1.80
Net per winning trade          = +$10.70

SL เฉลี่ย 0.15% ของ position  = -$7.50 gross
Fee on loss                    = $1.80
Net per losing trade           = -$9.30

วัน 1 — 20 trades/วัน × Win Rate 60%:
  Wins   : 12 × $10.70 = +$128.40
  Losses :  8 × $9.30  =  -$74.40
  NET DAILY              ≈ +$54.00
  Fee total              =  $36.00/วัน
  ประมาณการ/เดือน        ≈ $1,600

หมายเหตุ: Conservative estimate — จริงผันผวนตาม market condition
```

---

# 2. สิ่งที่ต้องเตรียม

## 2.1 Binance Account & API

### สิ่งที่ต้องสมัคร/เปิดใช้
- **Binance Account** ยืนยัน KYC ระดับ Intermediate
- **Futures Account** เปิด USDT-M Futures
- **API Key** ต้องเปิด Permission:
  - ✅ Enable Reading
  - ✅ Enable Futures
  - ❌ Enable Spot & Margin Trading (ไม่ต้อง)
  - ❌ Enable Withdrawals (ห้ามเปิดเด็ดขาด — security)
- **Restrict to IP** ใส่ IP ของ VPS เท่านั้น

### ประเภท API ที่ใช้
| API | ประเภท | การใช้งาน | Rate Limit |
|---|---|---|---|
| WebSocket aggTrade | WS | ทุก trade real-time | ไม่มี |
| WebSocket depth@100ms | WS | Orderbook 20 levels | ไม่มี |
| WebSocket kline_1m/3m/5m/15m | WS | Candle updates | ไม่มี |
| GET /fapi/v1/openInterest | REST | OI ปัจจุบัน | 1200/min |
| GET /futures/data/globalLongShortAccountRatio | REST | L/S Ratio | 1200/min |
| GET /fapi/v1/fundingRate | REST | Funding Rate | 1200/min |
| GET /futures/data/topLongShortAccountRatio | REST | Top Trader | 1200/min |
| GET /fapi/v1/klines | REST | Backfill historical | 1200/min |
| POST /fapi/v1/order | REST | ส่งออร์เดอร์ | 300/10s |
| DELETE /fapi/v1/order | REST | ยกเลิกออร์เดอร์ | 300/10s |
| GET /fapi/v2/positionRisk | REST | ดู position ปัจจุบัน | 1200/min |
| GET /fapi/v2/account | REST | Balance | 1200/min |

### BNB สำหรับจ่าย Fee
- ถือ BNB ในบัญชี Futures → ลด fee 10%
- Maker fee: 0.020% → **0.018%** (ด้วย BNB)
- Taker fee: 0.050% → **0.045%** (ด้วย BNB)
- Round-trip Maker+BNB: **0.036%**
- แนะนำถือ BNB เพียงพอสำหรับ ~100 trades ล่วงหน้า

## 2.2 Infrastructure

| Component | Spec | ราคา/เดือน |
|---|---|---|
| VPS Singapore | 2 vCPU, 4GB RAM, 50GB SSD | $20-40 |
| ผู้ให้บริการแนะนำ | AWS ap-southeast-1, Vultr SGP, DigitalOcean SGP | - |
| OS | Ubuntu 22.04 LTS | ฟรี |
| Docker + Compose | Container orchestration | ฟรี |
| Redis 7+ | Hot data / state | ฟรี (self-host) |
| PostgreSQL 15+ | Analytics / trade history | ฟรี (self-host) |

## 2.3 Software Dependencies

| Library | ใช้ทำอะไร | ภาษา |
|---|---|---|
| python-binance หรือ binance-futures-connector | Binance API wrapper | Python |
| websockets / aiohttp | WebSocket async | Python |
| asyncio | Async event loop | Python built-in |
| redis-py | Redis client | Python |
| asyncpg / psycopg2 | PostgreSQL client | Python |
| numpy | คำนวณ indicators | Python |
| pandas | Data manipulation (backtest) | Python |
| python-telegram-bot | Telegram notifications | Python |
| fastapi + uvicorn | Web dashboard API | Python |
| systemd | Process management | Linux |

## 2.4 Telegram Bot
- สร้าง Bot ผ่าน @BotFather
- เก็บ `BOT_TOKEN` และ `CHAT_ID` ของคุณ
- ใช้สำหรับ: แจ้งเตือน, สั่ง stop, ดู stats

---

# 3. สถาปัตยกรรมระบบ

## ภาพรวม Data Flow

```
BINANCE WEBSOCKET STREAMS (Singapore VPS → Binance: 1-3ms)
┌─────────────────┐  ┌──────────────┐  ┌───────────────────────┐
│  aggTrade WS    │  │ depth@100ms  │  │  kline WS             │
│  (ทุก trade)    │  │  (orderbook) │  │  1m / 3m / 5m / 15m   │
└────────┬────────┘  └──────┬───────┘  └──────────┬────────────┘
         │                  │                      │
         ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    E0. DATA HUB                                  │
│           Stream Processor + Redis State Manager                 │
└──────┬───────────┬───────────┬───────────┬────────────┬─────────┘
       │           │           │           │            │
       ▼           ▼           ▼           ▼            ▼
  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
  │  E1    │  │  E2    │  │  E3    │  │  E4    │  │  E5    │
  │Order   │  │ Tick   │  │ Tech   │  │Sent.   │  │Regime  │
  │ Flow   │  │Engine  │  │Engine  │  │Engine  │  │Filter  │
  │ 35%    │  │  25%   │  │  20%   │  │  12%   │  │  8%    │
  └────┬───┘  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘
       │          │           │           │            │
       └──────────┴─────┬─────┴───────────┴────────────┘
                        │
                        ▼
            ┌────────────────────┐
            │   S1. DECISION     │
            │      ENGINE        │
            └────────┬───────────┘
                     │
                     ▼
            ┌────────────────────┐
            │   S2. RISK         │
            │     MANAGER        │
            └────────┬───────────┘
                     │
                     ▼
            ┌────────────────────┐
            │   S3. EXECUTOR     │
            │ (Binance Orders)   │
            └────────┬───────────┘
                     │
            ┌────────┴────────┐
            ▼                 ▼
    ┌──────────────┐  ┌──────────────────┐
    │ Telegram Bot │  │ Dashboard + DB   │
    └──────────────┘  └──────────────────┘
```

## ความเร็วของแต่ละขั้นตอน

| ขั้นตอน | เวลา |
|---|---|
| Tick data เข้า Data Hub | < 1ms |
| Data Hub → Engine update | < 1ms |
| Engine → Decision Engine | < 3ms |
| Decision → Risk Check | < 1ms |
| Risk → Send Order | < 1ms |
| Order → Binance (network) | 1-3ms |
| **Total Pipeline** | **< 10ms** |

---

# 4. E0 — Data Hub

## หน้าที่
เป็นศูนย์กลางรับข้อมูลทุกอย่าง แล้ว distribute ไปให้ 5 engines

## WebSocket Connections ที่ดูแล

### 1. aggTrade Stream
- **Endpoint:** `wss://fstream.binance.com/ws/{symbol}@aggTrade`
- **ข้อมูลที่ได้:** price, quantity, isBuyerMaker, time, tradeId
- **การจัดเก็บ:** Ring Buffer ใน Redis — เก็บ 2000 ticks ล่าสุดต่อ symbol
- **ส่งต่อ:** E2 Tick Engine (ทุก trade), E1 (update CVD)

### 2. Depth Stream (Orderbook)
- **Endpoint:** `wss://fstream.binance.com/ws/{symbol}@depth20@100ms`
- **ข้อมูลที่ได้:** top 20 bid levels, top 20 ask levels (price, quantity)
- **การจัดเก็บ:** Redis Hash — snapshot ล่าสุด
- **ส่งต่อ:** E1 Order Flow Engine (ทุก 100ms)

### 3. Kline Stream
- **Endpoint:** `wss://fstream.binance.com/ws/{symbol}@kline_1m` (ทำ 4 connections: 1m, 3m, 5m, 15m)
- **ข้อมูลที่ได้:** OHLCV + volume + isClosed
- **การจัดเก็บ:** Redis Sorted Set — 500 candles ต่อ timeframe ต่อ symbol
- **ส่งต่อ:** E3 Technical Engine

### 4. REST Polling (ผ่าน asyncio task)
- OI: ทุก 15 วินาที → E4
- Long/Short Ratio: ทุก 30 วินาที → E4
- Funding Rate: ทุก 60 วินาที → E4
- Top Trader Ratio: ทุก 30 วินาที → E4

## Reconnection Logic
- Auto-reconnect ทันทีเมื่อ WS ตัด
- Exponential backoff: 1s, 2s, 4s, 8s, max 30s
- หลัง reconnect: backfill candles ที่หายไปผ่าน REST
- ถ้าตัดนาน > 5 วินาที: ปิดทุก position (Emergency Protocol)

---

# 5. E1 — Order Flow Engine (35%)

## หน้าที่
วิเคราะห์ orderbook + CVD เพื่อดูว่าเงินจริงๆ กำลังไปทางไหน
เป็น Primary Signal — มีน้ำหนักมากที่สุด

## ทำงานทุก 100ms (รับข้อมูลจาก depth update)

## สัญญาณที่คำนวณ

### 5.1 Bid/Ask Imbalance
```
bid_volume = Σ(quantity) ของ top 10 bid levels
ask_volume = Σ(quantity) ของ top 10 ask levels

imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)

Range: -1.0 ถึง +1.0
  > +0.30 = BUY_PRESSURE (bid ครอบงำ)
  < -0.30 = SELL_PRESSURE (ask ครอบงำ)
  ระหว่าง = NEUTRAL
```

### 5.2 Imbalance Velocity
```
velocity = (imbalance_now - imbalance_5_readings_ago) / time_elapsed

  > 0 และ positive = imbalance กำลังเพิ่มขึ้นฝั่ง buy = conviction สูง
  เปลี่ยนเร็ว > 0.05/s = signal แรง
```

### 5.3 CVD (Cumulative Volume Delta)
```
สำหรับแต่ละ trade ใน aggTrade:
  if isBuyerMaker == false:  delta = +quantity  (buy aggressor)
  if isBuyerMaker == true:   delta = -quantity  (sell aggressor)

CVD(t) = Σ delta ตั้งแต่เริ่ม session (หรือ reset ทุก 4 ชั่วโมง)

CVD rising + price rising  = healthy uptrend ✅
CVD falling + price rising = divergence → reversal signal ⚠️
CVD rising + price falling = divergence → reversal signal ⚠️
```

### 5.4 CVD Short-term Slope
```
cvd_slope_30s = (CVD_now - CVD_30_seconds_ago) / 30

  > 0 = buying pressure ใน 30 วินาทีที่ผ่านมา
  < 0 = selling pressure
  |slope| > threshold = momentum มีนัยสำคัญ
```

### 5.5 Wall Detection
```
avg_level_size = mean(quantity ของทุก bid/ask level)

สำหรับแต่ละ level:
  if quantity > avg_level_size × 5.0:
    → บันทึกเป็น WALL ที่ราคานั้น

Wall บน ask side = Resistance (ขาย pressure)
Wall บน bid side = Support (ซื้อ pressure)
```

### 5.6 Wall Absorption Detection
```
wall_was_there_before = ตรวจสอบ history ว่าเคยมี wall ที่ level นี้ไหม
wall_is_gone_now = quantity ลดลง > 80%

if wall_absorbed AND price_broke_through:
  → BREAKOUT signal (real momentum)
  strength = (wall_size / avg_level_size) normalized
```

### 5.7 Spoofing Filter
```
สำหรับแต่ละ order ที่ใหม่ใน orderbook:
  record: (price, quantity, time_appeared)

ทุก 500ms:
  ตรวจ orders ที่หายไปโดยไม่ถูก fill
  if disappeared_without_fill AND age < 500ms:
    → mark เป็น SPOOF → ไม่นับใน wall detection

Spoof ratio = spoof_orders / total_new_orders
  if > 0.5 = market manipulated → ลด conviction ของ E1
```

### 5.8 Micro Price (Fair Value)
```
micro_price = (best_bid × ask_volume + best_ask × bid_volume) / (bid_volume + ask_volume)

ใช้แทน last_price เพื่อความแม่นยำสูงกว่าในการ detect direction
```

## Output Signal
```
{
  direction: "BUY_PRESSURE" | "SELL_PRESSURE" | "NEUTRAL",
  strength: 0.0 — 1.0,
  conviction: 0.0 — 1.0,
  imbalance: float,
  cvd_slope: float,
  wall_near: bool,
  wall_level: float | null,
  wall_absorbed: bool,
  spoof_ratio: float,
  micro_price: float
}
```

---

# 6. E2 — Tick Engine (25%)

## หน้าที่
วิเคราะห์ trade flow จริงๆ ที่เกิดขึ้น (ไม่ใช่ orderbook คาดการณ์)
ดูว่า momentum ของการ execute จริงบอกอะไร

## ทำงาน: ทุก trade ที่เข้ามา (event-driven)

## สัญญาณที่คำนวณ

### 6.1 Trade Velocity
```
velocity_1s = จำนวน trades ใน 1 วินาทีล่าสุด
velocity_avg = moving average ของ velocity ใน 30 วินาทีที่ผ่านมา

velocity_ratio = velocity_1s / velocity_avg

  > 2.0 = ตลาดตื่นตัว — มี event เกิดขึ้น
  > 3.0 = ตื่นตัวมาก — มักเกิดก่อน/ระหว่าง big move
```

### 6.2 Buy/Sell Aggressor Ratio
```
buy_volume_5s  = Σ quantity ของ trades ที่ isBuyerMaker = false ใน 5 วินาทีล่าสุด
sell_volume_5s = Σ quantity ของ trades ที่ isBuyerMaker = true ใน 5 วินาทีล่าสุด

aggressor_ratio = buy_volume_5s / (buy_volume_5s + sell_volume_5s)

  > 0.65 = buy dominated → bullish signal
  < 0.35 = sell dominated → bearish signal
```

### 6.3 Momentum Detection (Trade Streak)
```
ดูทิศทางของ trades ล่าสุด N trades:

for each trade in last_20_trades:
  classify as BUY_AGGRESSOR or SELL_AGGRESSOR

ถ้า 8+ trades ติดกันเป็น BUY → MOMENTUM_LONG (burst detected)
ถ้า 8+ trades ติดกันเป็น SELL → MOMENTUM_SHORT (burst detected)

burst_strength = streak_length / 20  (normalized)
```

### 6.4 Volume Spike Detection
```
volume_3s = Σ quantity ใน 3 วินาทีล่าสุด
volume_avg_30s = Σ quantity ใน 30 วินาที / 10  (avg per 3s)

spike_ratio = volume_3s / volume_avg_30s

  > 2.5 = volume spike — ต้อง confirm ด้วย direction
  > 4.0 = extreme spike — อาจเป็น liquidation cascade
```

### 6.5 Big Trade Alert
```
สำหรับแต่ละ trade:
  notional_value = price × quantity

  if notional_value > $50,000:
    → BIG_TRADE detected
    direction = BUY หรือ SELL (จาก isBuyerMaker)
    → ส่ง alert ให้ Decision Engine พิจารณาพิเศษ
    → Institutional activity indicator
```

### 6.6 Delta Accumulation
```
ทุก 5 วินาที:
  delta_5s = buy_volume_5s - sell_volume_5s

delta_trend = slope ของ delta_5s ใน 30 วินาทีที่ผ่านมา (linear regression)

  positive slope = buying pressure เพิ่มขึ้น
  negative slope = selling pressure เพิ่มขึ้น
```

## Output Signal
```
{
  direction: "MOMENTUM_LONG" | "MOMENTUM_SHORT" | "NEUTRAL",
  strength: 0.0 — 1.0,
  velocity_ratio: float,
  aggressor_ratio: float,
  streak: int,
  volume_spike: bool,
  spike_ratio: float,
  big_trade: bool,
  big_trade_direction: "BUY" | "SELL" | null,
  delta_slope: float
}
```

---

# 7. E3 — Technical Engine (20%)

## หน้าที่
คำนวณ indicators แบบ fast บน candles เพื่อยืนยันทิศทาง
ใช้ข้อมูลจาก candle cache ใน Redis

## ทำงาน: ทุก 1 วินาที (หลังจาก candle cache อัปเดต)

## Indicators ที่ใช้

### 7.1 EMA Cross (1m)
```
EMA(9)  = Exponential Moving Average ของ close price 9 periods
EMA(21) = Exponential Moving Average ของ close price 21 periods

สูตร: EMA(t) = close(t) × k + EMA(t-1) × (1-k)
      k = 2 / (period + 1)

Signal:
  EMA9 > EMA21 AND distance > 0.02% = BULLISH trend
  EMA9 < EMA21 AND distance > 0.02% = BEARISH trend
  
Cross Up (EMA9 เพิ่งข้าม EMA21 ขึ้นมา)  = LONG signal เพิ่ม strength
Cross Down (EMA9 เพิ่งข้าม EMA21 ลง)    = SHORT signal เพิ่ม strength
```

### 7.2 EMA Slope บน 3m (Context)
```
ema9_3m = EMA(9) บน 3m candle

slope_3m = (ema9_3m_now - ema9_3m_5_periods_ago) / 5

  > 0 = uptrend context (เล่น LONG ดีกว่า)
  < 0 = downtrend context (เล่น SHORT ดีกว่า)
  
ใช้ weight เป็น multiplier: ถ้าเล่นตาม context → ×1.2, สวน → ×0.7
```

### 7.3 RSI (1m)
```
สูตร RSI(14):
  gains = average ของ (close - prev_close) เฉพาะที่เป็นบวก ใน 14 periods
  losses = average ของ (close - prev_close) เฉพาะที่เป็นลบ ใน 14 periods
  RS = gains / losses
  RSI = 100 - (100 / (1 + RS))

Signal:
  RSI < 30 = Oversold → LONG zone (mean revert / continuation ขึ้น)
  RSI > 70 = Overbought → SHORT zone
  RSI ระหว่าง 45-55 = Neutral

RSI Divergence:
  price_higher_high AND rsi_lower_high = BEARISH divergence → SHORT signal
  price_lower_low   AND rsi_higher_low = BULLISH divergence → LONG signal
```

### 7.4 MACD Histogram (1m)
```
MACD_line  = EMA(12) - EMA(26) ของ close
Signal_line = EMA(9) ของ MACD_line
Histogram   = MACD_line - Signal_line

Signal:
  Histogram เปลี่ยนจากลบเป็นบวก = Momentum shift UP
  Histogram เปลี่ยนจากบวกเป็นลบ = Momentum shift DOWN
  |Histogram| เพิ่มขึ้น = momentum เร่งตัว
```

### 7.5 Bollinger Bands (1m)
```
SMA(20)    = Simple Moving Average 20 periods
std_dev    = Standard Deviation ของ close 20 periods
Upper Band = SMA(20) + 2 × std_dev
Lower Band = SMA(20) - 2 × std_dev
Band Width = (Upper - Lower) / SMA(20)

Signal:
  price > Upper Band = overbought zone (short candidate)
  price < Lower Band = oversold zone (long candidate)
  
BB Squeeze (Band Width ต่ำผิดปกติ):
  band_width < 20th percentile ของ 100 periods ล่าสุด = squeeze
  หลัง squeeze มักเกิด breakout → รอ E1+E2 confirm ทิศทาง
```

### 7.6 VWAP
```
VWAP(t) = Σ(price × volume) / Σ(volume)  (reset ทุกวัน 00:00 UTC)

Signal:
  price > VWAP = bullish bias → เน้น LONG
  price < VWAP = bearish bias → เน้น SHORT
  
Distance from VWAP:
  vwap_distance = (price - VWAP) / VWAP × 100  (%)
  |distance| > 0.5% = extended จาก VWAP → reversion potential
```

### 7.7 ATR (ใช้ใน Risk Manager)
```
True Range(t) = max(
  high(t) - low(t),
  |high(t) - close(t-1)|,
  |low(t) - close(t-1)|
)

ATR(14) = EMA(14) ของ True Range

ใช้บน 1m candle → ATR ปัจจุบัน = volatility ของตลาดในช่วง 14 นาที
```

### 7.8 Support/Resistance Levels
```
ดู 200 candles ล่าสุดบน 5m timeframe:

Swing High = candle ที่ high สูงกว่า 2 candles ทั้งซ้ายและขวา
Swing Low  = candle ที่ low ต่ำกว่า 2 candles ทั้งซ้ายและขวา

เก็บ top 5 swing high (resistance)
เก็บ top 5 swing low (support)

ระยะห่างจาก price ปัจจุบัน:
  nearest_resistance_dist = (nearest_resistance - price) / price × 100
  nearest_support_dist    = (price - nearest_support) / price × 100

ถ้า TP target ชน resistance ก่อน → ปรับ TP ลงมาที่ resistance
ถ้าราคาอยู่ใกล้ S/R มาก → ระวัง (อาจ bounce)
```

## Output Signal
```
{
  direction: "LONG" | "SHORT" | "NEUTRAL",
  strength: 0.0 — 1.0,
  ema_trend: "BULLISH" | "BEARISH" | "NEUTRAL",
  rsi: float,
  rsi_zone: "OVERSOLD" | "OVERBOUGHT" | "NORMAL",
  rsi_divergence: bool,
  macd_momentum: "UP" | "DOWN" | "NEUTRAL",
  bb_zone: "UPPER" | "LOWER" | "MIDDLE",
  bb_squeeze: bool,
  vwap_side: "ABOVE" | "BELOW",
  atr: float,
  nearest_resistance: float,
  nearest_support: float,
  key_levels: [float]
}
```

---

# 8. E4 — Sentiment Engine (12%)

## หน้าที่
ดู crowd positioning และ liquidation zones
ใช้เป็น context และ contrarian signal เมื่อ extreme

## ทำงาน: ทุก 15-30 วินาที (REST poll)

## สัญญาณที่คำนวณ

### 8.1 Open Interest Delta
```
OI_now  = GET /fapi/v1/openInterest
OI_5min_ago = ค่าที่เก็บไว้ใน Redis 5 นาทีก่อน

OI_change_pct = (OI_now - OI_5min_ago) / OI_5min_ago × 100

แปลผล:
  OI ↑ + price ↑ = Real buying (new longs เข้า) → BULLISH confirm
  OI ↑ + price ↓ = Shorts stacking (new shorts เข้า) → BEARISH confirm
  OI ↓ + price ↑ = Short covering (ไม่ใช่ real demand) → อ่อน
  OI ↓ + price ↓ = Long liquidation / stop out → อาจ bounce เร็ว
```

### 8.2 Long/Short Ratio
```
GET /futures/data/globalLongShortAccountRatio

long_ratio  = % ของ accounts ที่มี net long position
short_ratio = % ของ accounts ที่มี net short position

ใช้เป็น contrarian:
  long_ratio > 70% = crowd ล็อง มากเกิน → SHORT bias (over-leveraged longs = fuel for cascade)
  short_ratio > 65% = crowd ชอร์ต มากเกิน → LONG bias
  ช่วงปกติ = ไม่ใช้เป็น signal
```

### 8.3 Funding Rate
```
GET /fapi/v1/fundingRate

ค่า funding ปัจจุบัน (ชำระทุก 8 ชั่วโมง):
  > +0.03% = over-leveraged longs → SHORT bias (longs จ่าย shorts)
  < -0.01% = over-leveraged shorts → LONG bias
  ช่วง -0.01% ถึง +0.03% = neutral

funding_urgency:
  ถ้าใกล้เวลาชำระ (< 2 ชั่วโมง) × 1.5 weight
  เพราะ traders ปิด position ก่อนชำระ = predictable movement
```

### 8.4 Estimated Liquidation Clusters
```
ใช้ OI + price + leverage assumptions คำนวณ:

สมมติ distribution ของ leverage: 5x (30%), 10x (35%), 20x (25%), 25x (10%)
สำหรับแต่ละ leverage tier:

  long_liq_price  = avg_entry × (1 - 1/leverage × 0.95)  (0.95 = maintenance margin)
  short_liq_price = avg_entry × (1 + 1/leverage × 0.95)

  avg_entry ≈ เฉลี่ย price ในช่วง OI เพิ่มขึ้นล่าสุด

สร้าง liq_map: dictionary ของ price_level → estimated_liq_volume

liq_clusters = price levels ที่มี estimated_liq_volume สูงมาก
```

### 8.5 Liquidation Proximity Score
```
current_price = ราคาปัจจุบัน
nearest_liq_cluster = liq cluster ที่ใกล้ที่สุดในทิศทาง momentum

distance_to_liq = |current_price - nearest_liq_cluster| / current_price

liq_proximity_score = max(0, 1 - distance_to_liq / 0.005)
  
  ถ้า distance = 0 → score = 1.0 (อยู่บน cluster)
  ถ้า distance = 0.5% → score = 0
  
score > 0.7 = ราคาใกล้ liq cluster มาก → Strategy C opportunity
```

### 8.6 Top Trader Positioning
```
GET /futures/data/topLongShortAccountRatio

top_trader_long_pct = % ของ top traders ที่ net long

ใช้เป็น smart money indicator:
  > 60% long = smart money bullish → reinforce LONG signals
  < 40% long = smart money bearish → reinforce SHORT signals
  ตรงข้ามกับ global ratio = smart money vs retail divergence
```

## Output Signal
```
{
  direction: "CROWD_LONG" | "CROWD_SHORT" | "BALANCED",
  strength: 0.0 — 1.0,
  oi_change_pct: float,
  oi_interpretation: "REAL_BUYING" | "SHORTS_STACKING" | "SHORT_COVER" | "LONG_LIQ",
  long_short_ratio: float,
  funding_rate: float,
  funding_signal: "LONGS_EXPENSIVE" | "SHORTS_EXPENSIVE" | "NEUTRAL",
  liq_proximity_score: float,
  nearest_liq_cluster: float | null,
  liq_direction: "ABOVE" | "BELOW" | null,
  top_trader_long_pct: float,
  extreme_level: 0.0 — 1.0
}
```

---

# 9. E5 — Regime Filter (8%)

## หน้าที่
**ไม่ใช่ signal generator** — เป็น filter และ weight adjuster
กรองว่าตลาดเทรดได้ไหม และปรับพฤติกรรมของระบบตาม market state

## ทำงาน: ทุก 30 วินาที

## การจำแนก Regime

### 9.1 Volatility Regime
```
ใช้ ATR(14) บน 3m candle:

atr_pct = ATR / price × 100  (% ของ price)
atr_history = ค่า atr_pct ใน 24 ชั่วโมงที่ผ่านมา

percentile_20 = percentile ที่ 20 ของ atr_history
percentile_80 = percentile ที่ 80 ของ atr_history

if atr_pct < percentile_20:
  regime = "LOW_VOL"
  → TP เล็กลง 20%, SL แคบลง 20%, Leverage ลดลง 1-2x
  
elif atr_pct < percentile_80:
  regime = "NORMAL_VOL"
  → ใช้ parameters ปกติ
  
elif atr_pct < percentile_95:
  regime = "HIGH_VOL"
  → TP ใหญ่ขึ้น 30%, SL กว้างขึ้น 30%, E1/E2 weight ขึ้น
  
else:
  regime = "EXTREME_VOL"
  → ⛔ STOP TRADING (Flash crash / pump zone — unpredictable)
```

### 9.2 Trend Phase
```
ใช้ ADX(14) + EMA slope บน 3m:

ADX(14):
  +DI = Directional Movement Plus
  -DI = Directional Movement Minus
  DX  = |(+DI - -DI)| / (+DI + -DI) × 100
  ADX = EMA(14) ของ DX

if ADX > 25 AND EMA slope ชัดเจน:
  phase = "TRENDING"
  → เน้น Strategy A (Momentum), เพิ่ม E3 weight
  
elif ADX > 20 AND price อยู่ใน range:
  phase = "RANGING"
  → เน้น Strategy B (Mean Revert), เพิ่ม E4 weight
  
else (ADX < 20):
  phase = "CHOPPY"
  → ⚠️ REDUCE trades มาก หรือ หยุด
  → CHOPPY = signal ไม่น่าเชื่อถือ, fee กินกำไร
```

### 9.3 Spread Monitor
```
spread = (best_ask - best_bid) / best_bid × 100  (%)

ถ้า spread > 0.015%:
  → ⛔ ไม่เข้าไม้ใหม่จนกว่า spread จะกลับมาปกติ
  
เหตุผล: LIMIT Maker entry ที่ spread > 0.015% 
  → TP ขั้นต่ำต้องมากกว่า spread + fee + กำไร
  → ยากขึ้นมากที่จะได้กำไร

spread_history: เก็บ 100 ค่าล่าสุด
avg_spread = mean(spread_history)
current_spread_ratio = current_spread / avg_spread
  > 2.0 = spread กว้างผิดปกติ (liquidity หาย)
```

### 9.4 BTC-ETH Correlation Check
```
ทุก 5 นาที คำนวณ correlation ระหว่าง BTC และ ETH returns:

correlation = pearson_correlation(btc_returns_10m, eth_returns_10m)

ปกติ correlation > 0.8
ถ้า correlation < 0.5 กะทันหัน = decorrelation event
  → RISK-OFF signal → ลด position size 50%
  → อาจมี news / whale activity เฉพาะตัว
```

## Weight Adjustments ที่ส่งกลับ
```
{
  tradeable: true | false,
  reason: string,
  regime: "TRENDING" | "RANGING" | "CHOPPY",
  vol_phase: "LOW" | "NORMAL" | "HIGH" | "EXTREME",
  spread_ok: bool,
  current_spread: float,
  
  weight_overrides: {
    e1: float,  // adjusted weight for this regime
    e2: float,
    e3: float,
    e4: float
  },
  
  param_overrides: {
    tp_multiplier: float,    // 0.8 - 1.5
    sl_multiplier: float,    // 0.8 - 1.3
    leverage_max: int,       // 5 - 12
    size_multiplier: float   // 0.5 - 1.0
  },
  
  preferred_strategy: "A" | "B" | "C" | "ANY" | "NONE"
}
```

---

# 10. S1 — Decision Engine

## หน้าที่
รวม signals จาก 5 engines → ตัดสินใจว่าจะเทรดหรือไม่ → เลือก strategy

## ขั้นตอนการตัดสินใจ

### Step 1: รับ signals
ทุก 100ms รับ latest signal จาก E1-E5

### Step 2: คำนวณ Weighted Score

```
Base weights (default):
  w1 = 0.35  (E1 OrderFlow)
  w2 = 0.25  (E2 Tick)
  w3 = 0.20  (E3 Technical)
  w4 = 0.12  (E4 Sentiment)
  w5 = 0.08  (E5 — ใช้เป็น multiplier ไม่ใช่ weight ตรง)

หลัง E5 ปรับ weights:
  w1, w2, w3, w4 = E5.weight_overrides  (ถ้ามี)
  normalize ให้รวม = 1.0

Convert direction เป็นตัวเลข:
  BUY_PRESSURE / MOMENTUM_LONG / LONG / CROWD_SHORT = +1
  SELL_PRESSURE / MOMENTUM_SHORT / SHORT / CROWD_LONG = -1
  NEUTRAL = 0

Directional score:
  s1 = direction_e1 × strength_e1 × conviction_e1
  s2 = direction_e2 × strength_e2
  s3 = direction_e3 × strength_e3
  s4 = direction_e4 × strength_e4  (inverted ถ้าใช้ contrarian)

final_score = s1×w1 + s2×w2 + s3×w3 + s4×w4

Range: -1.0 ถึง +1.0
  > 0 = LONG bias
  < 0 = SHORT bias
```

### Step 3: Entry Conditions Checklist
```
ต้องผ่านทุกข้อ:

[ ] |final_score| > 0.55  (threshold)
[ ] อย่างน้อย 3 จาก 4 engines (E1-E4) ชี้ทิศทางเดียวกัน
[ ] E1 (primary) ต้องไม่ขัดกับทิศทาง (E1 ≠ opposite direction)
[ ] E5.tradeable = true
[ ] E5.spread_ok = true
[ ] ไม่มี open position ในทิศตรงข้าม (ห้าม hedge)
[ ] จำนวน open positions < max_positions (default: 2)
[ ] ไม่อยู่ใน circuit breaker cooldown
[ ] |score| stability: score ไม่กระโดด > 0.3 ใน 500ms (filter noise)
```

### Step 4: Strategy Selection
```
สร้าง strategy_score สำหรับแต่ละ strategy:

Strategy A (Momentum Ride):
  score_A = 0 (ไม่ qualify จนกว่า...)
  + 0.4 ถ้า E2.velocity_ratio > 2.0
  + 0.3 ถ้า E2.streak >= 8
  + 0.2 ถ้า E1.strength > 0.60
  + 0.1 ถ้า E5.regime = "TRENDING"
  - 0.3 ถ้า E5.regime = "RANGING"

Strategy B (Mean Reversion):
  score_B = 0
  + 0.4 ถ้า E3.rsi < 25 หรือ > 75
  + 0.3 ถ้า E3.bb_zone = "UPPER" หรือ "LOWER"
  + 0.2 ถ้า E1.imbalance > 0.40 (extreme)
  + 0.1 ถ้า E5.phase = "RANGING"
  - 0.3 ถ้า E5.phase = "TRENDING"

Strategy C (Liq Cascade):
  score_C = 0
  + 0.5 ถ้า E4.liq_proximity_score > 0.70
  + 0.3 ถ้า E2.spike_ratio > 2.0
  + 0.2 ถ้า E4.oi_interpretation = "LONG_LIQ" หรือ "SHORT_LIQ"

selected_strategy = argmax(score_A, score_B, score_C)

ถ้า max_strategy_score < 0.4 → NO TRADE (ไม่ match strategy ชัดเจน)
```

### Step 5: Confidence Score
```
confidence = |final_score| × agreement_bonus × strategy_clarity

agreement_bonus = 1.0 + (num_engines_agree - 3) × 0.1
  3 agree = 1.0, 4 agree = 1.1, all 5 = 1.2

strategy_clarity = max(score_A, score_B, score_C) / 1.0

confidence = clamp(confidence × 100, 0, 100)  (เป็น %)
```

## Output
```
{
  action: "LONG" | "SHORT" | "NO_TRADE",
  strategy: "A" | "B" | "C",
  confidence: float (0-100),
  final_score: float,
  engines_agree: int,
  reason: string  (เช่น "E1 strong + E2 momentum burst + trending regime")
}
```

---

# 11. S2 — Risk Manager

## หน้าที่
คำนวณ position size, SL, TP และตรวจสอบ circuit breakers

## 11.1 Position Sizing
```
risk_pct = base risk ต่อไม้

  if confidence >= 80%: risk_pct = 1.5%
  if confidence >= 60%: risk_pct = 1.0%
  if confidence < 60%:  risk_pct = 0.5%

  ถ้า losing streak >= 3: risk_pct × 0.5  (ลดครึ่งนึง)
  ถ้า daily pnl < -1.5%:  risk_pct × 0.5

risk_amount = balance × risk_pct

position_size_usdt = risk_amount / sl_distance_pct

leverage = min(
  position_size_usdt / (balance × 0.1),  // min 10% margin
  E5.param_overrides.leverage_max,        // E5 cap
  12                                      // absolute max
)
leverage = max(leverage, 5)  // min 5x

margin_required = position_size_usdt / leverage
```

### 11.2 Dynamic SL/TP (ATR-Based)
```
atr = E3.atr  (ATR(14) บน 1m candle ปัจจุบัน)
atr_multiplier_sl = E5.param_overrides.sl_multiplier (default 1.0)
atr_multiplier_tp = E5.param_overrides.tp_multiplier (default 1.0)

Strategy A (Momentum):
  sl_distance = atr × 0.8 × atr_multiplier_sl
  tp1_distance = atr × 1.3 × atr_multiplier_tp
  tp2_trail = atr × 0.5  (trailing stop distance)

Strategy B (Mean Revert):
  sl_distance = atr × 1.0 × atr_multiplier_sl
  tp_distance = distance to VWAP หรือ BB middle
  (full close — ไม่ partial)

Strategy C (Liq Cascade):
  sl_distance = distance จาก entry ถึง near side ของ liq cluster
  tp1_distance = atr × 1.0 × atr_multiplier_tp
  tp2_trail = atr × 0.7

Minimum TP check (สำคัญมาก!):
  min_tp = fee_roundtrip + spread + 0.05%  (profit buffer)
  if tp1_distance < min_tp → NO TRADE

R:R Check:
  rr_ratio = tp1_distance / sl_distance
  if rr_ratio < 1.3 → NO TRADE
```

### 11.3 Partial TP Logic
```
Strategy A + C ใช้ Partial TP:
  TP1 (60% of position) = tp1_distance
  TP2 (40% ที่เหลือ) = Trailing Stop

เมื่อถึง TP1:
  → ปิด 60% ทันที (LIMIT order)
  → ขยับ SL ของ 40% ที่เหลือ → breakeven (entry price)
  → เริ่ม trailing: SL = max(SL, price - atr×0.5) อัปเดตทุก 10 วินาที

Strategy B ใช้ Full TP:
  ปิดทั้ง 100% เมื่อถึง target
```

### 11.4 Circuit Breakers
```
ตรวจสอบก่อนทุกไม้:

DAILY_LOSS_LIMIT:
  if daily_loss_pct > 2.5%:
    → หยุดทั้งวัน (reset เที่ยงคืน UTC)
    → Telegram alert: "Daily loss limit reached"

LOSS_STREAK:
  if consecutive_losses >= 3:
    → Cooldown 10 นาที
    → ลด risk_pct เป็น 0.5% ใน 10 trades ต่อมา

HOURLY_LOSS:
  if losses_in_1h >= 5:
    → Cooldown 30 นาที

OVERTRADE_LIMIT:
  if trades_this_hour >= 25:
    → หยุด 1 ชั่วโมง (reset ทุกชั่วโมง)

MAX_POSITIONS:
  if open_positions >= 2:
    → ไม่เปิดไม้ใหม่จนกว่าจะปิดอย่างน้อย 1 ไม้

SPREAD_GATE:
  ดูจาก E5 (ถ้า spread_ok = false → ไม่เทรด)

FEE_ALERT:
  if total_fee_today > gross_profit_today × 0.4:
    → Alert (ไม่หยุด แต่ต้อง review)
```

---

# 12. S3 — Executor

## หน้าที่
ส่งออร์เดอร์จริงไปยัง Binance และ manage open positions

## 12.1 Entry Order
```
Order Type: LIMIT
timeInForce: GTX (Good Till Crossing = Post-Only)
  → ถ้า order จะ execute ทันที (taker) → Binance reject อัตโนมัติ
  → เรา catch rejection → skip trade → ไม่จ่าย taker fee

LONG entry price = best_bid + 1 tick (tick = 0.1 USDT สำหรับ BTC)
SHORT entry price = best_ask - 1 tick

Timeout:
  Strategy A: 5 วินาที (momentum ต้องเข้าเร็ว)
  Strategy B: 10 วินาที (รอได้นานกว่า)
  Strategy C: 5 วินาที (cascade เกิดเร็ว)
  
  ถ้าไม่ fill ใน timeout → cancel order → NO_FILL → บันทึก
```

### 12.2 SL Order (ส่งพร้อมกับ Entry)
```
Order Type: STOP_MARKET
  (ยอมจ่าย taker fee 0.045% เพื่อความแน่ใจว่าจะ fill)
  
LONG SL price = entry_price - sl_distance
SHORT SL price = entry_price + sl_distance

Close Position = true (ปิด position อัตโนมัติ)
```

### 12.3 TP Order
```
Order Type: LIMIT
timeInForce: GTC (Good Till Cancel)

TP1 (60%):
  LONG TP1 = entry_price + tp1_distance
  SHORT TP1 = entry_price - tp1_distance
  quantity = position_size × 0.60

TP2 (40% — เริ่มหลัง TP1 hit):
  Trailing → อัปเดต LIMIT order ทุก 10 วินาที
  
  สำหรับ LONG trailing:
    new_sl = max(current_sl, current_price - trail_distance)
    if new_sl > current_sl:
      cancel old SL order → place new SL order
```

### 12.4 Max Hold Timeout
```
เมื่อเปิด position:
  record open_time = now()

ทุก 30 วินาที check:
  if (now() - open_time) > 20 minutes:
    → Force close ทั้ง position (MARKET order)
    → บันทึก exit_reason = "TIMEOUT"
    → Telegram alert
```

### 12.5 Order State Machine
```
States:
  PENDING_ENTRY → ENTRY_SENT → FILLED | NO_FILL | PARTIAL_FILL
  FILLED → ACTIVE_POSITION
  ACTIVE_POSITION → TP1_HIT → TRAILING | CLOSED_TP1_FULL
  ACTIVE_POSITION → SL_HIT → CLOSED_SL
  ACTIVE_POSITION → TIMEOUT → CLOSED_TIMEOUT
  ACTIVE_POSITION → MANUAL_CLOSE → CLOSED_MANUAL

Partial Fill handling:
  if filled_qty < order_qty × 0.5 → cancel, treat as NO_FILL
  if filled_qty >= order_qty × 0.5 → proceed, adjust SL/TP size
```

---

# 13. 3 Trading Strategies

## Strategy A — Momentum Ride 🚀
- **เมื่อไหร่:** Volume spike + OrderFlow + Tick ชี้ทางเดียวกัน + Trending regime
- **ถือ:** 30 วินาที — 5 นาที

### เงื่อนไข Entry
```
TRIGGER (ต้องมี):
  E2.velocity_ratio > 2.0  AND
  E2.streak >= 8 trades ติดกัน  AND
  E2.volume_spike = true (spike_ratio > 2.5)

CONFIRM (อย่างน้อย 2 จาก 3):
  E1.imbalance > 0.25 ทิศทางเดียวกัน
  E1.cvd_slope agree กับ direction
  E3.ema_trend agree กับ direction
  E3.price ไม่ติด S/R ระยะ < 0.05%

FILTER:
  E5.phase ≠ "CHOPPY"
  E5.vol_phase ≠ "EXTREME"

ENTRY: LIMIT Post-Only at best_bid+1tick (LONG) หรือ best_ask-1tick (SHORT)
       Timeout: 5 วินาที

EXIT:
  TP1 (60%): entry ± ATR×1.3
  TP2 (40%): Trailing stop ATR×0.5
  SL: entry ∓ ATR×0.8
  หลัง TP1 hit → SL ย้ายไป breakeven
  Max hold: 5 นาที สำหรับ strategy นี้
```

### Edge
Momentum burst มักดำเนินต่อสักพักก่อนจะหยุด การเข้าหลัง confirm (ไม่ใช่ตอนเริ่ม) ลดความเสี่ยงของ false signal

---

## Strategy B — Mean Reversion 🔄
- **เมื่อไหร่:** RSI extreme + BB outer + Imbalance extreme + Ranging regime
- **ถือ:** 1 — 10 นาที

### เงื่อนไข Entry
```
TRIGGER (ต้องมี):
  E3.rsi < 25 (LONG) หรือ > 75 (SHORT)  AND
  E3.bb_zone = "LOWER" (LONG) หรือ "UPPER" (SHORT)

CONFIRM (อย่างน้อย 2 จาก 3):
  E1.imbalance extreme > 0.40 (ฝั่งที่กด price)
  E1.cvd_divergence = true (price ไปแต่ CVD ไม่ตาม)
  E3.rsi_divergence = true

FILTER:
  E5.phase = "RANGING"  (ถ้า TRENDING → skip)
  E5.vol_phase ≠ "EXTREME"

ENTRY: LIMIT Post-Only ที่ BB outer band หรือ S/R level ที่ใกล้ที่สุด
       Timeout: 10 วินาที

EXIT:
  TP: ทั้ง 100% ที่ VWAP หรือ BB middle
  SL: นอก BB + ATR×0.3 buffer
  Max hold: 10 นาที
```

### Edge
Mean reversion ใน ranging market มีความน่าจะเป็นสูง เพราะไม่มี trend ที่จะดัน price ออกไปไกล

---

## Strategy C — Liquidation Cascade 💥
- **เมื่อไหร่:** ราคาใกล้ liq cluster + momentum push เข้าหา
- **ถือ:** 30 วินาที — 8 นาที

### เงื่อนไข Entry
```
TRIGGER (ต้องมี):
  E4.liq_proximity_score > 0.70  AND
  E2.volume_spike = true  AND
  E1/E2 momentum ชี้เข้าหา liq cluster

CONFIRM (อย่างน้อย 2 จาก 3):
  E4.oi_change กำลังลด (positions ถูก liquidate)
  E2.big_trade = true
  E1.wall_absorbed = true (wall ถูกกินก่อนเข้า liq zone)

FILTER:
  E5.vol_phase = "NORMAL" หรือ "HIGH" (ต้องมี vol พอ)
  E5.vol_phase ≠ "EXTREME"

ENTRY: LIMIT Post-Only ที่ edge ของ liq zone (ก่อนถึง cluster เล็กน้อย)
       Timeout: 5 วินาที

EXIT:
  TP1 (60%): ผ่าน liq cluster ไป ATR×1.0
  TP2 (40%): Trailing stop ATR×0.7
  SL: ก่อน liq cluster (ถ้า bounce = cascade ไม่เกิด)
  Max hold: 8 นาที
```

### Edge
Liquidation cascade เป็น forced buying/selling — ราคาถูกผลักโดยไม่มีใครต้านได้ชั่วคราว

---

# 14. Data Layer

## 14.1 Redis Schema (Hot Data — อ่าน/เขียนทุก cycle)

| Key Pattern | Type | เก็บอะไร | TTL |
|---|---|---|---|
| `position:{symbol}` | Hash | entry, size, sl, tp1, tp2, strategy, open_time, leverage | ไม่มี (ลบเมื่อปิด) |
| `ticks:{symbol}` | List (Ring) | aggTrade data ล่าสุด 2000 รายการ | ไม่มี |
| `orderbook:{symbol}` | Hash | top 20 bid/ask snapshot ล่าสุด | ไม่มี |
| `candles:{symbol}:{tf}` | Sorted Set | OHLCV data (score = timestamp) | ไม่มี |
| `engine_signals:{symbol}` | Hash | latest signal จาก E1-E4 | ไม่มี |
| `engine_weights:{symbol}` | Hash | current weights หลัง learning | ไม่มี |
| `regime:{symbol}` | Hash | volatility, phase, spread, tradeable | ไม่มี |
| `session` | Hash | trades_today, pnl_today, streak, fee_total, gross_pnl | reset daily |
| `circuit_breaker` | Hash | state (ON/OFF), reason, cooldown_until | ไม่มี |
| `oi:{symbol}` | Hash | current OI + history last 12 readings | ไม่มี |
| `sentiment:{symbol}` | Hash | l/s ratio, funding, top_trader, liq_clusters | ไม่มี |

## 14.2 PostgreSQL Schema (Cold Data — Analytics)

### ตาราง `trades`
```
id                  BIGSERIAL PRIMARY KEY
symbol              VARCHAR(20) NOT NULL
side                VARCHAR(5) NOT NULL          -- LONG/SHORT
strategy            CHAR(1) NOT NULL             -- A/B/C
entry_price         DECIMAL(18,8) NOT NULL
exit_price          DECIMAL(18,8)
size_usdt           DECIMAL(18,2) NOT NULL
leverage            INTEGER NOT NULL
sl_price            DECIMAL(18,8) NOT NULL
tp1_price           DECIMAL(18,8) NOT NULL
tp2_price           DECIMAL(18,8)
pnl_gross           DECIMAL(18,4)
fee_total           DECIMAL(18,4)
pnl_net             DECIMAL(18,4)
confidence          DECIMAL(5,2)                 -- 0-100
engine_signals      JSONB                        -- snapshot ของ signals ตอน entry
final_score         DECIMAL(5,4)
hold_duration_sec   INTEGER
exit_reason         VARCHAR(30)                  -- TP1/TP2/SL/TIMEOUT/MANUAL/EMERGENCY
maker_fills         INTEGER                      -- กี่ fills เป็น maker
taker_fills         INTEGER
entry_time          TIMESTAMPTZ NOT NULL
exit_time           TIMESTAMPTZ
regime_at_entry     VARCHAR(20)
vol_phase_at_entry  VARCHAR(20)

INDEX: (symbol, entry_time)
INDEX: (strategy, entry_time)
INDEX: (exit_reason)
```

### ตาราง `engine_accuracy`
```
id              BIGSERIAL PRIMARY KEY
trade_id        BIGINT REFERENCES trades(id)
engine          VARCHAR(5)       -- E1/E2/E3/E4
signal_dir      VARCHAR(10)      -- direction ที่ engine บอก
signal_strength DECIMAL(4,3)
trade_result    VARCHAR(4)       -- WIN/LOSS
recorded_at     TIMESTAMPTZ DEFAULT NOW()
```

### ตาราง `daily_summary`
```
date                DATE PRIMARY KEY
symbol              VARCHAR(20)
total_trades        INTEGER
wins                INTEGER
losses              INTEGER
no_fills            INTEGER
gross_pnl           DECIMAL(18,4)
total_fees          DECIMAL(18,4)
net_pnl             DECIMAL(18,4)
fee_ratio           DECIMAL(5,4)    -- fee/gross
maker_rate          DECIMAL(5,4)    -- maker fills / total fills
max_drawdown        DECIMAL(5,4)
best_trade_pnl      DECIMAL(18,4)
worst_trade_pnl     DECIMAL(18,4)
avg_hold_sec        DECIMAL(10,2)
avg_confidence      DECIMAL(5,2)
strategy_a_count    INTEGER
strategy_b_count    INTEGER
strategy_c_count    INTEGER
circuit_breaks      INTEGER         -- กี่ครั้งที่ circuit break ทำงาน
```

### ตาราง `weight_history`
```
id          BIGSERIAL PRIMARY KEY
trade_count INTEGER              -- optimized หลัง N trades
e1_weight   DECIMAL(4,3)
e2_weight   DECIMAL(4,3)
e3_weight   DECIMAL(4,3)
e4_weight   DECIMAL(4,3)
win_rate    DECIMAL(5,4)
recorded_at TIMESTAMPTZ DEFAULT NOW()
```

---

# 15. Infrastructure & APIs

## 15.1 VPS Setup

### ขั้นตอน Setup Server
```
1. สั่ง VPS Singapore (แนะนำ Vultr SGP $20/เดือน หรือ DigitalOcean SGP)
2. ติดตั้ง Ubuntu 22.04 LTS
3. Security hardening:
   - เปลี่ยน SSH port
   - ติดตั้ง UFW firewall
   - เปิดเฉพาะ port ที่จำเป็น (SSH, dashboard port)
   - Fail2ban
4. ติดตั้ง Docker + Docker Compose
5. Clone repo + สร้าง .env file ใส่ API keys
6. docker-compose up -d
7. ตรวจสอบ latency: ping fstream.binance.com (ควร < 5ms)
```

### Docker Compose Services
```
services:
  redis:
    image: redis:7-alpine
    volumes: redis_data:/data
    restart: always
    
  postgres:
    image: postgres:15-alpine
    environment: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    volumes: postgres_data:/var/lib/postgresql/data
    restart: always
    
  vortex7:
    build: .
    depends_on: [redis, postgres]
    env_file: .env
    restart: always
    network_mode: host  # สำคัญ — ลด latency
    
  dashboard:
    build: ./dashboard
    ports: "8080:8080"
    depends_on: [postgres, redis]
    restart: always
```

## 15.2 Environment Variables (.env)
```
# Binance API
BINANCE_API_KEY=xxx
BINANCE_SECRET_KEY=xxx
BINANCE_TESTNET=false  # true สำหรับ test

# Trading Config
TRADING_PAIRS=BTCUSDT,ETHUSDT
BASE_BALANCE=500        # USDT
MAX_LEVERAGE=12
RISK_PER_TRADE=0.01    # 1%

# Infrastructure
REDIS_HOST=localhost
REDIS_PORT=6379
POSTGRES_URL=postgresql://user:pass@localhost:5432/vortex7

# Telegram
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# Dashboard
DASHBOARD_SECRET=your_password
```

## 15.3 Latency Test
ก่อน go live ต้อง confirm:
```
1. ping fstream.binance.com → ควรได้ < 5ms
2. ส่ง test order ไป testnet → measure round-trip time → ควร < 50ms
3. WebSocket message delay → ควร < 10ms
ถ้า latency สูงกว่านี้ → เปลี่ยน VPS provider
```

---

# 16. Telegram Bot & Dashboard

## 16.1 Telegram Notifications

### Auto Alerts (บอทส่งเอง)
| Event | ข้อความ |
|---|---|
| เปิดไม้ | `🟢 LONG BTCUSDT\nStrategy: A (Momentum)\nEntry: $43,250\nSL: $43,120 (-0.30%)\nTP1: $43,420 (+0.39%)\nSize: $5,000 (10x)\nConfidence: 73%` |
| TP1 hit | `✅ PARTIAL TP1 — BTCUSDT LONG\n+$10.70 net (60% closed)\nTrailing 40% with SL at breakeven` |
| SL hit | `🔴 STOP LOSS — BTCUSDT LONG\n-$9.30 net\nHold: 2m 15s` |
| Daily summary | `📊 DAILY REPORT\nTrades: 18 | Wins: 11 | Losses: 7\nGross: +$165.40 | Fee: -$32.40\nNET: +$133.00 | Win Rate: 61%\nMaker Rate: 87%` |
| Circuit break | `⚠️ CIRCUIT BREAKER\n3 consecutive losses\nCooldown: 10 minutes` |
| Emergency | `🚨 EMERGENCY — All positions closed\nReason: WebSocket disconnected > 5s` |

### Commands
| Command | ทำอะไร |
|---|---|
| `/status` | ดู open positions, balance, daily P&L |
| `/stop` | หยุดเปิดไม้ใหม่ (ไม่ปิด positions ที่มีอยู่) |
| `/start` | เริ่มเปิดไม้ใหม่อีกครั้ง |
| `/close_all` | ปิดทุก position ทันที (MARKET) |
| `/stats` | ดูสถิติสะสม (win rate, fee ratio, avg hold) |
| `/balance` | ดู balance ปัจจุบัน |
| `/engines` | ดู signals ล่าสุดจากทุก engine |

## 16.2 Web Dashboard (FastAPI)
```
หน้า Dashboard แสดง:
  - P&L Chart (รายวัน, รายสัปดาห์, รายเดือน)
  - Real-time: current positions, live signals
  - Trade History: ตาราง trades ทั้งหมด + filter
  - Engine Performance: accuracy % ของแต่ละ engine
  - Fee Analysis: fee ratio, maker vs taker breakdown
  - KPI Monitor: win rate, R:R, drawdown
  - Regime Status: current market phase
  
Security: HTTP Basic Auth (DASHBOARD_SECRET ใน .env)
Port: 8080 (เปิดเฉพาะ IP ที่อนุญาต)
```

---

# 17. Learning Module

## หน้าที่
ปรับ engine weights และ parameters อัตโนมัติตาม historical performance
**ใช้ Rule-based ไม่ใช่ ML** — ง่ายกว่า debug ง่ายกว่า ไม่ overfit

## ทำงาน: ทุก 100 trades

### Step 1: คำนวณ Engine Accuracy
```
สำหรับแต่ละ engine E1-E4:
  trades_where_engine_signaled = ดูจาก engine_accuracy table
  correct_signals = trades ที่ engine ชี้ถูกทิศ AND trade เป็น WIN
  
  accuracy_e1 = correct_signals_e1 / trades_where_e1_signaled
  (ทำซ้ำสำหรับทุก engine)
```

### Step 2: ปรับ Weights
```
target_weight = accuracy / Σ(all_accuracies)  // proportional to accuracy

adjustment = (target_weight - current_weight) × 0.3  // เคลื่อนที่ 30% ของ gap

new_weight = current_weight + adjustment
new_weight = clamp(new_weight, 0.05, 0.60)  // floor 5%, cap 60%

ทำ normalize ให้รวม = 1.0 หลังจากปรับทุกตัว

ขอบเขตการเปลี่ยนแปลงต่อรอบ:
  |new_weight - old_weight| ≤ 0.05  // กัน overfit
```

### Step 3: ปรับ Parameters (ทุก 200 trades)
```
ตรวจสอบ:
  if avg_hold > 12 min:       → เพิ่ม threshold ±0.02 (เข้าน้อยลง แต่ชัวร์กว่า)
  if win_rate < 50%:          → เพิ่ม threshold +0.03
  if fee_ratio > 0.35:        → เพิ่ม min_tp_multiplier × 1.1
  if maker_rate < 0.70:       → ลด entry_offset (รอ fill นานขึ้น)
  if avg_rr < 1.2:            → เพิ่ม tp_multiplier × 1.05

บันทึก parameter version ทุกครั้ง (สามารถ rollback ได้)
```

---

# 18. โครงสร้างโปรเจค

```
vortex7/
│
├── .env                          # API keys + config (ไม่ commit ขึ้น git)
├── .env.example                  # Template สำหรับ config
├── docker-compose.yml            # Services: bot, redis, postgres, dashboard
├── Dockerfile                    # Bot container
├── requirements.txt              # Python dependencies
├── README.md
│
├── config/
│   ├── settings.py               # Load .env + global constants
│   ├── strategies.py             # TP/SL/timeout params สำหรับ A/B/C
│   └── pairs.py                  # Active pairs + pair-specific overrides
│
├── core/
│   ├── data_hub.py               # E0: WebSocket manager + Redis writer
│   ├── decision_engine.py        # S1: Signal aggregation + strategy select
│   ├── risk_manager.py           # S2: Sizing, SL/TP calc, circuit breakers
│   └── executor.py               # S3: Order management, position tracking
│
├── engines/
│   ├── base.py                   # Abstract Engine class
│   ├── orderflow_engine.py       # E1 (35%) — Orderbook analysis
│   ├── tick_engine.py            # E2 (25%) — Trade flow analysis
│   ├── technical_engine.py       # E3 (20%) — Fast indicators
│   ├── sentiment_engine.py       # E4 (12%) — OI, L/S, liq zones
│   └── regime_filter.py          # E5 (8%) — Market state filter
│
├── strategies/
│   ├── base.py                   # Abstract Strategy class
│   ├── momentum_ride.py          # Strategy A
│   ├── mean_reversion.py         # Strategy B
│   └── liq_cascade.py            # Strategy C
│
├── storage/
│   ├── redis_client.py           # Redis wrapper + helper functions
│   └── database.py               # PostgreSQL wrapper (asyncpg)
│
├── services/
│   ├── telegram_bot.py           # Notifications + commands
│   ├── learning.py               # Weight + parameter optimization
│   └── emergency.py              # Emergency protocol handlers
│
├── dashboard/
│   ├── main.py                   # FastAPI app
│   ├── routes/
│   │   ├── stats.py
│   │   ├── trades.py
│   │   └── engines.py
│   └── static/                   # HTML/CSS/JS frontend
│
├── backtesting/
│   ├── data_downloader.py        # Download historical aggTrade data
│   ├── tick_replay.py            # Replay historical data
│   ├── backtest_engine.py        # Simulate strategies
│   └── optimizer.py              # Grid search for parameters
│
├── utils/
│   ├── indicators.py             # EMA, RSI, MACD, ATR, BB, VWAP
│   ├── orderbook_math.py         # Imbalance, CVD, wall detection
│   ├── logger.py                 # Structured logging (JSON)
│   └── helpers.py                # Misc utilities
│
└── main.py                       # Entry point — wires everything, starts bot
```

---

# 19. แผนพัฒนา 4 Phases

## Phase 1 — Foundation + Primary Signals (4-6 วัน)

### เป้าหมาย: ระบบเทรดได้จริงด้วย E1 + E2 เท่านั้น

| Task | รายละเอียด |
|---|---|
| Docker Setup | Redis + PostgreSQL containers |
| Data Hub | WebSocket connections สำหรับ BTCUSDT: aggTrade + depth + kline |
| Redis Schema | ตั้ง data structures ทั้งหมด |
| E1 Order Flow | Imbalance, CVD, Wall detection, Spoof filter |
| E2 Tick Engine | Velocity, momentum burst, volume spike |
| Basic Decision | ถ้า E1 + E2 agree + strong → trade |
| Basic Risk | Fixed 1% risk, ATR SL/TP |
| Executor | LIMIT Post-Only entry, STOP SL, LIMIT TP |
| PostgreSQL | trades table + basic insert |
| Telegram basic | แจ้ง open/close |
| **TEST** | **Binance Futures Testnet (ไม่ใช้เงินจริง)** |

**Checkpoint**: ระบบส่งออร์เดอร์ได้, บันทึก trades, Maker fill rate > 70%

---

## Phase 2 — Full Engines + Strategies (5-7 วัน)

### เป้าหมาย: ระบบสมบูรณ์ทุก engine + ทดสอบ backtest

| Task | รายละเอียด |
|---|---|
| E3 Technical | EMA, RSI, MACD, VWAP, BB, S/R levels |
| E4 Sentiment | REST polling: OI, L/S, Funding, Liq clusters |
| E5 Regime | ATR regime, ADX trend phase, spread monitor |
| Decision v2 | Weighted aggregation + strategy selection |
| Strategy A | Momentum Ride complete implementation |
| Strategy B | Mean Reversion complete |
| Strategy C | Liq Cascade complete |
| Risk v2 | Confidence-based sizing, partial TP, dynamic SL |
| Circuit Breakers | Daily loss, streak, overtrade, spread gate |
| Backtest | Download 30 วัน historical tick data, run simulation |
| Parameter tuning | ปรับ threshold, ATR multipliers จาก backtest |

**Checkpoint**: Backtest 30 วัน → Profit Factor > 1.3, Fee Ratio < 35%

---

## Phase 3 — Safety + Monitoring (3-4 วัน)

### เป้าหมาย: ระบบ production-ready ปลอดภัย

| Task | รายละเอียด |
|---|---|
| Telegram full | ทุก commands + auto alerts |
| Emergency protocol | WS disconnect, API slow, price gap, balance drop |
| Web Dashboard | FastAPI + P&L charts + trade history |
| Learning Module | Weight optimization ทุก 100 trades |
| Fee tracking | Maker rate %, fee ratio dashboard |
| Logging | Structured JSON logs ทุก event |
| Backup | PostgreSQL daily backup script |
| Load testing | ทดสอบว่ารับได้ถ้า trades เยอะ |
| **Paper Trade** | **Real market data, เปิด position $10-20 (testnet หรือ real account เงินน้อย)** |

**Checkpoint**: Paper trade 5-7 วัน → ไม่มี crash, circuit breakers ทำงานถูก

---

## Phase 4 — Go Live 🔴

### กฎการ scale up
```
สัปดาห์ 1:
  Balance: $100-200
  คู่เทรด: BTCUSDT อย่างเดียว
  Leverage: 5x เท่านั้น
  เป้า: profitable + Maker rate > 80% + ไม่มี emergency
  
สัปดาห์ 2:
  เพิ่ม ETHUSDT ถ้า BTCUSDT ผ่าน
  Leverage: ขึ้นถึง 8x ถ้า win rate > 55%
  
เดือน 1:
  Review weights ทุก 100 trades
  เพิ่ม capital ถ้า net positive
  Target: 5-10% monthly return
  
หยุดและ review ถ้า:
  Fee > 40% of gross profit
  Win rate < 50% หลัง 200 trades
  Max drawdown > 5% ใน 1 สัปดาห์
```

---

# 20. KPI & Monitoring

## KPI หลักที่ต้อง Track ตลอด

| KPI | เป้าหมาย | อันตราย | วิธีคำนวณ |
|---|---|---|---|
| Win Rate | > 55% | < 48% | wins / total_trades |
| Fee Ratio | < 30% | > 45% | total_fee / gross_profit |
| Avg Hold Time | 1-8 นาที | > 15 นาที | avg(hold_duration_sec) / 60 |
| Profit Factor | > 1.4 | < 1.1 | gross_wins / gross_losses |
| Max Drawdown | < 5% | > 8% | max(peak - trough) / peak |
| Maker Rate | > 80% | < 60% | maker_fills / total_fills |
| Avg R:R | > 1.3 | < 1.0 | avg(pnl_win) / avg(|pnl_loss|) |
| Trades/Day | 15-30 | > 50 | count(trades) per day |
| Daily Net P&L | > 0.5% | < -1% | net_pnl / balance |
| No-Fill Rate | < 30% | > 50% | no_fills / entry_attempts |

## เมื่อ KPI ผิดปกติ

| สัญญาณ | สาเหตุที่เป็นไปได้ | แก้ไข |
|---|---|---|
| Maker rate ต่ำ | Spread กว้าง หรือ price เคลื่อนเร็วมาก | เพิ่ม entry_offset, เพิ่ม timeout |
| Fee ratio สูง | TP เล็กเกินไป หรือ SL ชนบ่อยก่อน TP | เพิ่ม min TP threshold |
| Win rate ต่ำ | Threshold ต่ำเกิน หรือ engine ไม่แม่น | เพิ่ม threshold, ตรวจ engine accuracy |
| Hold time นานเกิน | Market ไม่ reach TP | ลด TP target, หรือเพิ่ม SL trail sensitivity |
| No-fill rate สูง | Timeout สั้นเกิน หรือ market เร็วเกิน | ปรับ entry offset strategy |

---

# 21. สูตรคณิตศาสตร์ทั้งหมด

## Signal Aggregation
```
final_score = Σᵢ (dirᵢ × strengthᵢ × reliabilityᵢ × wᵢ)

เมื่อ:
  dirᵢ ∈ {-1, 0, +1}
  strengthᵢ ∈ [0, 1]
  reliabilityᵢ = engine accuracy จาก learning module ∈ [0.5, 1.0]
  wᵢ = engine weight, Σwᵢ = 1
```

## Position Sizing (Kelly-inspired, Conservative)
```
f = (p × b - q) / b

เมื่อ:
  p = win probability (จาก historical win rate)
  q = 1 - p
  b = avg_win / avg_loss (R:R ratio)

Conservative fraction = f × 0.25  (Quarter Kelly — ป้องกัน ruin)
risk_pct = min(Conservative fraction, max_risk_pct)
```

## ATR Calculation
```
TRₜ = max(Hₜ - Lₜ, |Hₜ - Cₜ₋₁|, |Lₜ - Cₜ₋₁|)
ATR(14)ₜ = ATR(14)ₜ₋₁ × (13/14) + TRₜ × (1/14)
```

## EMA
```
k = 2 / (n + 1)
EMA(n)ₜ = Cₜ × k + EMA(n)ₜ₋₁ × (1 - k)
```

## Bollinger Bands
```
SMA(20)ₜ = (1/20) × Σ Cₜ₋ᵢ  (i=0 to 19)
σₜ = √[(1/20) × Σ (Cₜ₋ᵢ - SMA)²]
Upper = SMA + 2σ
Lower = SMA - 2σ
BB_Width = (Upper - Lower) / SMA
```

## RSI
```
Gainᵢ = max(Cᵢ - Cᵢ₋₁, 0)
Lossᵢ = max(Cᵢ₋₁ - Cᵢ, 0)
AvgGain = EMA(14) of Gain
AvgLoss = EMA(14) of Loss
RS = AvgGain / AvgLoss
RSI = 100 - (100 / (1 + RS))
```

## VWAP
```
VWAP = Σ(Pᵢ × Vᵢ) / ΣVᵢ

เมื่อ Pᵢ = (Hᵢ + Lᵢ + Cᵢ) / 3 (Typical Price)
Reset ทุก 00:00 UTC
```

## Imbalance Score
```
I = (Σbidᵢ - Σaskᵢ) / (Σbidᵢ + Σaskᵢ)  , i = 1 to 10 levels

I ∈ [-1, +1]
signal threshold: |I| > 0.30
```

## Liquidation Price Estimation
```
Long Liq Price = avg_entry × (1 - (1/leverage) × maintenance_margin_rate)
Short Liq Price = avg_entry × (1 + (1/leverage) × maintenance_margin_rate)

maintenance_margin_rate ≈ 0.95 สำหรับ Binance Futures
```

## Fee Impact on R:R
```
fee_rate_maker = 0.018%  (with BNB)
fee_roundtrip = fee_rate_maker × 2 = 0.036%

Adjusted TP = TP_gross - fee_roundtrip
Adjusted SL = SL_gross + fee_roundtrip

Effective R:R = Adjusted_TP / Adjusted_SL

Must be: Effective R:R ≥ 1.3
```

## Expected Value per Trade
```
EV = (win_rate × avg_net_win) - ((1 - win_rate) × avg_net_loss)

Positive EV condition:
  win_rate > avg_net_loss / (avg_net_win + avg_net_loss)
  
ตัวอย่าง: avg_win=$10.70, avg_loss=$9.30
  break-even win rate = 9.30 / (10.70 + 9.30) = 46.5%
  → ต้องชนะ > 46.5% เท่านั้นถึงได้กำไร
```

---

# สรุป: สิ่งที่ต้องมีก่อนเริ่ม Build

## Checklist ก่อนเริ่ม

```
✅ Binance Account + Futures เปิดแล้ว
✅ API Key สร้างแล้ว (read + futures only, restrict IP)
✅ BNB ในบัญชี Futures (ลด fee 10%)
✅ VPS Singapore (2vCPU / 4GB RAM)
✅ Telegram Bot Token + Chat ID
✅ Binance Futures Testnet API (สำหรับ test)
✅ เข้าใจ concept ทุก engine
✅ เข้าใจ risk management + circuit breakers
```

## ลำดับความสำคัญ

1. **E1 Order Flow** — สำคัญที่สุด ทำก่อน ทดสอบก่อน
2. **Risk Manager** — ต้องสมบูรณ์ก่อน go live เสมอ
3. **Executor + Fee Protection** — LIMIT Post-Only เท่านั้น
4. **Circuit Breakers** — กันหายนะ
5. **Engines อื่นๆ** — เพิ่ม signal quality
6. **Learning Module** — optimize ต่อเมื่อมีข้อมูลพอ

---

*VORTEX-7 Blueprint v1.0 — Binance USDT-M Futures · Sweet Spot Scalping 30s-15min*
*⚠️ Trading involves significant financial risk. Test thoroughly before using real funds.*