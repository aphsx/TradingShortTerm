"""
signal_engine.py — The Brain: Signal Generation + Market Regime + Adversarial Logic.
Processes volume bars and generates trading signals with regime filtering
and liquidity sweep detection.
"""

import numpy as np
import logging
from enum import Enum
from dataclasses import dataclass, field
from collections import deque

from .indicators import (
    calc_ema, calc_rsi, calc_atr, calc_bollinger,
    detect_squeeze, calc_vwap, calc_rvol, order_book_imbalance,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Volume Bar Aggregator
# ─────────────────────────────────────────────────────────────────────

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

    @property
    def cvd(self) -> float:
        return self.buy_volume - self.sell_volume


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
            self._current.high = price
            self._current.low = price
            self._current.ts_start = ts

        self._current.high = max(self._current.high, price)
        self._current.low = min(self._current.low, price)
        self._current.close = price
        self._current.volume += qty
        self._current.tick_count += 1
        self._current.ts_end = ts

        if is_buyer_maker:
            self._current.sell_volume += qty
        else:
            self._current.buy_volume += qty

        self._accumulated_notional += notional

        if self._accumulated_notional >= self.threshold:
            completed = self._current
            self._current = VolumeBar()
            self._accumulated_notional = 0.0
            return completed
        return None


# ─────────────────────────────────────────────────────────────────────
# Signal Types
# ─────────────────────────────────────────────────────────────────────

class SignalType(Enum):
    NONE = 0
    BREAKOUT_LONG = 1
    BREAKOUT_SHORT = 2
    MEAN_REV_LONG = 3
    MEAN_REV_SHORT = 4
    SWEEP_LONG = 5        # Adversarial: bullish liquidity sweep
    SWEEP_SHORT = 6       # Adversarial: bearish liquidity sweep


class MarketRegime(Enum):
    CHOPPY = 0      # Halt trading
    TRENDING = 1    # Normal trading
    VOLATILE = 2    # Reduce size 50%


@dataclass
class Signal:
    type: SignalType
    regime: MarketRegime
    side: str          # "BUY" / "SELL"
    confidence: float  # 0.0 - 1.0
    atr: float
    entry_reason: str


# ─────────────────────────────────────────────────────────────────────
# CVD Tracker
# ─────────────────────────────────────────────────────────────────────

class CVDTracker:
    """Tracks Cumulative Volume Delta over a rolling window."""

    def __init__(self, window: int = 100):
        self.deltas: deque[float] = deque(maxlen=window)
        self.cumulative: float = 0.0

    def update(self, qty: float, is_buyer_maker: bool) -> float:
        delta = -qty if is_buyer_maker else qty
        self.deltas.append(delta)
        self.cumulative = sum(self.deltas)
        return self.cumulative


# ─────────────────────────────────────────────────────────────────────
# Liquidity Sweep Detector
# ─────────────────────────────────────────────────────────────────────

class LiquiditySweepDetector:
    """
    Detects failed breakouts (stop runs) for adversarial entries.
    Pattern: Price breaks key level → high volume → immediate reversal.
    """

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

        # Bearish sweep: wick above swing high, close back below, volume spike
        if (np.any(sweep_highs > recent_high)
                and sweep_closes[-1] < recent_high
                and np.max(sweep_vols) > avg_volume * self.vol_mult):
            return SignalType.SWEEP_SHORT

        # Bullish sweep: wick below swing low, close back above, volume spike
        if (np.any(sweep_lows < recent_low)
                and sweep_closes[-1] > recent_low
                and np.max(sweep_vols) > avg_volume * self.vol_mult):
            return SignalType.SWEEP_LONG

        return SignalType.NONE


# ─────────────────────────────────────────────────────────────────────
# Market Regime Filter
# ─────────────────────────────────────────────────────────────────────

def detect_regime(atr_history: np.ndarray, closes: np.ndarray,
                  ema_fast: float, ema_medium: float,
                  ema_trend: float) -> MarketRegime:
    """
    Regime detection using ATR percentile + trend alignment.

    - CHOPPY:   ATR percentile < 25% AND EMAs converged → HALT
    - VOLATILE: ATR percentile > 90% → reduce size
    - TRENDING: otherwise → normal trading
    """
    if len(atr_history) < 50:
        return MarketRegime.TRENDING  # not enough data

    # ATR percentile rank
    current_atr = atr_history[-1]
    sorted_atr = np.sort(atr_history[-100:])
    pctile = np.searchsorted(sorted_atr, current_atr) / len(sorted_atr)

    # EMA convergence check (all 3 EMAs within 0.05% = choppy)
    price = closes[-1] if len(closes) > 0 else 1.0
    max_ema = max(ema_fast, ema_medium, ema_trend)
    min_ema = min(ema_fast, ema_medium, ema_trend)
    ema_range_pct = (max_ema - min_ema) / price if price > 0 else 0

    if pctile < 0.25 and ema_range_pct < 0.0005:
        return MarketRegime.CHOPPY

    if pctile > 0.90:
        return MarketRegime.VOLATILE

    return MarketRegime.TRENDING


# ─────────────────────────────────────────────────────────────────────
# Signal Engine (The Brain)
# ─────────────────────────────────────────────────────────────────────

class SignalEngine:
    """
    Processes volume bars and generates trading signals.
    Integrates regime filter, AMS v2 logic, and liquidity sweep detection.
    """

    def __init__(self, config):
        self.cfg = config
        buf_size = max(config.ema_trend, config.bb_period,
                       config.atr_period) + config.bb_squeeze_lookback + 50

        self.closes = np.zeros(buf_size, dtype=np.float64)
        self.highs = np.zeros(buf_size, dtype=np.float64)
        self.lows = np.zeros(buf_size, dtype=np.float64)
        self.volumes = np.zeros(buf_size, dtype=np.float64)
        self.atr_history = np.zeros(200, dtype=np.float64)
        self._buf_idx = 0
        self._atr_idx = 0
        self._bar_count = 0

        # Previous bar state
        self._prev_ema_fast = 0.0
        self._prev_ema_medium = 0.0
        self._prev_close = 0.0
        self._prev_bb_upper = 0.0
        self._prev_bb_lower = 0.0
        self._was_squeezed = False

        # Sub-detectors
        self.sweep_detector = LiquiditySweepDetector()
        self.cvd = CVDTracker()

        # Latest OBI from bookTicker
        self._latest_obi = 0.0

    def update_obi(self, bid_qty: float, ask_qty: float):
        self._latest_obi = order_book_imbalance(bid_qty, ask_qty)

    def on_volume_bar(self, bar: VolumeBar) -> Signal | None:
        """Process a completed volume bar and return a signal (or None)."""
        cfg = self.cfg
        idx = self._buf_idx % len(self.closes)
        self.closes[idx] = bar.close
        self.highs[idx] = bar.high
        self.lows[idx] = bar.low
        self.volumes[idx] = bar.volume
        self._buf_idx += 1
        self._bar_count += 1

        if self._bar_count < cfg.bb_squeeze_lookback + cfg.bb_period:
            return None

        # Get contiguous arrays for indicators
        n = min(self._buf_idx, len(self.closes))
        c = np.roll(self.closes, -max(0, self._buf_idx - len(self.closes)))[:n]
        h = np.roll(self.highs, -max(0, self._buf_idx - len(self.highs)))[:n]
        l = np.roll(self.lows, -max(0, self._buf_idx - len(self.lows)))[:n]
        v = np.roll(self.volumes, -max(0, self._buf_idx - len(self.volumes)))[:n]

        # ── Calculate all indicators ──
        ema_f = calc_ema(c, cfg.ema_fast)
        ema_m = calc_ema(c, cfg.ema_medium)
        ema_t = calc_ema(c, cfg.ema_trend)
        vwap = calc_vwap(c, v, cfg.vwap_period)
        rsi = calc_rsi(c, cfg.rsi_period)
        atr = calc_atr(h, l, c, cfg.atr_period)
        bb_u, bb_mid, bb_l = calc_bollinger(c, cfg.bb_period, cfg.bb_std)
        is_squeeze = detect_squeeze(c, cfg.bb_period, cfg.bb_std,
                                     cfg.bb_squeeze_lookback)
        rvol = calc_rvol(v, 20)

        # Track ATR history for regime
        aidx = self._atr_idx % len(self.atr_history)
        self.atr_history[aidx] = atr
        self._atr_idx += 1

        # ── Regime filter ──
        atr_n = min(self._atr_idx, len(self.atr_history))
        regime = detect_regime(
            self.atr_history[:atr_n], c, ema_f, ema_m, ema_t
        )
        if regime == MarketRegime.CHOPPY:
            self._save_prev_state(ema_f, ema_m, bar.close, bb_u, bb_l, is_squeeze)
            return None

        close = bar.close

        # ── Minimum volatility gate ──
        if close > 0 and (atr / close) < cfg.min_atr_pct:
            self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
            return None

        # ── Liquidity sweep detection (adversarial) ──
        avg_vol = float(np.mean(v[-20:])) if n >= 20 else 0
        sweep = self.sweep_detector.detect(h, l, c, v, avg_vol)
        if sweep in (SignalType.SWEEP_LONG, SignalType.SWEEP_SHORT):
            side = "BUY" if sweep == SignalType.SWEEP_LONG else "SELL"
            sig = Signal(
                type=sweep, regime=regime, side=side,
                confidence=0.7, atr=atr,
                entry_reason=f"liquidity_sweep_{side.lower()}",
            )
            self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
            return sig

        # ── Standard AMS v2 signal logic (from ams_scalper.py) ──
        # Layer 1: Trend bias
        bias_long = (close > vwap and close > ema_t
                     and ema_f > ema_m
                     and abs(ema_f - ema_m) / close >= cfg.min_ema_spread_pct)
        bias_short = (close < vwap and close < ema_t
                      and ema_f < ema_m
                      and abs(ema_f - ema_m) / close >= cfg.min_ema_spread_pct)

        if not (bias_long or bias_short):
            self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
            return None

        # Layer 2: Signal detection
        signal_type = self._detect_signal(
            close, bias_long, bias_short,
            ema_f, ema_m, bb_u, bb_l, is_squeeze, cfg.entry_mode
        )
        if signal_type == SignalType.NONE:
            self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
            return None

        # Layer 3: RSI confirmation
        if signal_type in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            if not (cfg.rsi_long_min <= rsi <= cfg.rsi_long_max):
                self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
                return None
        else:
            if not (cfg.rsi_short_min <= rsi <= cfg.rsi_short_max):
                self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
                return None

        # Layer 4: Volume confirmation
        if rvol < cfg.rvol_threshold:
            self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
            return None

        # ── Generate signal ──
        is_long = signal_type in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG)
        confidence = 0.6
        if self._latest_obi > 0.3 and is_long:
            confidence += 0.15
        elif self._latest_obi < -0.3 and not is_long:
            confidence += 0.15

        sig = Signal(
            type=signal_type, regime=regime,
            side="BUY" if is_long else "SELL",
            confidence=confidence, atr=atr,
            entry_reason=signal_type.name.lower(),
        )
        self._save_prev_state(ema_f, ema_m, close, bb_u, bb_l, is_squeeze)
        return sig

    def _detect_signal(self, close, bias_long, bias_short,
                       ema_f, ema_m, bb_u, bb_l,
                       is_squeeze, mode) -> SignalType:
        """EMA crossover + BB breakout/mean-rev detection."""
        had_cross_up = (self._prev_ema_fast > 0
                        and self._prev_ema_fast <= self._prev_ema_medium
                        and ema_f > ema_m)
        had_cross_down = (self._prev_ema_fast > 0
                          and self._prev_ema_fast >= self._prev_ema_medium
                          and ema_f < ema_m)

        if mode in ("breakout", "hybrid"):
            if self._was_squeezed:
                if bias_long and close > bb_u:
                    if had_cross_up or ema_f > ema_m:
                        return SignalType.BREAKOUT_LONG
                if bias_short and close < bb_l:
                    if had_cross_down or ema_f < ema_m:
                        return SignalType.BREAKOUT_SHORT

        if mode in ("mean_rev", "hybrid"):
            if self._prev_close > 0 and self._prev_bb_lower > 0:
                if (bias_long and self._prev_close < self._prev_bb_lower
                        and close > bb_l and had_cross_up):
                    return SignalType.MEAN_REV_LONG
                if (bias_short and self._prev_close > self._prev_bb_upper
                        and close < bb_u and had_cross_down):
                    return SignalType.MEAN_REV_SHORT

        return SignalType.NONE

    def _save_prev_state(self, ema_f, ema_m, close, bb_u, bb_l, squeeze):
        self._prev_ema_fast = ema_f
        self._prev_ema_medium = ema_m
        self._prev_close = close
        self._prev_bb_upper = bb_u
        self._prev_bb_lower = bb_l
        self._was_squeezed = squeeze
