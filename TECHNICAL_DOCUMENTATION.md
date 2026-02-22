# TECHNICAL DOCUMENTATION — VORTEX-7 Engine 🧠
> **Version 2.0** | Updated February 2026

เอกสารนี้ครอบคลุมสถาปัตยกรรม, logic, และ data layer ปัจจุบันของระบบ VORTEX-7

---

## 1. สถาปัตยกรรมโดยรวม (System Architecture)

```
 Market Data (WebSocket / REST)
         │
         ▼
┌────────────────────┐      Hot Store
│  VortexBot (async) │ ──► Redis  ◄──── read every 150 ms
│   main.py          │
└────────┬───────────┘
         │ fan-out
   ┌─────┴──────────────────────────────────┐
   │                                         │
   ▼                                         ▼
5 Engines (E1–E5)                 position_monitor_loop
   │                                  (every 2 s)
   ▼                                         │
DecisionEngine                     Close position if
   │                                TP | SL | Time exit
   ▼                                         │
RiskManager                                  ▼
   │ PASS                         log_trade_close (async)
   ▼
Executor  ──► Binance Futures API
   │
   ▼
log_trade_open (async) ──► Supabase (fire-and-forget)
```

**กฎหลัก: ห้าม `await` DB ใน hot path**
ทุก Supabase write ใช้ `asyncio.create_task()` เพื่อให้ event loop ทำงานต่อโดยไม่รอ

---

## 2. Multi-Engine System (E1–E5)

### E1 — Order Flow Engine (Weight: 35%)
วิเคราะห์ Level 2 Orderbook เพื่อหา supply/demand imbalance แบบ real-time

| สูตร | คำอธิบาย |
|------|----------|
| `Imbalance = (BidVol − AskVol) / (BidVol + AskVol)` | ค่า +1 = bid ท่วม, −1 = ask ท่วม |
| `MicroPrice = (BestBid × AskQty + BestAsk × BidQty) / (BidQty + AskQty)` | Fair value ณ ปัจจุบัน |

- **VPIN (Volume-Synchronized P-I-N)**: วัด information asymmetry ระหว่าง buyer/seller
- **OFI Velocity**: อัตราการเปลี่ยน Order Flow Imbalance ต่อนาที

### E2 — Tick Engine (Weight: 25%)
ประมวลผลทุก aggTrade เพื่อวัด momentum

| Metric | ความหมาย |
|--------|----------|
| `Aggressor Ratio = BuyVol / (BuyVol + SellVol)` | > 0.55 = buy pressure |
| `Velocity` | จำนวน trade/วินาที สูง = กำลังจะ expand |
| `Alignment` | สัญญาณ E1 กับ E2 ตรงกันหรือไม่ (เพิ่ม confidence) |

### E3 — Technical Engine (Weight: 20%)
Reality-check ด้วย indicator แบบดั้งเดิม

- **RSI**: Overbought (>70) / Oversold (<30)
- **Bollinger Bands**: Extension ที่ขอบบน/ล่าง = แรงหรือจะกลับ
- **ATR**: ส่งตรงให้ RiskManager ใช้กำหนด SL/TP แบบ dynamic
- **Keltner Channel Squeeze**: ตรวจจับ low-vol periods ก่อน breakout

### E4 — Sentiment Engine (Weight: 12%)
วัด crowd positioning และ smart money

| Signal | Logic |
|--------|-------|
| Long/Short Ratio > 70% Long | → **Short bias** (anticipate long squeeze) |
| Funding Rate > 0.01% | → ฝั่งที่แพงจะถูก squeeze |
| Top Trader vs Global ratio | → แยก institutional จาก retail |

### E5 — Regime Filter (Weight: 8% + Global Switch)
"สมองหลัก" ที่ตัดสินว่าตลาดเหมาะค้าหรือไม่

| Regime | Vol Phase | ผลต่อระบบ |
|--------|-----------|-----------|
| TRENDING_UP / TRENDING_DOWN | NORMAL | เพิ่ม weight E1, E2 |
| RANGING | NORMAL | เพิ่ม weight E3 |
| ANY | EXTREME | **บล็อกเทรดทั้งหมด** |

---

## 3. Core Decision Pipeline

```
Signals (E1–E4) + Regime (E5)
         │
         ▼
  DecisionEngine.evaluate()
  ├─ Final Score = Σ(sᵢ × wᵢ)   [−1.0 → +1.0]
  ├─ Strategy match: A | B | C
  └─ Output: { action, strategy, confidence, final_score }
         │
         ▼
  RiskManager.calculate()
  ├─ Fee/Slippage test
  ├─ R:R floor check (min 0.8)
  ├─ Dynamic leverage (10x–30x)
  ├─ Liquidation protection
  └─ Daily PnL drawdown guard
         │
    PASS │ FAIL ──► log_rejected() → rejected_signals
         ▼
  Executor.execute_trade()
  └─ POST to Binance Futures API
         │
    OK   │ ERROR
         ▼
  log_trade_open() → trade_logs (status=OPEN)
```

### Strategy Types

| Strategy | Trigger | SL/TP |
|----------|---------|-------|
| A — Momentum/Breakout | E1 + E2 conviction สูง | SL แคบมาก |
| B — Mean Reversion | E3 overbought/oversold ใน Ranging | TP กว้าง |
| C — Liquidity Fishing | E4 sentiment extreme + liquidation cluster | SL ปานกลาง |

---

## 4. Database Layer (v2.0)

### Tables

#### `trade_logs` — ตารางหลัก (1 row per trade)

| Column | Type | เติมตอน |
|--------|------|---------|
| `id` | UUID | INSERT |
| `symbol`, `side`, `strategy` | text | INSERT |
| `entry_price`, `quantity`, `leverage` | numeric | INSERT |
| `open_fee_usdt` | numeric | INSERT (taker 0.05% × notional) |
| `sl_price`, `tp_price` | numeric | INSERT |
| `confidence`, `final_score`, `e1_direction`, `e5_regime` | numeric/text | INSERT (signal snapshot) |
| `exit_price`, `closed_at`, `hold_time_s` | numeric/ts | UPDATE เมื่อปิด |
| `close_reason` | text | UPDATE (TP_HIT / SL_HIT / TIME_EXIT) |
| `close_fee_usdt` | numeric | UPDATE |
| `pnl_gross_usdt` | numeric | UPDATE (ก่อนหักค่าธรรมเนียม) |
| `pnl_net_usdt` | **numeric** | **UPDATE (กำไรจริง)** |
| `pnl_pct` | numeric | UPDATE (% เทียบ margin) |
| `status` | text | OPEN → CLOSED / FAILED |

#### `rejected_signals` — บันทึก RiskManager rejects

| Column | Type | คำอธิบาย |
|--------|------|----------|
| `symbol`, `action` | text | สัญญาณที่ถูกปฏิเสธ |
| `rejection_reason` | text | FEE_TOO_HIGH / RR_LOW / DRAWDOWN / COOLDOWN |
| `confidence` | numeric | ความมั่นใจของ DecisionEngine |
| `daily_pnl` | numeric | PnL รายวัน ณ เวลาที่ถูกปฏิเสธ |

### Views ที่ใช้บน Frontend

| View | ใช้สำหรับ |
|------|----------|
| `v_trading_summary` | Dashboard หน้าหลัก (stats รวม) |
| `v_symbol_summary` | Breakdown ต่อ symbol |
| `v_recent_trades` | ตาราง 50 trades ล่าสุด |

### Write Pattern (ป้องกันระบบช้า)

```python
# ✅ Fire-and-forget — loop ไม่หยุดรอ
asyncio.create_task(storage.log_trade_open(data))

# ✅ ปิดไม้ — ใช้ trade_id จาก Redis
trade_id = pos_data.get('trade_id')
asyncio.create_task(storage.log_trade_close(trade_id, close_data))

# ❌ อย่าทำแบบนี้ใน hot path
await storage.log_trade_open(data)  # บล็อก 150 ms loop!
```

---

## 5. Hot Store — Redis Keys

| Key Pattern | ข้อมูล | TTL |
|-------------|--------|-----|
| `position:{symbol}` | open position + trade_id | จนกว่าจะปิด |
| `orderbook:{symbol}` | bids/asks (top 20) | overwrite ทุก tick |
| `ticks:{symbol}` | ring buffer 2,000 trades | rolling |
| `klines:{symbol}:{tf}` | OHLCV 96 candles (1m, 15m) | overwrite |
| `sentiment:{symbol}` | OI, L/S ratio, funding rate | overwrite ทุก 30s |
| `engine_signals:{symbol}` | output ของแต่ละ engine | overwrite |

---

## 6. Infrastructure & Deployment

| Component | เทคโนโลยี | คำอธิบาย |
|-----------|-----------|----------|
| Bot Runtime | Python 3.11 + asyncio | single process, multi-task |
| Market Data | CCXT Pro (WebSocket) | orderbook, trades, klines |
| Hot Store | Redis | latency < 1ms |
| Cold Store | Supabase (PostgreSQL) | write async, never blocks trading |
| Exchange | Binance USD-M Futures | leverage up to 30x |

### Server Recommendations
- **Region**: AWS / Vultr **Singapore (ap-southeast-1)** — ใกล้ Binance matching engine
- **Specs**: 2 vCPU, 4 GB RAM เป็นอย่างน้อย (Redis + Python + network buffer)
- **Docker**: ใช้ `docker-compose.yml` ที่มาพร้อม project เพื่อ Redis
- **Testnet**: ตั้ง `TESTNET=true` ใน `.env` — ใช้ Demo Trading ของ Binance โดยตรงผ่าน CCXT

### Environment Variables (`.env`)
```
BINANCE_API_KEY=...
BINANCE_SECRET_KEY=...
TESTNET=true

SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...

REDIS_HOST=localhost
REDIS_PORT=6379

TRADING_PAIRS=BTCUSDT,ETHUSDT
```

---

## 7. Graceful Shutdown

```
Ctrl-C / SIGTERM
      │
      ▼
_shutdown_event.set()
      │
      ├─ ทุก WebSocket loop ออกจาก while loop
      ├─ trade_loop หยุด
      ├─ position_monitor_loop หยุด
      │
      ▼
_cancel_all_tasks() → gather(return_exceptions=True)
exchange.close()  → ปิด WebSocket sessions
```

---

*VORTEX-7 Technical Manual — Internal Use Only*
