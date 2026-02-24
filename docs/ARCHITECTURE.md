# Directional Scalping System — Production Architecture Blueprint
**Version:** 2.0 | **Date:** 2026-02-24 | **Target:** Binance Futures (USDT-M)

---

## Table of Contents
1. [System Architecture & Python Optimization](#1-system-architecture)
2. [Market Data Ingestion (The Observer)](#2-the-observer)
3. [Signal Generation (The Brain)](#3-the-brain)
4. [Order Management System (The Core)](#4-the-core)
5. [Trade Execution & Exit Lifecycle (The Profit Maker)](#5-the-profit-maker)
6. [Risk Management & Circuit Breakers (The Shield)](#6-the-shield)
7. [The 2026 Edge (Market Regime & Adversarial Logic)](#7-the-2026-edge)
8. [Migration Path: Python → Rust/Cython Hybrid](#8-migration-path)

---

## Current Codebase Analysis

```
TradingShortTerm/
├── nautilus_backtest/          ← Python backtesting (WORKING)
│   ├── strategies/ams_scalper.py   ← AMS Scalper v2 (692 lines)
│   ├── run_node.py                 ← BacktestNode runner + sweep
│   └── fetch_data.py              ← Binance klines → Parquet catalog
├── mft_engine/                ← Rust engine (SKELETON, ~5KB stubs)
│   └── src/{engine,strategy,risk,executor,data,models}.rs
└── .env                       ← Binance testnet credentials
```

**Key Observations:**
- `ams_scalper.py` is a **backtest-only** strategy (Nautilus Trader). It uses `deque` buffers + NumPy indicators. No live WebSocket, no OMS, no rate limiting.
- `mft_engine/` Rust crate has placeholder structs with `DashMap`, `tokio`, `Polars` deps but zero real logic.
- **Gap to Production:** Need WebSocket ingestion, state-machine OMS, risk engine, and live execution layer.

---

## 1. System Architecture & Python Optimization {#1-system-architecture}

### 1.1 Core Event Loop Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                      MAIN ASYNCIO EVENT LOOP                        │
│                      (uvloop on Linux / asyncio on Windows)          │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │ WS Market│   │ WS User  │   │ REST     │   │ Heartbeat/       │ │
│  │ Data Task│   │ Data Task│   │ Reconcile│   │ ListenKey Renew  │ │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────────────┘ │
│       │              │              │              │               │
│       ▼              ▼              ▼              ▼               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              asyncio.Queue (Event Bus)                         │ │
│  └────────────────────────┬───────────────────────────────────────┘ │
│                           ▼                                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              STRATEGY DISPATCHER (single consumer)             │ │
│  │  1. Update indicators (Numba/Cython)                          │ │
│  │  2. Generate signals                                          │ │
│  │  3. Pass to OMS                                               │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
import asyncio
import signal
from typing import Protocol

# Use uvloop on Linux for ~2-4x throughput
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass  # Windows fallback to default asyncio

class TradingSystem:
    def __init__(self):
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
        self.shutdown_event = asyncio.Event()

    async def run(self):
        tasks = [
            asyncio.create_task(self.market_ws_task(), name="market_ws"),
            asyncio.create_task(self.user_ws_task(), name="user_ws"),
            asyncio.create_task(self.strategy_dispatcher(), name="dispatcher"),
            asyncio.create_task(self.heartbeat_task(), name="heartbeat"),
            asyncio.create_task(self.reconciliation_task(), name="reconcile"),
        ]
        # Graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.shutdown_event.set)

        await self.shutdown_event.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
```

### 1.2 GIL-Avoidance Strategy

| Bottleneck | Solution | Speedup |
|------------|----------|---------|
| EMA/RSI/ATR calc (per-tick) | **Numba `@njit`** on NumPy arrays | 50-100x |
| Order book aggregation | **Rust via PyO3** (see §8) | 200x+ |
| JSON WebSocket parsing | `orjson.loads()` instead of `json.loads()` | 5-10x |
| Bollinger Squeeze detection | **Cython** `.pyx` module | 30-50x |
| Blocking I/O (REST calls) | `aiohttp` (already async) | N/A |

**Numba example for your existing `calc_ema`:**
```python
from numba import njit
import numpy as np

@njit(cache=True)
def calc_ema_fast(prices: np.ndarray, period: int) -> float:
    if len(prices) < period:
        return prices[-1] if len(prices) > 0 else 0.0
    k = 2.0 / (period + 1)
    result = prices[0]
    for i in range(1, len(prices)):
        result = prices[i] * k + result * (1.0 - k)
    return result
```

---

## 2. Market Data Ingestion — The Observer {#2-the-observer}

### 2.1 WebSocket Architecture

```python
import aiohttp
import orjson
import time

class BinanceWSManager:
    """Manages Market Data + User Data WebSocket streams."""

    MARKET_WS = "wss://fstream.binance.com/stream"
    USER_WS   = "wss://fstream.binance.com/ws/"

    def __init__(self, event_queue: asyncio.Queue, symbols: list[str]):
        self.event_queue = event_queue
        self.symbols = symbols
        self._last_agg_trade_id: dict[str, int] = {}  # sequence tracking
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._session: aiohttp.ClientSession | None = None

    async def connect_market_streams(self):
        """Combined stream: aggTrade + bookTicker for all symbols."""
        streams = []
        for s in self.symbols:
            sl = s.lower()
            streams.extend([f"{sl}@aggTrade", f"{sl}@bookTicker"])
        url = f"{self.MARKET_WS}?streams={'/'.join(streams)}"

        while True:
            try:
                self._session = aiohttp.ClientSession()
                async with self._session.ws_connect(url, heartbeat=15) as ws:
                    self._reconnect_delay = 1.0  # reset on success
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = orjson.loads(msg.data)
                            await self._process_market_msg(data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                          aiohttp.WSMsgType.ERROR):
                            break
            except Exception as e:
                print(f"[WS] Market stream error: {e}")
            finally:
                if self._session:
                    await self._session.close()
            # Exponential backoff reconnect
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay
            )

    async def _process_market_msg(self, wrapper: dict):
        stream = wrapper.get("stream", "")
        data = wrapper.get("data", {})
        ts_recv = time.monotonic_ns()

        if "aggTrade" in stream:
            # Sequence gap detection
            symbol = data["s"]
            trade_id = data["a"]
            last_id = self._last_agg_trade_id.get(symbol, trade_id - 1)
            if trade_id > last_id + 1:
                gap = trade_id - last_id - 1
                print(f"[WARN] {symbol} aggTrade gap: {gap} missed")
                # Trigger REST backfill here
            self._last_agg_trade_id[symbol] = trade_id

            await self.event_queue.put({
                "type": "agg_trade",
                "symbol": symbol,
                "price": float(data["p"]),
                "qty": float(data["q"]),
                "is_buyer_maker": data["m"],
                "trade_id": trade_id,
                "event_time": data["E"],
                "ts_recv": ts_recv,
            })

        elif "bookTicker" in stream:
            await self.event_queue.put({
                "type": "book_ticker",
                "symbol": data["s"],
                "bid": float(data["b"]),
                "bid_qty": float(data["B"]),
                "ask": float(data["a"]),
                "ask_qty": float(data["A"]),
                "ts_recv": ts_recv,
            })
```

### 2.2 User Data Stream (Account + Order Updates)

```python
class UserDataStream:
    REST_BASE = "https://fapi.binance.com"

    def __init__(self, api_key: str, event_queue: asyncio.Queue):
        self.api_key = api_key
        self.event_queue = event_queue
        self.listen_key: str = ""

    async def start(self):
        """Create listenKey, connect WS, auto-renew every 30 min."""
        self.listen_key = await self._create_listen_key()
        asyncio.create_task(self._renew_loop())
        await self._connect_user_ws()

    async def _create_listen_key(self) -> str:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.REST_BASE}/fapi/v1/listenKey",
                headers={"X-MBX-APIKEY": self.api_key}
            ) as r:
                return (await r.json())["listenKey"]

    async def _renew_loop(self):
        while True:
            await asyncio.sleep(30 * 60)  # every 30 min
            async with aiohttp.ClientSession() as s:
                await s.put(
                    f"{self.REST_BASE}/fapi/v1/listenKey",
                    headers={"X-MBX-APIKEY": self.api_key}
                )

    async def _connect_user_ws(self):
        url = f"wss://fstream.binance.com/ws/{self.listen_key}"
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=15) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = orjson.loads(msg.data)
                        event_type = data.get("e")
                        if event_type == "ORDER_TRADE_UPDATE":
                            await self.event_queue.put({
                                "type": "order_update",
                                "data": data["o"],
                            })
                        elif event_type == "ACCOUNT_UPDATE":
                            await self.event_queue.put({
                                "type": "account_update",
                                "data": data["a"],
                            })
```

---

## 3. Signal Generation — The Brain {#3-the-brain}

### 3.1 Tick/Volume Bars (replacing time-based candles)

Your current `ams_scalper.py` uses **1-minute time bars**. For MFT scalping, tick/volume bars are superior because they normalize for activity.

```python
from dataclasses import dataclass, field

@dataclass
class VolumeBar:
    open: float = 0.0
    high: float = -float('inf')
    low: float = float('inf')
    close: float = 0.0
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    tick_count: int = 0
    ts_start: int = 0
    ts_end: int = 0

class VolumeBarAggregator:
    """Aggregates aggTrades into volume bars of fixed notional size."""

    def __init__(self, threshold_usd: float = 50_000.0):
        self.threshold = threshold_usd
        self._current = VolumeBar()
        self._accumulated_notional = 0.0

    def on_trade(self, price: float, qty: float,
                 is_buyer_maker: bool, ts: int) -> VolumeBar | None:
        notional = price * qty

        if self._current.tick_count == 0:
            self._current.open = price
            self._current.ts_start = ts

        self._current.high = max(self._current.high, price)
        self._current.low = min(self._current.low, price)
        self._current.close = price
        self._current.volume += qty
        self._current.tick_count += 1
        self._current.ts_end = ts

        if is_buyer_maker:
            self._current.sell_volume += qty  # taker sold
        else:
            self._current.buy_volume += qty   # taker bought

        self._accumulated_notional += notional

        if self._accumulated_notional >= self.threshold:
            completed = self._current
            self._current = VolumeBar()
            self._accumulated_notional = 0.0
            return completed
        return None
```

### 3.2 Core Micro-Trend Indicators

**Order Book Imbalance (OBI)** — from bookTicker stream:
```python
@njit(cache=True)
def order_book_imbalance(bid_qty: float, ask_qty: float) -> float:
    """Returns -1.0 (sell pressure) to +1.0 (buy pressure)."""
    total = bid_qty + ask_qty
    if total == 0:
        return 0.0
    return (bid_qty - ask_qty) / total
```

**Cumulative Volume Delta (CVD)** — from aggTrade stream:
```python
class CVDTracker:
    """Tracks net buying vs selling pressure over rolling window."""

    def __init__(self, window: int = 100):
        self.deltas: deque[float] = deque(maxlen=window)
        self.cumulative: float = 0.0

    def update(self, qty: float, is_buyer_maker: bool) -> float:
        delta = -qty if is_buyer_maker else qty  # taker direction
        self.deltas.append(delta)
        self.cumulative = sum(self.deltas)
        return self.cumulative
```

---

## 4. Order Management System — The Core {#4-the-core}

### 4.1 Order State Machine

```python
from enum import Enum, auto
from dataclasses import dataclass
import time

class OrderState(Enum):
    PENDING_SUBMIT = auto()   # Sent to API, no ACK yet
    NEW = auto()              # ACK received (on book)
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    PENDING_CANCEL = auto()   # Cancel sent, no ACK yet
    CANCELED = auto()
    REJECTED = auto()
    EXPIRED = auto()
    ORPHANED = auto()         # No response after timeout

@dataclass
class ManagedOrder:
    client_order_id: str
    symbol: str
    side: str         # "BUY" / "SELL"
    order_type: str   # "MARKET" / "LIMIT"
    quantity: float
    price: float | None
    state: OrderState = OrderState.PENDING_SUBMIT
    exchange_order_id: int | None = None
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    submit_ts: float = 0.0    # time.monotonic()
    last_update_ts: float = 0.0
    retry_count: int = 0

class OrderMonitor:
    ORPHAN_TIMEOUT_SEC = 5.0
    MAX_RETRIES = 3

    def __init__(self):
        self.orders: dict[str, ManagedOrder] = {}

    def on_order_submitted(self, order: ManagedOrder):
        order.state = OrderState.PENDING_SUBMIT
        order.submit_ts = time.monotonic()
        self.orders[order.client_order_id] = order

    def on_user_data_update(self, data: dict):
        """Called when ORDER_TRADE_UPDATE arrives from User Data Stream."""
        coid = data["c"]  # clientOrderId
        status = data["X"]  # NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED
        order = self.orders.get(coid)
        if not order:
            return  # Unknown order — log warning

        state_map = {
            "NEW": OrderState.NEW,
            "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
            "FILLED": OrderState.FILLED,
            "CANCELED": OrderState.CANCELED,
            "REJECTED": OrderState.REJECTED,
            "EXPIRED": OrderState.EXPIRED,
        }
        order.state = state_map.get(status, order.state)
        order.filled_qty = float(data.get("z", 0))
        order.avg_fill_price = float(data.get("ap", 0))
        order.exchange_order_id = int(data.get("i", 0))
        order.last_update_ts = time.monotonic()

    async def check_orphans(self, rest_client):
        """Periodic check: orders stuck in PENDING_SUBMIT."""
        now = time.monotonic()
        for coid, order in list(self.orders.items()):
            if order.state == OrderState.PENDING_SUBMIT:
                if now - order.submit_ts > self.ORPHAN_TIMEOUT_SEC:
                    # REST fallback: query order status
                    status = await rest_client.get_order(
                        symbol=order.symbol,
                        orig_client_order_id=coid
                    )
                    if status:
                        self.on_user_data_update(status)
                    else:
                        order.state = OrderState.ORPHANED
                        order.retry_count += 1
```

### 4.2 Rate Limit Manager

```python
class RateLimitManager:
    """Tracks Binance API weight consumption to prevent IP bans."""
    # Binance: 2400 weight / minute for futures

    def __init__(self, max_weight: int = 2400, window_sec: int = 60):
        self.max_weight = max_weight
        self.window_sec = window_sec
        self._requests: deque[tuple[float, int]] = deque()  # (timestamp, weight)

    def _purge_old(self):
        cutoff = time.monotonic() - self.window_sec
        while self._requests and self._requests[0][0] < cutoff:
            self._requests.popleft()

    @property
    def current_weight(self) -> int:
        self._purge_old()
        return sum(w for _, w in self._requests)

    def can_request(self, weight: int = 1) -> bool:
        return self.current_weight + weight <= self.max_weight * 0.85  # 15% safety margin

    def record(self, weight: int = 1):
        self._requests.append((time.monotonic(), weight))

    async def wait_if_needed(self, weight: int = 1):
        while not self.can_request(weight):
            await asyncio.sleep(0.5)
        self.record(weight)
```

---

## 5. Trade Execution & Exit Lifecycle — The Profit Maker {#5-the-profit-maker}

### 5.1 Dynamic TP/SL (ATR-Based, Already in Your Code)

Your `ams_scalper.py` already implements ATR-based SL/TP. For **live**, the key change is submitting **server-side** SL/TP orders:

```python
async def place_entry_with_brackets(self, side: str, qty: float,
                                     entry_price: float, atr: float):
    """Atomic entry: MARKET order + server-side SL + TP."""
    sl_mult = self.cfg.atr_sl_multiplier  # 2.0
    tp_mult = self.cfg.atr_tp_multiplier  # 4.0

    if side == "BUY":
        sl_price = round(entry_price - atr * sl_mult, 2)
        tp_price = round(entry_price + atr * tp_mult, 2)
        sl_side, tp_side = "SELL", "SELL"
    else:
        sl_price = round(entry_price + atr * sl_mult, 2)
        tp_price = round(entry_price - atr * tp_mult, 2)
        sl_side, tp_side = "BUY", "BUY"

    # 1. Market entry
    await self.rest.new_order(symbol=self.symbol, side=side,
        type="MARKET", quantity=qty)
    # 2. Stop-Market SL
    await self.rest.new_order(symbol=self.symbol, side=sl_side,
        type="STOP_MARKET", stopPrice=sl_price, quantity=qty,
        reduceOnly=True, workingType="MARK_PRICE")
    # 3. Take-Profit Market
    await self.rest.new_order(symbol=self.symbol, side=tp_side,
        type="TAKE_PROFIT_MARKET", stopPrice=tp_price, quantity=qty,
        reduceOnly=True, workingType="MARK_PRICE")
```

### 5.2 Mathematical Trailing Stop (Volatility-Based)

```python
@njit(cache=True)
def calc_trailing_stop(side_is_long: bool, highest: float, lowest: float,
                       current_atr: float, entry_price: float,
                       activate_atr_mult: float, trail_atr_mult: float,
                       prev_trailing_stop: float) -> tuple[bool, float]:
    """Returns (is_active, stop_price) using real-time ATR."""
    if side_is_long:
        unrealized = highest - entry_price
        activate_dist = current_atr * activate_atr_mult
        if unrealized >= activate_dist:
            new_stop = highest - (current_atr * trail_atr_mult)
            return True, max(new_stop, prev_trailing_stop)
    else:
        unrealized = entry_price - lowest
        activate_dist = current_atr * activate_atr_mult
        if unrealized >= activate_dist:
            new_stop = lowest + (current_atr * trail_atr_mult)
            if prev_trailing_stop <= 0:
                return True, new_stop
            return True, min(new_stop, prev_trailing_stop)
    return False, prev_trailing_stop
```

### 5.3 Maker vs. Taker Exit Logic

```python
def choose_exit_strategy(self, side: str, current_price: float,
                          spread: float, unrealized_pnl: float,
                          urgency: str) -> dict:
    """
    urgency: "SL" → always TAKER (market order, cut losses NOW)
             "TP" → prefer MAKER (limit order inside spread, capture rebate)
             "TRAILING" → TAKER if gap > 1 ATR, else MAKER
    """
    if urgency == "SL":
        return {"type": "MARKET", "reason": "loss_cut_taker"}

    if urgency == "TP":
        # Post limit order 1 tick inside the spread
        if side == "BUY":  # closing a long = sell
            limit_price = current_price - 0.01  # 1 tick better than market
        else:
            limit_price = current_price + 0.01
        return {"type": "LIMIT", "price": limit_price,
                "timeInForce": "GTX",  # post-only (maker guaranteed)
                "reason": "tp_maker_rebate"}

    if urgency == "TRAILING":
        gap_to_trail = abs(current_price - self._trailing_stop)
        if gap_to_trail > self._entry_atr:
            return {"type": "MARKET", "reason": "trail_gap_taker"}
        else:
            return {"type": "LIMIT", "price": self._trailing_stop,
                    "timeInForce": "GTX", "reason": "trail_maker"}
```

---

## 6. Risk Management & Circuit Breakers — The Shield {#6-the-shield}

### 6.1 Dynamic Position Sizing

```python
def dynamic_position_size(balance: float, atr: float, price: float,
                           risk_pct: float = 0.01,
                           sl_atr_mult: float = 2.0,
                           max_position_pct: float = 0.25,
                           leverage: int = 10) -> float:
    """
    Size = (Balance × Risk%) / (ATR × SL_multiplier)
    Capped at max_position_pct of balance.
    """
    risk_amount = balance * risk_pct           # e.g., $10 on $1000
    stop_distance = atr * sl_atr_mult          # e.g., $200 × 2 = $400
    if stop_distance <= 0:
        return 0.0
    raw_qty = risk_amount / stop_distance       # e.g., 0.025 BTC
    max_qty = (balance * max_position_pct * leverage) / price
    return min(raw_qty, max_qty)
```

### 6.2 Circuit Breaker System

```python
@dataclass
class CircuitBreakerState:
    daily_pnl: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0
    peak_balance: float = 0.0
    current_balance: float = 0.0
    session_start: float = 0.0
    avg_latency_ms: float = 0.0
    is_halted: bool = False
    halt_reason: str = ""

class CircuitBreaker:
    def __init__(self, config: dict):
        self.max_daily_loss_pct: float = config.get("max_daily_loss_pct", 0.03)
        self.max_drawdown_pct: float = config.get("max_drawdown_pct", 0.10)
        self.max_consecutive_losses: int = config.get("max_consecutive_losses", 5)
        self.max_daily_trades: int = config.get("max_daily_trades", 50)
        self.max_latency_ms: float = config.get("max_latency_ms", 500.0)
        self.state = CircuitBreakerState()

    def check(self) -> tuple[bool, str]:
        s = self.state
        # 1. Daily loss limit
        if s.peak_balance > 0:
            daily_loss_pct = -s.daily_pnl / s.peak_balance
            if daily_loss_pct >= self.max_daily_loss_pct:
                return False, f"DAILY_LOSS:{daily_loss_pct:.1%}"
        # 2. Max drawdown
        if s.peak_balance > 0:
            dd = (s.peak_balance - s.current_balance) / s.peak_balance
            if dd >= self.max_drawdown_pct:
                return False, f"MAX_DRAWDOWN:{dd:.1%}"
        # 3. Consecutive losses
        if s.consecutive_losses >= self.max_consecutive_losses:
            return False, f"LOSS_STREAK:{s.consecutive_losses}"
        # 4. Daily trade limit
        if s.daily_trades >= self.max_daily_trades:
            return False, f"TRADE_LIMIT:{s.daily_trades}"
        # 5. Latency degradation
        if s.avg_latency_ms > self.max_latency_ms:
            return False, f"LATENCY:{s.avg_latency_ms:.0f}ms"
        return True, "OK"
```

---

## 7. The 2026 Edge {#7-the-2026-edge}

### 7.1 Market Regime Filter

```python
@njit(cache=True)
def detect_regime(closes: np.ndarray, atr_values: np.ndarray,
                  adx_period: int = 14) -> int:
    """
    Returns: 0=CHOPPY (halt), 1=TRENDING (trade), 2=VOLATILE (reduce size)

    Uses ADX + ATR percentile rank:
    - ADX < 20 AND ATR percentile < 30% → CHOPPY → HALT
    - ADX > 25 AND ATR percentile > 50% → TRENDING → TRADE
    - ATR percentile > 90% → VOLATILE → reduce size 50%
    """
    if len(closes) < adx_period * 3:
        return 0
    # Simplified ADX calculation
    n = adx_period
    highs = closes  # placeholder — use actual H/L in production
    plus_dm = np.maximum(np.diff(highs), 0)
    minus_dm = np.maximum(-np.diff(highs), 0)
    # ... (full ADX impl)
    atr_pctile = np.searchsorted(np.sort(atr_values[-100:]),
                                  atr_values[-1]) / 100.0
    # Simplified regime decision
    if atr_pctile < 0.30:
        return 0  # CHOPPY
    elif atr_pctile > 0.90:
        return 2  # VOLATILE
    return 1      # TRENDING
```

### 7.2 Liquidity Sweep / Stop Run Detection

```python
class LiquiditySweepDetector:
    """
    Detects failed breakouts (stop runs) to enter against trapped traders.

    Pattern: Price breaks key level → high volume → immediate reversal
    This is the "adversarial" edge against retail breakout bots.
    """
    def __init__(self, lookback: int = 20, volume_spike_mult: float = 2.0,
                 reversal_bars: int = 3):
        self.lookback = lookback
        self.vol_mult = volume_spike_mult
        self.reversal_bars = reversal_bars

    def detect(self, highs: np.ndarray, lows: np.ndarray,
               closes: np.ndarray, volumes: np.ndarray,
               avg_volume: float) -> dict | None:
        if len(closes) < self.lookback + self.reversal_bars:
            return None
        # 1. Find recent swing high/low
        recent_high = np.max(highs[-self.lookback:-self.reversal_bars])
        recent_low = np.min(lows[-self.lookback:-self.reversal_bars])

        # 2. Check if recent bars swept above swing high then reversed
        sweep_bars = highs[-self.reversal_bars:]
        close_bars = closes[-self.reversal_bars:]
        vol_bars = volumes[-self.reversal_bars:]

        # BEARISH sweep (false breakout above swing high)
        if (np.any(sweep_bars > recent_high)              # wick above
            and close_bars[-1] < recent_high               # closed back below
            and np.max(vol_bars) > avg_volume * self.vol_mult):  # volume spike
            return {"type": "BEARISH_SWEEP", "level": recent_high,
                    "signal": "SHORT", "confidence": 0.7}

        # BULLISH sweep (false breakdown below swing low)
        sweep_low_bars = lows[-self.reversal_bars:]
        if (np.any(sweep_low_bars < recent_low)
            and close_bars[-1] > recent_low
            and np.max(vol_bars) > avg_volume * self.vol_mult):
            return {"type": "BULLISH_SWEEP", "level": recent_low,
                    "signal": "LONG", "confidence": 0.7}
        return None
```

---

## 8. Migration Path: Python → Rust/Cython Hybrid {#8-migration-path}

### Phase Plan (aligned with your existing `mft_engine/` Rust crate)

| Phase | Component | Tool | Impact |
|-------|-----------|------|--------|
| **Phase 1** (now) | EMA, RSI, ATR, BB | `Numba @njit` | 50-100x on hot path |
| **Phase 2** (week 2) | VolumeBar aggregator, CVD | `Cython .pyx` | 30x, no GIL |
| **Phase 3** (week 4) | Order Book engine, Sweep detector | `Rust + PyO3` (extend `mft_engine/`) | 200x+, zero-copy |
| **Phase 4** (week 6) | Full signal pipeline | `mft_engine` as Python extension | Full MFT latency |

### Rust/PyO3 Integration (extending your existing `mft_engine/Cargo.toml`)

Add to your existing `Cargo.toml`:
```toml
[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
numpy = "0.22"  # PyO3 numpy bindings

[lib]
name = "mft_engine"
crate-type = ["cdylib"]  # Change from rlib to Python extension
```

Example PyO3 function to replace `detect_squeeze`:
```rust
use pyo3::prelude::*;
use numpy::{PyArray1, PyReadonlyArray1};

#[pyfunction]
fn detect_squeeze_rs(
    closes: PyReadonlyArray1<f64>,
    bb_period: usize,
    bb_std: f64,
    lookback: usize,
) -> bool {
    let arr = closes.as_slice().unwrap();
    if arr.len() < bb_period + lookback { return false; }
    // ... (same logic as Python, but 200x faster)
    // Calculate bandwidths, find percentile
    true
}

#[pymodule]
fn mft_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(detect_squeeze_rs, m)?)?;
    Ok(())
}
```

Build and use from Python:
```bash
cd mft_engine && maturin develop --release
```
```python
# In ams_scalper.py
from mft_engine import detect_squeeze_rs  # Rust-compiled, ~200x faster
```

---

## Quick-Start: Recommended File Structure for Live System

```
TradingShortTerm/
├── nautilus_backtest/        ← Keep as-is for backtesting
├── mft_engine/               ← Rust accelerators (PyO3)
├── live_engine/              ← NEW: Production live system
│   ├── __init__.py
│   ├── main.py               ← asyncio entrypoint (§1)
│   ├── ws_manager.py         ← WebSocket streams (§2)
│   ├── bar_aggregator.py     ← Volume/tick bars (§3.1)
│   ├── indicators.py         ← Numba-accelerated (§1.2)
│   ├── signal_engine.py      ← Brain: regime + sweep + signals (§3, §7)
│   ├── oms.py                ← Order state machine (§4)
│   ├── execution.py          ← REST order placement (§5)
│   ├── risk.py               ← Circuit breakers + sizing (§6)
│   ├── rate_limiter.py       ← API weight tracker (§4.2)
│   └── config.py             ← Pydantic settings
├── .env
└── docs/ARCHITECTURE.md      ← This file
```
