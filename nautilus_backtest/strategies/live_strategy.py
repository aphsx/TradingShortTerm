"""
live_strategy.py — Nautilus Backtest Strategy (mirrors live_engine exactly)
============================================================================
Strategy นี้ port logic จาก live_engine มาทุกส่วน:
  - indicators.py  → calc_ema, calc_rsi, calc_atr, calc_bollinger,
                      detect_squeeze, calc_vwap, calc_rvol, order_book_imbalance
  - signal_engine.py → VolumeBar, CVDTracker, LiquiditySweepDetector,
                        detect_regime, SignalEngine (MarketRegime filter)
  - risk.py        → dynamic_position_size, CircuitBreaker counters

เนื่องจาก Nautilus backtest รับ Bar (OHLCV) ไม่ใช่ tick/aggTrade
จึงปรับดังนี้:
  - ใช้ 5-MINUTE Bar (ตรงกับ live bot จริง)
  - CVD ประมาณจาก (close - open) / range ต่อ bar
  - OBI ไม่มีข้อมูลจริง → ตั้งเป็น 0 (ไม่ boost confidence)
  - CircuitBreaker ใช้ consecutive loss tracker เหมือน live
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

import numpy as np

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


# ═══════════════════════════════════════════════════════════════════════
# Config — mirrors live_engine/config.py TradingConfig
# ═══════════════════════════════════════════════════════════════════════

class LiveStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: str = "BTCUSDT-PERP.BINANCE"
    bar_type: str = "BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"

    # ── Indicator Periods (live_engine/config.py) ──
    ema_fast: int = 9
    ema_medium: int = 21
    ema_trend: int = 50
    rsi_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    bb_squeeze_lookback: int = 60
    vwap_period: int = 20

    # ── Entry Filters ──
    rsi_long_min: float = 45.0
    rsi_long_max: float = 68.0
    rsi_short_min: float = 32.0
    rsi_short_max: float = 55.0
    rvol_threshold: float = 1.3
    min_ema_spread_pct: float = 0.0005
    min_atr_pct: float = 0.001
    entry_mode: str = "hybrid"   # breakout | mean_rev | hybrid

    # ── Risk Management ──
    atr_sl_multiplier: float = 2.0
    atr_tp_multiplier: float = 4.0
    trailing_activate_atr: float = 2.0
    trailing_distance_atr: float = 1.0
    trade_size: float = 0.001            # fixed qty (สำหรับ backtest)

    # ── Circuit Breaker / Cooldown (live_engine/config.py) ──
    cooldown_bars: int = 10
    max_consecutive_losses: int = 5
    pause_bars_after_streak: int = 60
    max_bars_in_trade: int = 120
    max_daily_trades: int = 50

    # ── Liquidity Sweep Detector ──
    sweep_lookback: int = 20
    sweep_vol_spike_mult: float = 2.0
    sweep_reversal_bars: int = 3

    # ── Warmup ──
    warmup_bars: int = 80


# ═══════════════════════════════════════════════════════════════════════
# Enums — identical to live_engine/signal_engine.py
# ═══════════════════════════════════════════════════════════════════════

class SignalType(Enum):
    NONE = 0
    BREAKOUT_LONG = 1
    BREAKOUT_SHORT = 2
    MEAN_REV_LONG = 3
    MEAN_REV_SHORT = 4
    SWEEP_LONG = 5
    SWEEP_SHORT = 6


class MarketRegime(Enum):
    CHOPPY = 0
    TRENDING = 1
    VOLATILE = 2


# ═══════════════════════════════════════════════════════════════════════
# Indicators — pure NumPy (same algorithm as live_engine/indicators.py)
# ═══════════════════════════════════════════════════════════════════════

def calc_ema(prices: np.ndarray, period: int) -> float:
    n = len(prices)
    if n == 0:
        return 0.0
    if n < period:
        return float(prices[-1])
    k = 2.0 / (period + 1)
    result = float(prices[0])
    for p in prices[1:]:
        result = float(p) * k + result * (1.0 - k)
    return result


def calc_rsi(prices: np.ndarray, period: int) -> float:
    n = len(prices)
    if n < period + 1:
        return 50.0
    start = n - period - 1
    avg_gain = 0.0
    avg_loss = 0.0
    delta = prices[start + 1] - prices[start]
    if delta > 0:
        avg_gain = delta
    else:
        avg_loss = -delta
    for i in range(start + 2, n):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            avg_gain = (avg_gain * (period - 1) + delta) / period
            avg_loss = (avg_loss * (period - 1)) / period
        else:
            avg_gain = (avg_gain * (period - 1)) / period
            avg_loss = (avg_loss * (period - 1) + (-delta)) / period
    if avg_loss == 0.0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def calc_atr(highs: np.ndarray, lows: np.ndarray,
             closes: np.ndarray, period: int) -> float:
    n = len(highs)
    if n < 2:
        return float(highs[0] - lows[0]) if n > 0 else 0.0
    if n < period + 1:
        total = 0.0
        for i in range(1, n):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
            total += tr
        return total / max(n - 1, 1)
    atr_val = 0.0
    for i in range(1, period + 1):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        atr_val += tr
    atr_val /= period
    for i in range(period + 1, n):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


def calc_bollinger(closes: np.ndarray, period: int,
                   num_std: float) -> tuple[float, float, float]:
    n = len(closes)
    if n < period:
        v = float(closes[-1]) if n > 0 else 0.0
        return (v, v, v)
    window = closes[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window, ddof=1))
    return (middle + num_std * std, middle, middle - num_std * std)


def detect_squeeze(closes: np.ndarray, bb_period: int,
                   bb_std: float, lookback: int) -> bool:
    n = len(closes)
    if n < bb_period + lookback:
        return False
    bandwidths = []
    for offset in range(lookback):
        end = n - offset
        start = end - bb_period
        if start < 0:
            break
        window = closes[start:end]
        mid = float(np.mean(window))
        if mid <= 0:
            continue
        std = float(np.std(window, ddof=1))
        bw = (2.0 * bb_std * std) / mid
        bandwidths.append(bw)
    if len(bandwidths) < 2:
        return False
    current_bw = bandwidths[0]
    bw_range = max(bandwidths) - min(bandwidths)
    if bw_range <= 0:
        return False
    percentile = (current_bw - min(bandwidths)) / bw_range
    return percentile < 0.15


def calc_vwap(closes: np.ndarray, volumes: np.ndarray, period: int) -> float:
    n = len(closes)
    if n < period:
        return float(closes[-1]) if n > 0 else 0.0
    c_win = closes[-period:]
    v_win = volumes[-period:]
    total_v = float(np.sum(v_win))
    if total_v <= 0:
        return float(closes[-1])
    return float(np.sum(c_win * v_win) / total_v)


def calc_rvol(volumes: np.ndarray, period: int) -> float:
    n = len(volumes)
    if n < period + 1:
        return 0.0
    current = float(volumes[-1])
    avg = float(np.mean(volumes[-(period + 1):-1]))
    return current / avg if avg > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════
# Market Regime Filter — identical to live_engine/signal_engine.py
# ═══════════════════════════════════════════════════════════════════════

def detect_regime(atr_history: np.ndarray, closes: np.ndarray,
                  ema_fast: float, ema_medium: float,
                  ema_trend: float) -> MarketRegime:
    if len(atr_history) < 50:
        return MarketRegime.TRENDING
    current_atr = atr_history[-1]
    sorted_atr = np.sort(atr_history[-100:])
    pctile = np.searchsorted(sorted_atr, current_atr) / len(sorted_atr)
    price = float(closes[-1]) if len(closes) > 0 else 1.0
    max_ema = max(ema_fast, ema_medium, ema_trend)
    min_ema = min(ema_fast, ema_medium, ema_trend)
    ema_range_pct = (max_ema - min_ema) / price if price > 0 else 0
    if pctile < 0.25 and ema_range_pct < 0.0005:
        return MarketRegime.CHOPPY
    if pctile > 0.90:
        return MarketRegime.VOLATILE
    return MarketRegime.TRENDING


# ═══════════════════════════════════════════════════════════════════════
# Liquidity Sweep Detector — identical to live_engine/signal_engine.py
# ═══════════════════════════════════════════════════════════════════════

class LiquiditySweepDetector:
    def __init__(self, lookback: int = 20, vol_spike_mult: float = 2.0,
                 reversal_bars: int = 3):
        self.lookback = lookback
        self.vol_mult = vol_spike_mult
        self.reversal_bars = reversal_bars

    def detect(self, highs: np.ndarray, lows: np.ndarray,
               closes: np.ndarray, volumes: np.ndarray,
               avg_volume: float) -> SignalType:
        n = len(closes)
        needed = self.lookback + self.reversal_bars
        if n < needed:
            return SignalType.NONE
        recent_high = np.max(highs[-needed:-self.reversal_bars])
        recent_low = np.min(lows[-needed:-self.reversal_bars])
        sweep_highs = highs[-self.reversal_bars:]
        sweep_lows = lows[-self.reversal_bars:]
        sweep_closes = closes[-self.reversal_bars:]
        sweep_vols = volumes[-self.reversal_bars:]
        if (np.any(sweep_highs > recent_high)
                and sweep_closes[-1] < recent_high
                and np.max(sweep_vols) > avg_volume * self.vol_mult):
            return SignalType.SWEEP_SHORT
        if (np.any(sweep_lows < recent_low)
                and sweep_closes[-1] > recent_low
                and np.max(sweep_vols) > avg_volume * self.vol_mult):
            return SignalType.SWEEP_LONG
        return SignalType.NONE


# ═══════════════════════════════════════════════════════════════════════
# CVD Approximator (ใช้ Bar แทน aggTrade)
# bar CVD ≈ (close - open) / (high - low) × volume
# ═══════════════════════════════════════════════════════════════════════

class CVDTracker:
    def __init__(self, window: int = 100):
        self.deltas: deque[float] = deque(maxlen=window)
        self.cumulative: float = 0.0

    def update_from_bar(self, open_: float, high: float,
                        low: float, close: float, volume: float) -> float:
        rng = high - low
        if rng > 0:
            buy_ratio = (close - low) / rng
        else:
            buy_ratio = 0.5
        buy_vol = volume * buy_ratio
        sell_vol = volume * (1.0 - buy_ratio)
        delta = buy_vol - sell_vol
        self.deltas.append(delta)
        self.cumulative = sum(self.deltas)
        return self.cumulative


# ═══════════════════════════════════════════════════════════════════════
# The Strategy
# ═══════════════════════════════════════════════════════════════════════

class LiveStrategy(Strategy):
    """
    Nautilus backtest strategy ที่ mirror live_engine ทุกส่วน:
    - MarketRegime filter (CHOPPY → halt, VOLATILE → reduce)
    - LiquiditySweepDetector (adversarial entries)
    - AMS v2 signal logic (breakout / mean_rev / hybrid)
    - ATR-based SL/TP + trailing stop
    - CircuitBreaker counters (consecutive losses, daily trade limit)
    - Cooldown + pause after loss streak
    """

    def __init__(self, config: LiveStrategyConfig):
        super().__init__(config)
        self.cfg = config
        self._instrument_id = InstrumentId.from_str(config.instrument_id)

        # ── Data buffers ──
        max_buf = (max(config.ema_trend, config.bb_period, config.atr_period,
                       config.vwap_period)
                   + config.bb_squeeze_lookback + 50)
        self._closes = np.zeros(max_buf, dtype=np.float64)
        self._highs = np.zeros(max_buf, dtype=np.float64)
        self._lows = np.zeros(max_buf, dtype=np.float64)
        self._volumes = np.zeros(max_buf, dtype=np.float64)
        self._opens = np.zeros(max_buf, dtype=np.float64)
        self._atr_history = np.zeros(200, dtype=np.float64)
        self._buf_idx = 0
        self._atr_idx = 0
        self._bar_count = 0

        # ── Sub-detectors ──
        self.sweep_detector = LiquiditySweepDetector(
            lookback=config.sweep_lookback,
            vol_spike_mult=config.sweep_vol_spike_mult,
            reversal_bars=config.sweep_reversal_bars,
        )
        self.cvd = CVDTracker()

        # ── Previous bar state (for crossover detection) ──
        self._prev_ema_fast: float = 0.0
        self._prev_ema_medium: float = 0.0
        self._prev_close: float = 0.0
        self._prev_bb_upper: float = 0.0
        self._prev_bb_lower: float = 0.0
        self._was_squeezed: bool = False

        # ── Position state ──
        self._position_open: bool = False
        self._entry_price: float = 0.0
        self._entry_side: OrderSide | None = None
        self._entry_bar: int = 0
        self._entry_atr: float = 0.0
        self._stop_loss: float = 0.0
        self._take_profit: float = 0.0
        self._trailing_active: bool = False
        self._trailing_stop: float = 0.0
        self._highest_since_entry: float = 0.0
        self._lowest_since_entry: float = float("inf")

        # ── Circuit breaker / cooldown state (mirrors live_engine) ──
        self._consecutive_losses: int = 0
        self._daily_trades: int = 0
        self._bars_since_last_close: int = 9999
        self._pause_until_bar: int = 0

        # ── Stats ──
        self._total_trades: int = 0
        self._wins: int = 0
        self._losses: int = 0

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────

    def on_start(self):
        bar_type = BarType.from_str(self.cfg.bar_type)
        self.subscribe_bars(bar_type)
        self.log.info(
            f"[LiveStrategy] Started | instrument={self.cfg.instrument_id} "
            f"| mode={self.cfg.entry_mode} | SL={self.cfg.atr_sl_multiplier}x "
            f"| TP={self.cfg.atr_tp_multiplier}x ATR"
        )

    def on_stop(self):
        if self._total_trades > 0:
            wr = self._wins / self._total_trades * 100
            self.log.info(
                f"[LiveStrategy] DONE: trades={self._total_trades} "
                f"W={self._wins} L={self._losses} WR={wr:.1f}%"
            )

    # ─────────────────────────────────────────────────────────────────
    # Main bar handler
    # ─────────────────────────────────────────────────────────────────

    def on_bar(self, bar: Bar):
        close  = float(bar.close)
        high   = float(bar.high)
        low    = float(bar.low)
        open_  = float(bar.open)
        volume = float(bar.volume)

        # Write into circular buffer
        idx = self._buf_idx % len(self._closes)
        self._closes[idx]  = close
        self._highs[idx]   = high
        self._lows[idx]    = low
        self._volumes[idx] = volume
        self._opens[idx]   = open_
        self._buf_idx += 1
        self._bar_count += 1
        self._bars_since_last_close += 1

        # Warmup
        if self._bar_count < self.cfg.warmup_bars:
            return

        # Get ordered arrays
        n = min(self._buf_idx, len(self._closes))
        roll_off = max(0, self._buf_idx - len(self._closes))
        c = np.roll(self._closes, -roll_off)[:n]
        h = np.roll(self._highs,  -roll_off)[:n]
        lo = np.roll(self._lows,   -roll_off)[:n]
        v = np.roll(self._volumes, -roll_off)[:n]

        # ── Indicators ──
        ema_f = calc_ema(c, self.cfg.ema_fast)
        ema_m = calc_ema(c, self.cfg.ema_medium)
        ema_t = calc_ema(c, self.cfg.ema_trend)
        vwap  = calc_vwap(c, v, self.cfg.vwap_period)
        rsi   = calc_rsi(c, self.cfg.rsi_period)
        atr   = calc_atr(h, lo, c, self.cfg.atr_period)
        bb_u, bb_mid, bb_l = calc_bollinger(c, self.cfg.bb_period, self.cfg.bb_std)
        is_sq = detect_squeeze(c, self.cfg.bb_period, self.cfg.bb_std,
                               self.cfg.bb_squeeze_lookback)
        rvol  = calc_rvol(v, 20)

        # ── ATR history for regime ──
        aidx = self._atr_idx % len(self._atr_history)
        self._atr_history[aidx] = atr
        self._atr_idx += 1
        atr_n = min(self._atr_idx, len(self._atr_history))

        # ── CVD from bar ──
        self.cvd.update_from_bar(open_, high, low, close, volume)

        # ── Position management ──
        if self._position_open:
            self._manage_position(close, high, low, ema_f, ema_m, ema_t, vwap)
        else:
            self._check_entry(
                c, h, lo, v, close, high, low,
                ema_f, ema_m, ema_t, vwap, rsi, atr,
                bb_u, bb_l, is_sq, rvol,
                self._atr_history[:atr_n], n,
            )

        # ── Save prev state ──
        self._prev_ema_fast   = ema_f
        self._prev_ema_medium = ema_m
        self._prev_close      = close
        self._prev_bb_upper   = bb_u
        self._prev_bb_lower   = bb_l
        self._was_squeezed    = is_sq

    # ─────────────────────────────────────────────────────────────────
    # Entry Logic — mirrors live_engine/signal_engine.py on_volume_bar()
    # ─────────────────────────────────────────────────────────────────

    def _check_entry(
        self, c, h, lo, v,
        close, high, low,
        ema_f, ema_m, ema_t,
        vwap, rsi, atr,
        bb_u, bb_l, is_sq, rvol,
        atr_hist, n,
    ):
        cfg = self.cfg

        # ── Circuit breaker: daily trade limit ──
        if self._daily_trades >= cfg.max_daily_trades:
            return

        # ── Cooldown ──
        if self._bars_since_last_close < cfg.cooldown_bars:
            return

        # ── Loss-streak pause ──
        if self._bar_count < self._pause_until_bar:
            return

        # ── Minimum volatility gate ──
        if close > 0 and (atr / close) < cfg.min_atr_pct:
            return

        # ── Regime filter ──
        regime = detect_regime(atr_hist, c, ema_f, ema_m, ema_t)
        if regime == MarketRegime.CHOPPY:
            return

        # ── Liquidity sweep (adversarial) ──
        avg_vol = float(np.mean(v[-20:])) if n >= 20 else 0.0
        sweep = self.sweep_detector.detect(h, lo, c, v, avg_vol)
        if sweep in (SignalType.SWEEP_LONG, SignalType.SWEEP_SHORT):
            side = OrderSide.BUY if sweep == SignalType.SWEEP_LONG else OrderSide.SELL
            size_mult = 0.5 if regime == MarketRegime.VOLATILE else 1.0
            self._enter(side, close, atr, sweep, size_mult)
            return

        # ── Trend bias (Layer 1) ──
        ema_spread_pct = abs(ema_f - ema_m) / close if close > 0 else 0.0
        bias_long = (close > vwap and close > ema_t
                     and ema_f > ema_m
                     and ema_spread_pct >= cfg.min_ema_spread_pct)
        bias_short = (close < vwap and close < ema_t
                      and ema_f < ema_m
                      and ema_spread_pct >= cfg.min_ema_spread_pct)

        if not (bias_long or bias_short):
            return

        # ── Signal detection (Layer 2) ──
        signal = self._detect_signal(close, bias_long, bias_short,
                                     ema_f, ema_m, bb_u, bb_l, is_sq,
                                     cfg.entry_mode)
        if signal == SignalType.NONE:
            return

        # ── RSI confirmation (Layer 3) ──
        if signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            if not (cfg.rsi_long_min <= rsi <= cfg.rsi_long_max):
                return
        else:
            if not (cfg.rsi_short_min <= rsi <= cfg.rsi_short_max):
                return

        # ── Volume confirmation (Layer 4) ──
        if rvol < cfg.rvol_threshold:
            return

        # ── Submit entry ──
        is_long = signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG)
        side = OrderSide.BUY if is_long else OrderSide.SELL
        size_mult = 0.5 if regime == MarketRegime.VOLATILE else 1.0
        self._enter(side, close, atr, signal, size_mult)

    def _detect_signal(
        self, close, bias_long, bias_short,
        ema_f, ema_m, bb_u, bb_l, is_sq, mode,
    ) -> SignalType:
        """Same crossover + BB logic as live_engine SignalEngine._detect_signal()"""
        had_cross_up = (self._prev_ema_fast > 0
                        and self._prev_ema_fast <= self._prev_ema_medium
                        and ema_f > ema_m)
        had_cross_down = (self._prev_ema_fast > 0
                          and self._prev_ema_fast >= self._prev_ema_medium
                          and ema_f < ema_m)

        if mode in ("breakout", "hybrid"):
            if is_sq:
                if bias_long and close > bb_u:
                    if had_cross_up or ema_f > ema_m:
                        return SignalType.BREAKOUT_LONG
                if bias_short and close < bb_l:
                    if had_cross_down or ema_f < ema_m:
                        return SignalType.BREAKOUT_SHORT

        if mode in ("mean_rev", "hybrid"):
            if self._prev_close > 0 and self._prev_bb_lower > 0:
                if (bias_long
                        and self._prev_close < self._prev_bb_lower
                        and close > bb_l
                        and had_cross_up):
                    return SignalType.MEAN_REV_LONG
                if (bias_short
                        and self._prev_close > self._prev_bb_upper
                        and close < bb_u
                        and had_cross_down):
                    return SignalType.MEAN_REV_SHORT

        return SignalType.NONE

    # ─────────────────────────────────────────────────────────────────
    # Position Management — mirrors live_engine risk/trailing logic
    # ─────────────────────────────────────────────────────────────────

    def _manage_position(self, close, high, low,
                         ema_f, ema_m, ema_t, vwap):
        cfg = self.cfg
        bars_in_trade = self._bar_count - self._entry_bar

        if self._entry_side == OrderSide.BUY:
            self._highest_since_entry = max(self._highest_since_entry, high)

            # Trailing stop activation
            unrealized_atr = ((high - self._entry_price) / self._entry_atr
                              if self._entry_atr > 0 else 0.0)
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = (self._highest_since_entry
                             - self._entry_atr * cfg.trailing_distance_atr)
                if new_trail > self._trailing_stop:
                    self._trailing_stop = new_trail

            # Exit priority order (same as ams_scalper / live_engine)
            if self._trailing_active and low <= self._trailing_stop:
                self._close_position(close, "TRAILING")
                return
            if low <= self._stop_loss:
                self._close_position(close, "SL")
                return
            if high >= self._take_profit:
                self._close_position(close, "TP")
                return
            if bars_in_trade >= cfg.max_bars_in_trade:
                self._close_position(close, "TIMEOUT")
                return
            # Trend reversal exit
            if (close < vwap and close < ema_t and ema_f < ema_m):
                self._close_position(close, "REVERSAL")
                return

        elif self._entry_side == OrderSide.SELL:
            self._lowest_since_entry = min(self._lowest_since_entry, low)

            unrealized_atr = ((self._entry_price - low) / self._entry_atr
                              if self._entry_atr > 0 else 0.0)
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = (self._lowest_since_entry
                             + self._entry_atr * cfg.trailing_distance_atr)
                if self._trailing_stop <= 0 or new_trail < self._trailing_stop:
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
            if (close > vwap and close > ema_t and ema_f > ema_m):
                self._close_position(close, "REVERSAL")
                return

    # ─────────────────────────────────────────────────────────────────
    # Order helpers
    # ─────────────────────────────────────────────────────────────────

    def _enter(self, side: OrderSide, price: float, atr: float,
               signal: SignalType, size_mult: float = 1.0):
        cfg = self.cfg
        if atr <= 0:
            return

        qty = round(cfg.trade_size * size_mult, 3)
        if qty < 0.001:
            return

        self._position_open = True
        self._entry_price = price
        self._entry_side = side
        self._entry_bar = self._bar_count
        self._entry_atr = atr
        self._trailing_active = False
        self._trailing_stop = 0.0
        self._highest_since_entry = price
        self._lowest_since_entry = price
        self._total_trades += 1
        self._daily_trades += 1

        if side == OrderSide.BUY:
            self._stop_loss   = price - atr * cfg.atr_sl_multiplier
            self._take_profit = price + atr * cfg.atr_tp_multiplier
        else:
            self._stop_loss   = price + atr * cfg.atr_sl_multiplier
            self._take_profit = price - atr * cfg.atr_tp_multiplier

        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=Quantity.from_str(f"{qty:.3f}"),
        )
        self.submit_order(order)
        self.log.info(
            f"[ENTRY] {signal.name} {side.name} @ {price:.2f} "
            f"SL={self._stop_loss:.2f} TP={self._take_profit:.2f} "
            f"ATR={atr:.2f} qty={qty:.3f}"
        )

    def _close_position(self, close_price: float, reason: str):
        if self._entry_side is None:
            return

        pnl = (close_price - self._entry_price
               if self._entry_side == OrderSide.BUY
               else self._entry_price - close_price)

        # ── CircuitBreaker state update (mirrors live_engine/risk.py) ──
        if pnl > 0:
            self._wins += 1
            self._consecutive_losses = 0
        else:
            self._losses += 1
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.cfg.max_consecutive_losses:
                self._pause_until_bar = (self._bar_count
                                         + self.cfg.pause_bars_after_streak)
                self._consecutive_losses = 0
                self.log.warning(
                    f"[CB] Loss streak={self.cfg.max_consecutive_losses} → "
                    f"pausing until bar {self._pause_until_bar}"
                )

        close_side = (OrderSide.SELL if self._entry_side == OrderSide.BUY
                      else OrderSide.BUY)
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=close_side,
            quantity=Quantity.from_str(f"{self.cfg.trade_size:.3f}"),
            reduce_only=True,
        )
        self.submit_order(order)
        self.log.info(
            f"[EXIT] {reason} @ {close_price:.2f} "
            f"PnL≈{pnl:.2f} streak={self._consecutive_losses}"
        )

        # Reset position state
        self._position_open = False
        self._entry_price = 0.0
        self._entry_side = None
        self._entry_bar = 0
        self._entry_atr = 0.0
        self._stop_loss = 0.0
        self._take_profit = 0.0
        self._trailing_active = False
        self._trailing_stop = 0.0
        self._highest_since_entry = 0.0
        self._lowest_since_entry = float("inf")
        self._bars_since_last_close = 0
