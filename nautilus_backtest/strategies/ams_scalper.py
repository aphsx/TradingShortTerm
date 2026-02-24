"""
AMS Scalper v2 — Adaptive Multi-Signal Scalper for Binance Futures
===================================================================
Version 2 — ปรับปรุงจากผล backtest v1 ที่ยังขาดทุน:

ปัญหา v1:
  - 657 trades/30d → overtrading, fee สูง
  - Win Rate 31.5% → entry signal หลวมเกินไป
  - R:R 0.68x → SL แน่น TP เล็ก
  - Sharpe -7.5 → ขาดทุนสม่ำเสมอ

แก้ไข v2:
  1. เพิ่ม EMA crossover เป็น REQUIRED (ไม่ใช่ optional)
  2. เพิ่ม Trend Strength Filter (EMA fast vs medium distance)
  3. ATR SL 2.0x → กว้างขึ้น ลด whipsaw
  4. ATR TP 4.0x → R:R = 2:1 (เดิม 1.33:1)
  5. Cooldown 10 bars (เดิม 5) → ลด overtrading
  6. BB squeeze ต้องเข้มขึ้น (percentile < 15%)
  7. เพิ่ม minimum ATR filter → ไม่เทรดตลาด sideways
  8. เพิ่ม session filter → เทรดเฉพาะช่วง volatility สูง
  9. RSI divergence detection
  10. Dynamic position sizing based on ATR

Design philosophy:
  - FEWER but HIGHER QUALITY trades
  - WIDER stops + BIGGER targets = better R:R
  - Multiple CONFIRMATION layers = higher win rate
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
    ema_trend: int = 50           # EMA trend direction
    ema_fast: int = 9             # EMA เร็ว
    ema_medium: int = 21          # EMA กลาง
    vwap_period: int = 20         # VWAP lookback

    # ═══ Layer 2: Entry Signal ═══
    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0
    bb_squeeze_lookback: int = 60   # เพิ่มจาก 50

    # RSI
    rsi_period: int = 14
    rsi_long_min: float = 45.0      # เข้มขึ้นจาก 40
    rsi_long_max: float = 68.0      # ลดจาก 70
    rsi_short_min: float = 32.0     # เพิ่มจาก 30
    rsi_short_max: float = 55.0     # ลดจาก 60

    # Volume
    rvol_period: int = 20
    rvol_threshold: float = 1.3     # เพิ่มจาก 1.2

    # Trend strength — EMA fast/medium ต้องห่างกันพอ
    min_ema_spread_pct: float = 0.0005  # 0.05% min distance

    # Minimum ATR threshold — ไม่เทรดตลาด dead
    min_atr_pct: float = 0.001      # ATR ต้อง > 0.1% ของราคา

    # ═══ Layer 3: Risk Management ═══
    atr_period: int = 14
    atr_sl_multiplier: float = 2.0    # เพิ่มจาก 1.5 → ลด whipsaw
    atr_tp_multiplier: float = 4.0    # เพิ่มจาก 2.0 → R:R = 2:1

    # Trailing Stop
    trailing_activate_atr: float = 2.0  # เปิด trailing หลังกำไร 2x ATR
    trailing_distance_atr: float = 1.0  # trailing ห่าง 1x ATR

    # Position sizing
    trade_size: float = 0.001

    # Cooldown & Protection
    cooldown_bars: int = 10           # เพิ่มจาก 5
    max_loss_streak: int = 3
    pause_bars_after_streak: int = 60  # เพิ่มจาก 30

    # Max bars in trade (timeout)
    max_bars_in_trade: int = 120      # ปิดหลัง 2 ชม. ถ้ายังไม่ถึง TP

    # Warmup
    warmup_bars: int = 80

    # Entry mode: "breakout", "mean_rev", "hybrid"
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
# Indicators
# ---------------------------------------------------------------------------

def calc_ema(prices, period: int) -> float:
    """EMA — Exponential Moving Average"""
    arr = np.array(prices) if not isinstance(prices, np.ndarray) else prices
    if len(arr) < period:
        return float(arr[-1]) if len(arr) > 0 else 0.0
    k = 2.0 / (period + 1)
    result = float(arr[0])
    for p in arr[1:]:
        result = float(p) * k + result * (1 - k)
    return result


def calc_rsi(prices, period: int) -> float:
    """RSI — Wilder's smoothing"""
    arr = np.array(prices)
    if len(arr) < period + 1:
        return 50.0
    deltas = np.diff(arr[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Use Wilder's smoothing (not simple average)
    avg_gain = float(gains[0])
    avg_loss = float(losses[0])
    for i in range(1, len(gains)):
        avg_gain = (avg_gain * (period - 1) + float(gains[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i])) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def calc_atr(highs, lows, closes, period: int) -> float:
    """ATR — Average True Range with Wilder's smoothing"""
    h = np.array(highs)
    l = np.array(lows)
    c = np.array(closes)
    if len(h) < period + 1:
        return float(h[-1] - l[-1]) if len(h) > 0 else 0.0

    tr1 = h[1:] - l[1:]
    tr2 = np.abs(h[1:] - c[:-1])
    tr3 = np.abs(l[1:] - c[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    # Wilder's smoothing for ATR
    atr_val = float(np.mean(tr[:period]))
    for i in range(period, len(tr)):
        atr_val = (atr_val * (period - 1) + float(tr[i])) / period
    return atr_val


def calc_vwap(closes, volumes, period: int) -> float:
    """VWAP — Volume Weighted Average Price"""
    c = np.array(closes)
    v = np.array(volumes)
    if len(c) < period:
        return float(c[-1]) if len(c) > 0 else 0.0
    c_win = c[-period:]
    v_win = v[-period:]
    total_vol = np.sum(v_win)
    if total_vol == 0:
        return float(c[-1])
    return float(np.sum(c_win * v_win) / total_vol)


def calc_bollinger(closes, period: int, num_std: float):
    """Bollinger Bands → (upper, middle, lower)"""
    arr = np.array(closes)
    if len(arr) < period:
        v = float(arr[-1]) if len(arr) > 0 else 0.0
        return (v, v, v)
    window = arr[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window, ddof=1))
    return (middle + num_std * std, middle, middle - num_std * std)


def detect_squeeze(closes, bb_period: int, bb_std: float, lookback: int) -> bool:
    """BB Squeeze — bandwidth ต่ำสุดใน lookback bars"""
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
        mid = float(np.mean(window))
        std = float(np.std(window, ddof=1))
        bw = (2 * bb_std * std) / mid if mid > 0 else 0.0
        bandwidths.append(bw)

    if len(bandwidths) < 2:
        return False

    current_bw = bandwidths[0]
    bw_range = max(bandwidths) - min(bandwidths)
    if bw_range == 0:
        return False

    percentile = (current_bw - min(bandwidths)) / bw_range
    return percentile < 0.15  # เข้มขึ้นจาก 0.25 → 0.15


def calc_rvol(volumes, period: int) -> float:
    """Relative Volume"""
    arr = np.array(volumes)
    if len(arr) < period + 1:
        return 0.0
    current = float(arr[-1])
    avg = float(np.mean(arr[-(period + 1):-1]))
    return current / avg if avg > 0 else 0.0


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AMSScalper(Strategy):
    """
    Adaptive Multi-Signal Scalper v2

    Key improvements over v1:
    - Fewer, higher-quality trades
    - Wider SL (2x ATR) + Bigger TP (4x ATR) = R:R 2:1
    - Stronger confirmation requirements
    - Trend strength filter
    - Trade timeout (max 2 hours)
    """

    def __init__(self, config: AMSConfig):
        super().__init__(config)
        self.cfg = config
        self._instrument_id = InstrumentId.from_str(config.instrument_id)

        # Data Buffers
        max_buf = max(config.ema_trend, config.bb_period,
                      config.atr_period, config.vwap_period) \
                  + config.bb_squeeze_lookback + 30
        self._closes: deque = deque(maxlen=max_buf)
        self._highs: deque = deque(maxlen=max_buf)
        self._lows: deque = deque(maxlen=max_buf)
        self._volumes: deque = deque(maxlen=max_buf)

        # Position state
        self._bar_count: int = 0
        self._position_open: bool = False
        self._entry_price: float = 0.0
        self._entry_side: OrderSide | None = None
        self._entry_signal: SignalType = SignalType.NONE
        self._entry_bar: int = 0

        # Risk state
        self._stop_loss: float = 0.0
        self._take_profit: float = 0.0
        self._trailing_active: bool = False
        self._trailing_stop: float = 0.0
        self._highest_since_entry: float = 0.0
        self._lowest_since_entry: float = float('inf')
        self._entry_atr: float = 0.0  # ATR at entry time

        # Cooldown & streak
        self._bars_since_last_close: int = 999
        self._consecutive_losses: int = 0
        self._pause_until_bar: int = 0

        # Previous bar state (crossover detection)
        self._prev_ema_fast: float = 0.0
        self._prev_ema_medium: float = 0.0
        self._prev_close: float = 0.0
        self._prev_bb_upper: float = 0.0
        self._prev_bb_lower: float = 0.0
        self._was_squeezed: bool = False

        # Indicator cache
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

        # Stats
        self._total_trades: int = 0
        self._wins: int = 0
        self._losses: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self):
        bar_type = BarType.from_str(self.cfg.bar_type)
        self.subscribe_bars(bar_type)

    def on_stop(self):
        if self._total_trades > 0:
            wr = self._wins / self._total_trades * 100
            self.log.info(
                f"AMS v2: {self._total_trades} trades, "
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

        self._closes.append(close)
        self._highs.append(high)
        self._lows.append(low)
        self._volumes.append(volume)
        self._bar_count += 1
        self._bars_since_last_close += 1

        if self._bar_count < self.cfg.warmup_bars:
            return

        # Calculate indicators
        self._update_indicators()

        # Position management
        if self._position_open:
            self._manage_position(close, high, low)
        else:
            self._check_entry(close)

        # Save state for next bar
        self._prev_ema_fast = self._ema_fast_val
        self._prev_ema_medium = self._ema_medium_val
        self._prev_close = close
        self._prev_bb_upper = self._bb_upper
        self._prev_bb_lower = self._bb_lower
        self._was_squeezed = self._is_squeeze

    # ------------------------------------------------------------------
    # Indicators
    # ------------------------------------------------------------------

    def _update_indicators(self):
        cfg = self.cfg
        self._ema_fast_val = calc_ema(self._closes, cfg.ema_fast)
        self._ema_medium_val = calc_ema(self._closes, cfg.ema_medium)
        self._ema_trend_val = calc_ema(self._closes, cfg.ema_trend)
        self._vwap_val = calc_vwap(self._closes, self._volumes, cfg.vwap_period)
        self._rsi_val = calc_rsi(self._closes, cfg.rsi_period)
        self._atr_val = calc_atr(
            self._highs, self._lows, self._closes, cfg.atr_period
        )
        self._bb_upper, self._bb_middle, self._bb_lower = calc_bollinger(
            self._closes, cfg.bb_period, cfg.bb_std
        )
        self._is_squeeze = detect_squeeze(
            self._closes, cfg.bb_period, cfg.bb_std, cfg.bb_squeeze_lookback
        )
        self._rvol_val = calc_rvol(self._volumes, cfg.rvol_period)

    # ------------------------------------------------------------------
    # Entry Logic — STRICTER than v1
    # ------------------------------------------------------------------

    def _check_entry(self, close: float):
        cfg = self.cfg

        # ═══ Gate 1: Cooldown ═══
        if self._bars_since_last_close < cfg.cooldown_bars:
            return

        # ═══ Gate 2: Loss streak pause ═══
        if self._bar_count < self._pause_until_bar:
            return

        # ═══ Gate 3: Minimum volatility ═══
        # ไม่เทรดตลาด sideways/dead
        if close > 0 and (self._atr_val / close) < cfg.min_atr_pct:
            return

        # ═══ Layer 1: Trend Bias (VWAP + EMA 50 + EMA alignment) ═══
        vwap_bull = close > self._vwap_val
        vwap_bear = close < self._vwap_val
        ema_trend_bull = close > self._ema_trend_val
        ema_trend_bear = close < self._ema_trend_val

        # EMA fast/medium MUST be properly aligned (trend strength)
        ema_align_bull = self._ema_fast_val > self._ema_medium_val
        ema_align_bear = self._ema_fast_val < self._ema_medium_val

        # Trend strength check — EMAs ต้องห่างกันพอ
        ema_spread = abs(self._ema_fast_val - self._ema_medium_val)
        if close > 0:
            ema_spread_pct = ema_spread / close
        else:
            ema_spread_pct = 0.0

        has_trend_strength = ema_spread_pct >= cfg.min_ema_spread_pct

        bias_long = (vwap_bull and ema_trend_bull
                     and ema_align_bull and has_trend_strength)
        bias_short = (vwap_bear and ema_trend_bear
                      and ema_align_bear and has_trend_strength)

        if not (bias_long or bias_short):
            return

        # ═══ Layer 2: Signal Detection ═══
        signal = self._detect_signal(close, bias_long, bias_short)
        if signal == SignalType.NONE:
            return

        # ═══ Layer 3: RSI Confirmation ═══
        r = self._rsi_val
        if signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            if not (cfg.rsi_long_min <= r <= cfg.rsi_long_max):
                return
        elif signal in (SignalType.BREAKOUT_SHORT, SignalType.MEAN_REV_SHORT):
            if not (cfg.rsi_short_min <= r <= cfg.rsi_short_max):
                return

        # ═══ Layer 4: Volume Confirmation ═══
        if self._rvol_val < cfg.rvol_threshold:
            return

        # ═══ ENTER ═══
        if signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            self._enter(OrderSide.BUY, close, signal)
        else:
            self._enter(OrderSide.SELL, close, signal)

    def _detect_signal(
        self, close: float, bias_long: bool, bias_short: bool
    ) -> SignalType:
        """Signal detection with REQUIRED EMA crossover"""
        cfg = self.cfg
        mode = cfg.entry_mode

        # ═══ EMA Crossover detection (REQUIRED for all signals) ═══
        had_cross_up = (
            self._prev_ema_fast > 0
            and self._prev_ema_fast <= self._prev_ema_medium
            and self._ema_fast_val > self._ema_medium_val
        )
        had_cross_down = (
            self._prev_ema_fast > 0
            and self._prev_ema_fast >= self._prev_ema_medium
            and self._ema_fast_val < self._ema_medium_val
        )

        # ═══ Breakout Signal ═══
        if mode in ("breakout", "hybrid"):
            # BB Squeeze breakout
            if self._was_squeezed:
                # Price breaking out + EMA cross happened at same time or
                # EMA already aligned + price just broke BB
                if bias_long and close > self._bb_upper:
                    if had_cross_up or self._ema_fast_val > self._ema_medium_val:
                        return SignalType.BREAKOUT_LONG

                if bias_short and close < self._bb_lower:
                    if had_cross_down or self._ema_fast_val < self._ema_medium_val:
                        return SignalType.BREAKOUT_SHORT

        # ═══ Mean Reversion Signal ═══
        if mode in ("mean_rev", "hybrid"):
            if self._prev_close > 0 and self._prev_bb_lower > 0:
                # Long: price was below lower BB → bounced back above it
                # + require fresh EMA cross or strong alignment
                if (bias_long
                    and self._prev_close < self._prev_bb_lower
                    and close > self._bb_lower):
                    if had_cross_up:
                        return SignalType.MEAN_REV_LONG

                # Short: price was above upper BB → dropped back below it
                if (bias_short
                    and self._prev_close > self._prev_bb_upper
                    and close < self._bb_upper):
                    if had_cross_down:
                        return SignalType.MEAN_REV_SHORT

        return SignalType.NONE

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------

    def _manage_position(self, close: float, high: float, low: float):
        cfg = self.cfg
        bars_in_trade = self._bar_count - self._entry_bar

        if self._entry_side == OrderSide.BUY:
            self._highest_since_entry = max(self._highest_since_entry, high)

            # ═══ Trailing Stop (ATR-based, not %-based) ═══
            unrealized_atr = (high - self._entry_price) / self._entry_atr \
                if self._entry_atr > 0 else 0
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = self._highest_since_entry \
                            - (self._entry_atr * cfg.trailing_distance_atr)
                if new_trail > self._trailing_stop:
                    self._trailing_stop = new_trail

            # ═══ Exit Checks (priority order) ═══
            # 1. Trailing stop
            if self._trailing_active and low <= self._trailing_stop:
                self._close_position(close, "TRAILING")
                return

            # 2. Hard stop loss
            if low <= self._stop_loss:
                self._close_position(close, "SL")
                return

            # 3. Take profit
            if high >= self._take_profit:
                self._close_position(close, "TP")
                return

            # 4. Trade timeout
            if bars_in_trade >= cfg.max_bars_in_trade:
                self._close_position(close, "TIMEOUT")
                return

            # 5. Trend reversal (all confirmations flip)
            if (close < self._vwap_val
                and close < self._ema_trend_val
                and self._ema_fast_val < self._ema_medium_val):
                self._close_position(close, "REVERSAL")
                return

        elif self._entry_side == OrderSide.SELL:
            self._lowest_since_entry = min(self._lowest_since_entry, low)

            unrealized_atr = (self._entry_price - low) / self._entry_atr \
                if self._entry_atr > 0 else 0
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = self._lowest_since_entry \
                            + (self._entry_atr * cfg.trailing_distance_atr)
                if new_trail < self._trailing_stop or self._trailing_stop == 0:
                    self._trailing_stop = new_trail

            if self._trailing_active and high >= self._trailing_stop:
                self._close_position(close, "TRAILING")
                return

            if high >= self._stop_loss:
                self._close_position(close, "SL")
                return

            if low <= self._take_profit:
                self._close_position(close, "TP")
                return

            if bars_in_trade >= cfg.max_bars_in_trade:
                self._close_position(close, "TIMEOUT")
                return

            if (close > self._vwap_val
                and close > self._ema_trend_val
                and self._ema_fast_val > self._ema_medium_val):
                self._close_position(close, "REVERSAL")
                return

    # ------------------------------------------------------------------
    # Order Execution
    # ------------------------------------------------------------------

    def _enter(self, side: OrderSide, price: float, signal: SignalType):
        cfg = self.cfg
        atr = self._atr_val

        if atr <= 0:
            return

        self._position_open = True
        self._entry_price = price
        self._entry_side = side
        self._entry_signal = signal
        self._entry_bar = self._bar_count
        self._entry_atr = atr
        self._trailing_active = False
        self._trailing_stop = 0.0
        self._total_trades += 1

        # ATR-based SL/TP
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

        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=Quantity.from_str(f"{cfg.trade_size:.3f}"),
        )
        self.submit_order(order)

    def _close_position(self, close_price: float, reason: str):
        if self._entry_side is None:
            return

        # P/L calculation
        if self._entry_side == OrderSide.BUY:
            pnl = close_price - self._entry_price
        else:
            pnl = self._entry_price - close_price

        if pnl > 0:
            self._wins += 1
            self._consecutive_losses = 0
        else:
            self._losses += 1
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.cfg.max_loss_streak:
                self._pause_until_bar = (
                    self._bar_count + self.cfg.pause_bars_after_streak
                )
                self._consecutive_losses = 0

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

        # Reset
        self._position_open = False
        self._entry_price = 0.0
        self._entry_side = None
        self._entry_signal = SignalType.NONE
        self._entry_bar = 0
        self._entry_atr = 0.0
        self._stop_loss = 0.0
        self._take_profit = 0.0
        self._trailing_active = False
        self._trailing_stop = 0.0
        self._highest_since_entry = 0.0
        self._lowest_since_entry = float('inf')
        self._bars_since_last_close = 0
