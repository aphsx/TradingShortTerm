"""
AMS Scalper — Adaptive Multi-Signal Scalper for Binance Futures
================================================================
กลยุทธ์ Scalping ที่รวมเทคนิคจากงานวิจัยหลายแหล่ง:

Layer 1 (Trend Bias)   : VWAP + EMA 50 → กำหนดทิศทาง
Layer 2 (Entry Signal) : Bollinger Band Squeeze Breakout + RSI Confirmation
Layer 3 (Risk Mgmt)    : ATR-Adaptive SL/TP + Trailing Stop + Cooldown

คุณสมบัติเด่น:
- VWAP แทน EMA 200 (เร็วกว่า, แม่นกว่าสำหรับ intraday scalping)
- Bollinger Band Squeeze Detection (จับ breakout หลัง volatility ต่ำ)
- ATR-based dynamic SL/TP (ปรับตาม volatility ตลาด)
- Trailing Stop (ล็อคกำไร ไม่ปล่อยให้กำไรหนี)
- Cooldown Timer (ลด overtrading ลดค่า fee)
- Momentum Filter (RSI + Volume)

อ้างอิง:
- VWAP+BB+RSI strategy: Sharpe 1.65, 300% return over 3y (Backtested on BTC 5m)
- ATR-adaptive stops: ลด whipsaw, เพิ่ม win rate
- Mean reversion + breakout hybrid approach
"""

from decimal import Decimal
from collections import deque
from enum import Enum

import numpy as np

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class AMSConfig(StrategyConfig, frozen=True):
    instrument_id: str = "BTCUSDT-PERP.BINANCE"
    bar_type: str = "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL"

    # ═══ Layer 1: Trend Bias ═══
    # EMA for trend direction (replaces EMA 200)
    ema_trend: int = 50           # EMA 50 — เร็วพอสำหรับ scalping
    ema_fast: int = 9             # EMA เร็ว สำหรับ crossover signal
    ema_medium: int = 21          # EMA กลาง สำหรับ crossover signal

    # VWAP settings
    vwap_period: int = 20         # VWAP lookback (20 bars ≈ 20 นาที สำหรับ 1m chart)

    # ═══ Layer 2: Entry Signal ═══
    # Bollinger Bands
    bb_period: int = 20           # BB lookback period
    bb_std: float = 2.0           # จำนวน standard deviations
    bb_squeeze_lookback: int = 50 # จำนวน bars ย้อนหลังที่ดู squeeze

    # RSI — กว้างขึ้นจากเดิม
    rsi_period: int = 14
    rsi_long_min: float = 40.0    # RSI ≥ 40 → bullish momentum (กว้างขึ้นจาก 50)
    rsi_long_max: float = 70.0    # RSI ≤ 70 → ยังไม่ overbought  (กว้างขึ้นจาก 65)
    rsi_short_min: float = 30.0   # RSI ≥ 30 → ยังไม่ oversold    (กว้างขึ้นจาก 35)
    rsi_short_max: float = 60.0   # RSI ≤ 60 → bearish momentum   (กว้างขึ้นจาก 50)

    # Volume confirmation
    rvol_period: int = 20
    rvol_threshold: float = 1.2   # ลดจาก 1.5 → 1.2 เพื่อไม่กรองมากเกินไป

    # ═══ Layer 3: Risk Management ═══
    # ATR-based SL/TP
    atr_period: int = 14          # ATR lookback period
    atr_sl_multiplier: float = 1.5  # SL = ATR × 1.5 (tight for scalping)
    atr_tp_multiplier: float = 2.0  # TP = ATR × 2.0 (R:R = 1.33:1)

    # Trailing Stop
    trailing_activate_pct: float = 0.003  # เปิดใช้ trailing หลังกำไร 0.3%
    trailing_step_pct: float = 0.001      # trailing ทีละ 0.1%

    # Position sizing
    trade_size: float = 0.001     # BTC ต่อ trade

    # Cooldown
    cooldown_bars: int = 5        # รอ 5 bars หลังปิด position ก่อน

    # Max concurrent loss streak before pause
    max_loss_streak: int = 3      # หยุดเทรดหลังขาดทุนติดกัน 3 ครั้ง
    pause_bars_after_streak: int = 30  # หยุด 30 bars (30 นาที)

    # Warmup
    warmup_bars: int = 60         # ลดจาก 210 → 60 (ไม่ต้องรอ EMA 200)

    # ═══ Entry Mode ═══
    # "breakout"  — เข้าเมื่อ BB squeeze breakout
    # "mean_rev"  — เข้าเมื่อราคาหลุด BB แล้ว revert กลับ
    # "hybrid"    — ใช้ทั้งสอง (แนะนำ)
    entry_mode: str = "hybrid"


# ---------------------------------------------------------------------------
# Signal Type
# ---------------------------------------------------------------------------

class SignalType(Enum):
    NONE = 0
    BREAKOUT_LONG = 1
    BREAKOUT_SHORT = 2
    MEAN_REV_LONG = 3
    MEAN_REV_SHORT = 4


# ---------------------------------------------------------------------------
# Indicators — คำนวณเอง ไม่ต้องพึ่ง ta-lib
# ---------------------------------------------------------------------------

def calc_ema(prices: deque | list | np.ndarray, period: int) -> float:
    """EMA — Exponential Moving Average"""
    arr = np.array(prices) if not isinstance(prices, np.ndarray) else prices
    if len(arr) < period:
        return arr[-1] if len(arr) > 0 else 0.0
    k = 2.0 / (period + 1)
    result = arr[0]
    for p in arr[1:]:
        result = p * k + result * (1 - k)
    return float(result)


def calc_rsi(prices: deque | list, period: int) -> float:
    """RSI — Relative Strength Index (Wilder's smoothing)"""
    arr = np.array(prices)
    if len(arr) < period + 1:
        return 50.0
    deltas = np.diff(arr[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1 + rs)))


def calc_atr(highs: deque, lows: deque, closes: deque, period: int) -> float:
    """ATR — Average True Range"""
    h = np.array(highs)
    l = np.array(lows)
    c = np.array(closes)
    if len(h) < period + 1:
        return float(h[-1] - l[-1]) if len(h) > 0 else 0.0

    # True Range = max(H-L, |H-Cprev|, |L-Cprev|)
    tr1 = h[1:] - l[1:]
    tr2 = np.abs(h[1:] - c[:-1])
    tr3 = np.abs(l[1:] - c[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    # EMA smoothing of TR
    atr_val = np.mean(tr[-period:])
    return float(atr_val)


def calc_vwap(closes: deque, volumes: deque, period: int) -> float:
    """VWAP — Volume Weighted Average Price"""
    c = np.array(closes)
    v = np.array(volumes)
    if len(c) < period:
        return float(c[-1]) if len(c) > 0 else 0.0

    c_slice = c[-period:]
    v_slice = v[-period:]
    total_vol = np.sum(v_slice)
    if total_vol == 0:
        return float(c[-1])
    return float(np.sum(c_slice * v_slice) / total_vol)


def calc_bollinger(
    closes: deque, period: int, num_std: float
) -> tuple[float, float, float]:
    """Bollinger Bands — returns (upper, middle, lower)"""
    arr = np.array(closes)
    if len(arr) < period:
        last = float(arr[-1]) if len(arr) > 0 else 0.0
        return (last, last, last)

    window = arr[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window, ddof=1))
    upper = middle + num_std * std
    lower = middle - num_std * std
    return (upper, middle, lower)


def calc_bb_bandwidth(closes: deque, period: int, num_std: float) -> float:
    """Bollinger Band Bandwidth = (Upper - Lower) / Middle"""
    upper, middle, lower = calc_bollinger(closes, period, num_std)
    if middle == 0:
        return 0.0
    return (upper - lower) / middle


def detect_squeeze(
    closes: deque, bb_period: int, bb_std: float, lookback: int
) -> bool:
    """
    Squeeze Detection — BB Bandwidth ต่ำสุดใน N bars ที่ผ่านมา
    = ตลาดอัดตัว → พร้อม breakout
    """
    arr = np.array(closes)
    if len(arr) < bb_period + lookback:
        return False

    bandwidths = []
    for i in range(lookback):
        end_idx = len(arr) - i
        start_idx = end_idx - bb_period
        if start_idx < 0:
            break
        window = arr[start_idx:end_idx]
        mid = np.mean(window)
        std = np.std(window, ddof=1)
        if mid > 0:
            bw = (2 * bb_std * std) / mid
        else:
            bw = 0.0
        bandwidths.append(bw)

    if not bandwidths:
        return False

    current_bw = bandwidths[0]
    min_bw = min(bandwidths)

    # Squeeze = current bandwidth อยู่ในส่วน 20% ล่างของ range
    bw_range = max(bandwidths) - min_bw
    if bw_range == 0:
        return False

    percentile = (current_bw - min_bw) / bw_range
    return percentile < 0.25  # อยู่ในส่วน 25% ล่าง


def calc_rvol(volumes: deque, period: int) -> float:
    """Relative Volume = current volume / average volume"""
    arr = np.array(volumes)
    if len(arr) < period + 1:
        return 0.0
    current = arr[-1]
    avg = np.mean(arr[-(period + 1):-1])
    if avg == 0:
        return 0.0
    return float(current / avg)


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AMSScalper(Strategy):
    """
    Adaptive Multi-Signal Scalper

    ┌──────────────────────────────────────────────────────────────────┐
    │  FLOW:                                                          │
    │                                                                  │
    │  [1] Check Cooldown / Loss Streak                               │
    │       │                                                          │
    │  [2] Layer 1: Trend Bias (VWAP + EMA 50)                       │
    │       │                                                          │
    │  [3] Layer 2: Entry Signal Detection                            │
    │       ├── Breakout: BB Squeeze → Price breaks BB band           │
    │       └── Mean Rev: Price outside BB → reverting to mean        │
    │       │                                                          │
    │  [4] RSI + Volume Confirmation                                  │
    │       │                                                          │
    │  [5] Entry with ATR-based SL/TP                                 │
    │       │                                                          │
    │  [6] Trailing Stop Management                                   │
    │       │                                                          │
    │  [7] Exit: SL / TP / Trailing / Signal Reversal                 │
    └──────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: AMSConfig):
        super().__init__(config)
        self.cfg = config

        # Instrument
        self._instrument_id = InstrumentId.from_str(config.instrument_id)

        # ═══ Data Buffers ═══
        max_buf = max(config.ema_trend, config.bb_period, config.atr_period,
                      config.vwap_period) + config.bb_squeeze_lookback + 20
        self._closes: deque = deque(maxlen=max_buf)
        self._highs: deque = deque(maxlen=max_buf)
        self._lows: deque = deque(maxlen=max_buf)
        self._volumes: deque = deque(maxlen=max_buf)

        # ═══ State ═══
        self._bar_count: int = 0
        self._position_open: bool = False
        self._entry_price: float = 0.0
        self._entry_side: OrderSide | None = None
        self._entry_signal: SignalType = SignalType.NONE

        # ═══ Risk Management State ═══
        self._stop_loss: float = 0.0
        self._take_profit: float = 0.0
        self._trailing_active: bool = False
        self._trailing_stop: float = 0.0
        self._highest_since_entry: float = 0.0
        self._lowest_since_entry: float = float('inf')

        # ═══ Cooldown & Loss Streak ═══
        self._bars_since_last_close: int = 999  # Start ready
        self._consecutive_losses: int = 0
        self._pause_until_bar: int = 0

        # ═══ Previous bar state (for crossover detection) ═══
        self._prev_ema_fast: float = 0.0
        self._prev_ema_medium: float = 0.0
        self._prev_close: float = 0.0
        self._was_squeezed: bool = False

        # ═══ Indicators cache ═══
        self._ema_fast_val: float = 0.0
        self._ema_medium_val: float = 0.0
        self._ema_trend_val: float = 0.0
        self._vwap_val: float = 0.0
        self._rsi_val: float = 50.0
        self._atr_val: float = 0.0
        self._rvol_val: float = 0.0
        self._bb_upper: float = 0.0
        self._bb_middle: float = 0.0
        self._bb_lower: float = 0.0
        self._is_squeeze: bool = False

        # ═══ Stats ═══
        self._total_trades: int = 0
        self._wins: int = 0
        self._losses: int = 0

    # ------------------------------------------------------------------
    # Nautilus Lifecycle
    # ------------------------------------------------------------------

    def on_start(self):
        bar_type = BarType.from_str(self.cfg.bar_type)
        self.subscribe_bars(bar_type)

    def on_stop(self):
        # Log final stats
        if self._total_trades > 0:
            wr = self._wins / self._total_trades * 100
            self.log.info(
                f"AMS Scalper Stats: {self._total_trades} trades, "
                f"W:{self._wins} L:{self._losses} WR:{wr:.1f}%"
            )

    # ------------------------------------------------------------------
    # Main Bar Handler
    # ------------------------------------------------------------------

    def on_bar(self, bar: Bar):
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        volume = float(bar.volume)

        # Buffer data
        self._closes.append(close)
        self._highs.append(high)
        self._lows.append(low)
        self._volumes.append(volume)
        self._bar_count += 1
        self._bars_since_last_close += 1

        # Warmup
        if self._bar_count < self.cfg.warmup_bars:
            return

        # ═══ Calculate ALL indicators ═══
        self._update_indicators()

        # ═══ Position Management ═══
        if self._position_open:
            self._manage_position(close, high, low)
            return

        # ═══ Check Entry ═══
        self._check_entry(close, bar)

        # Save previous state for next bar
        self._prev_ema_fast = self._ema_fast_val
        self._prev_ema_medium = self._ema_medium_val
        self._prev_close = close
        self._was_squeezed = self._is_squeeze

    # ------------------------------------------------------------------
    # Indicator Calculation
    # ------------------------------------------------------------------

    def _update_indicators(self):
        """คำนวณ indicators ทั้งหมดในที่เดียว"""
        cfg = self.cfg

        # EMA
        self._ema_fast_val = calc_ema(self._closes, cfg.ema_fast)
        self._ema_medium_val = calc_ema(self._closes, cfg.ema_medium)
        self._ema_trend_val = calc_ema(self._closes, cfg.ema_trend)

        # VWAP
        self._vwap_val = calc_vwap(self._closes, self._volumes, cfg.vwap_period)

        # RSI
        self._rsi_val = calc_rsi(self._closes, cfg.rsi_period)

        # ATR
        self._atr_val = calc_atr(
            self._highs, self._lows, self._closes, cfg.atr_period
        )

        # Bollinger Bands
        self._bb_upper, self._bb_middle, self._bb_lower = calc_bollinger(
            self._closes, cfg.bb_period, cfg.bb_std
        )

        # Squeeze Detection
        self._is_squeeze = detect_squeeze(
            self._closes, cfg.bb_period, cfg.bb_std, cfg.bb_squeeze_lookback
        )

        # Relative Volume
        self._rvol_val = calc_rvol(self._volumes, cfg.rvol_period)

    # ------------------------------------------------------------------
    # Entry Logic
    # ------------------------------------------------------------------

    def _check_entry(self, close: float, bar: Bar):
        """Multi-signal entry with confirmation layers"""
        cfg = self.cfg

        # ═══ Pre-checks ═══

        # Cooldown check
        if self._bars_since_last_close < cfg.cooldown_bars:
            return

        # Loss streak pause
        if self._bar_count < self._pause_until_bar:
            return

        # ═══ Layer 1: Trend Bias ═══
        # ใช้ VWAP + EMA 50 ร่วมกัน → ทั้งคู่ต้องเห็นด้วย
        vwap_bullish = close > self._vwap_val
        vwap_bearish = close < self._vwap_val
        ema_bullish = close > self._ema_trend_val
        ema_bearish = close < self._ema_trend_val

        bias_long = vwap_bullish and ema_bullish
        bias_short = vwap_bearish and ema_bearish

        if not (bias_long or bias_short):
            return  # No clear trend bias → skip

        # ═══ Layer 2: Signal Detection ═══
        signal = self._detect_signal(close, bias_long, bias_short)

        if signal == SignalType.NONE:
            return

        # ═══ Layer 3: Confirmation ═══
        # RSI confirmation
        r = self._rsi_val
        if signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            if not (cfg.rsi_long_min <= r <= cfg.rsi_long_max):
                return
        elif signal in (SignalType.BREAKOUT_SHORT, SignalType.MEAN_REV_SHORT):
            if not (cfg.rsi_short_min <= r <= cfg.rsi_short_max):
                return

        # Volume confirmation (ต่ำกว่าเดิมเพื่อไม่ miss โอกาส)
        if self._rvol_val < cfg.rvol_threshold:
            return

        # ═══ ENTRY! ═══
        if signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            self._enter(OrderSide.BUY, close, signal)
        elif signal in (SignalType.BREAKOUT_SHORT, SignalType.MEAN_REV_SHORT):
            self._enter(OrderSide.SELL, close, signal)

    def _detect_signal(
        self, close: float, bias_long: bool, bias_short: bool
    ) -> SignalType:
        """
        ตรวจจับสัญญาณเข้าเทรด:
        1. Breakout: หลัง BB Squeeze → ราคาทะลุ BB band
        2. Mean Reversion: ราคาหลุด BB → กลับเข้ามา
        """
        cfg = self.cfg
        mode = cfg.entry_mode

        # ═══ Breakout Signal ═══
        if mode in ("breakout", "hybrid"):
            # ต้อง squeeze ก่อน (หรือ bar ก่อน squeeze)
            if self._was_squeezed or self._is_squeeze:
                # EMA crossover confirmation
                ema_cross_up = (
                    self._prev_ema_fast <= self._prev_ema_medium
                    and self._ema_fast_val > self._ema_medium_val
                )
                ema_cross_down = (
                    self._prev_ema_fast >= self._prev_ema_medium
                    and self._ema_fast_val < self._ema_medium_val
                )

                # Price breaking out of BB
                if bias_long and close > self._bb_upper and ema_cross_up:
                    return SignalType.BREAKOUT_LONG
                if bias_short and close < self._bb_lower and ema_cross_down:
                    return SignalType.BREAKOUT_SHORT

                # Breakout without strict EMA cross (ถ้า squeeze แรง)
                if bias_long and close > self._bb_upper and self._ema_fast_val > self._ema_medium_val:
                    return SignalType.BREAKOUT_LONG
                if bias_short and close < self._bb_lower and self._ema_fast_val < self._ema_medium_val:
                    return SignalType.BREAKOUT_SHORT

        # ═══ Mean Reversion Signal ═══
        if mode in ("mean_rev", "hybrid"):
            # ราคาเคยหลุด BB แล้วกลับเข้ามา → mean revert
            if self._prev_close != 0:
                # Long: ราคา bar ก่อนอยู่ใต้ lower BB → ตอนนี้กลับเข้ามา
                if (bias_long
                    and self._prev_close < self._bb_lower
                    and close > self._bb_lower
                    and self._ema_fast_val > self._ema_medium_val):
                    return SignalType.MEAN_REV_LONG

                # Short: ราคา bar ก่อนอยู่เหนือ upper BB → ตอนนี้กลับลงมา
                if (bias_short
                    and self._prev_close > self._bb_upper
                    and close < self._bb_upper
                    and self._ema_fast_val < self._ema_medium_val):
                    return SignalType.MEAN_REV_SHORT

        return SignalType.NONE

    # ------------------------------------------------------------------
    # Position Management — ATR SL/TP + Trailing
    # ------------------------------------------------------------------

    def _manage_position(self, close: float, high: float, low: float):
        """จัดการ position: SL, TP, Trailing Stop"""

        if self._entry_side == OrderSide.BUY:
            # Track highest
            self._highest_since_entry = max(self._highest_since_entry, high)

            # ═══ Trailing Stop Logic ═══
            unrealized_pct = (close - self._entry_price) / self._entry_price
            if unrealized_pct >= self.cfg.trailing_activate_pct:
                self._trailing_active = True
                # Update trailing stop
                new_trail = self._highest_since_entry * (1 - self.cfg.trailing_step_pct)
                if new_trail > self._trailing_stop:
                    self._trailing_stop = new_trail

            # ═══ Exit Checks ═══
            # Trailing Stop hit
            if self._trailing_active and low <= self._trailing_stop:
                self._close_position(close, "TRAILING_STOP")
                return

            # Fixed SL hit
            if low <= self._stop_loss:
                self._close_position(close, "STOP_LOSS")
                return

            # Fixed TP hit
            if high >= self._take_profit:
                self._close_position(close, "TAKE_PROFIT")
                return

            # ═══ Signal Reversal Exit ═══
            # ถ้า trend เปลี่ยนทิศ → ปิดเลย
            if close < self._vwap_val and close < self._ema_trend_val:
                self._close_position(close, "TREND_REVERSAL")
                return

        elif self._entry_side == OrderSide.SELL:
            # Track lowest
            self._lowest_since_entry = min(self._lowest_since_entry, low)

            # ═══ Trailing Stop Logic ═══
            unrealized_pct = (self._entry_price - close) / self._entry_price
            if unrealized_pct >= self.cfg.trailing_activate_pct:
                self._trailing_active = True
                new_trail = self._lowest_since_entry * (1 + self.cfg.trailing_step_pct)
                if new_trail < self._trailing_stop or self._trailing_stop == 0:
                    self._trailing_stop = new_trail

            # ═══ Exit Checks ═══
            if self._trailing_active and high >= self._trailing_stop:
                self._close_position(close, "TRAILING_STOP")
                return

            if high >= self._stop_loss:
                self._close_position(close, "STOP_LOSS")
                return

            if low <= self._take_profit:
                self._close_position(close, "TAKE_PROFIT")
                return

            if close > self._vwap_val and close > self._ema_trend_val:
                self._close_position(close, "TREND_REVERSAL")
                return

    # ------------------------------------------------------------------
    # Order Execution
    # ------------------------------------------------------------------

    def _enter(self, side: OrderSide, price: float, signal: SignalType):
        """เปิด position พร้อม ATR-based SL/TP"""
        cfg = self.cfg
        atr = self._atr_val

        # ป้องกัน ATR = 0
        if atr <= 0:
            return

        self._position_open = True
        self._entry_price = price
        self._entry_side = side
        self._entry_signal = signal
        self._trailing_active = False
        self._trailing_stop = 0.0
        self._total_trades += 1

        # ═══ ATR-based SL/TP ═══
        if side == OrderSide.BUY:
            self._stop_loss = price - (atr * cfg.atr_sl_multiplier)
            self._take_profit = price + (atr * cfg.atr_tp_multiplier)
            self._highest_since_entry = price
            self._lowest_since_entry = price
        else:
            self._stop_loss = price + (atr * cfg.atr_sl_multiplier)
            self._take_profit = price - (atr * cfg.atr_tp_multiplier)
            self._highest_since_entry = price
            self._lowest_since_entry = price

        # ═══ Submit Order ═══
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=Quantity.from_str(f"{cfg.trade_size:.3f}"),
        )
        self.submit_order(order)

    def _close_position(self, close_price: float, reason: str):
        """ปิด position + update statistics"""
        if self._entry_side is None:
            return

        # Calculate P/L
        if self._entry_side == OrderSide.BUY:
            pnl = close_price - self._entry_price
        else:
            pnl = self._entry_price - close_price

        # Update stats
        if pnl > 0:
            self._wins += 1
            self._consecutive_losses = 0
        else:
            self._losses += 1
            self._consecutive_losses += 1

            # Loss streak check
            if self._consecutive_losses >= self.cfg.max_loss_streak:
                self._pause_until_bar = self._bar_count + self.cfg.pause_bars_after_streak
                self._consecutive_losses = 0  # Reset after pause

        # Submit close order
        close_side = (
            OrderSide.SELL if self._entry_side == OrderSide.BUY
            else OrderSide.BUY
        )
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=close_side,
            quantity=Quantity.from_str(f"{self.cfg.trade_size:.3f}"),
            reduce_only=True,
        )
        self.submit_order(order)

        # Reset state
        self._position_open = False
        self._entry_price = 0.0
        self._entry_side = None
        self._entry_signal = SignalType.NONE
        self._stop_loss = 0.0
        self._take_profit = 0.0
        self._trailing_active = False
        self._trailing_stop = 0.0
        self._highest_since_entry = 0.0
        self._lowest_since_entry = float('inf')
        self._bars_since_last_close = 0
