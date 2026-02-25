"""
live_strategy.py — Nautilus Backtest Strategy
==============================================
ใช้ Nautilus built-in สำหรับ infrastructure:
  - ExponentialMovingAverage, RelativeStrengthIndex, AverageTrueRange, BollingerBands
  - TradeTick subscription → CVD จริงจาก is_buyer_maker
  - ValueBar ($50k INTERNAL) — เหมือน live_engine VolumeBarAggregator 100%
  - Dynamic position sizing จาก self.portfolio

กลยุทธ์การเทรดของเรา (ไม่เปลี่ยน):
  - VWAP rolling period (custom, Nautilus ใช้ session-based)
  - RVOL (custom)
  - detect_squeeze() (custom)
  - detect_regime() (custom)
  - LiquiditySweepDetector (custom)
  - Signal logic: BREAKOUT / MEAN_REV / SWEEP (ไม่เปลี่ยน)
  - Circuit breakers (ไม่เปลี่ยน)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

import numpy as np

from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.indicators.bollinger_bands import BollingerBands
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency, Quantity
from nautilus_trader.trading.strategy import Strategy


# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

class LiveStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: str = "BTCUSDT-PERP.BINANCE"
    # ValueBar $50k INTERNAL — เหมือน live_engine
    bar_type: str = "BTCUSDT-PERP.BINANCE-50000-VALUE-LAST-INTERNAL"

    # ── Indicator Periods ──
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
    entry_mode: str = "hybrid"

    # ── Risk Management ──
    risk_per_trade_pct: float = 0.01       # 1% risk per trade (dynamic sizing)
    atr_sl_multiplier: float = 2.0
    atr_tp_multiplier: float = 4.0
    trailing_activate_atr: float = 2.0
    trailing_distance_atr: float = 1.0

    # ── Circuit Breaker / Cooldown ──
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
# Enums
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
# Custom indicators (ไม่มีใน Nautilus built-in)
# ═══════════════════════════════════════════════════════════════════════

def calc_vwap(closes: np.ndarray, volumes: np.ndarray, period: int) -> float:
    """Rolling VWAP (Nautilus ใช้ session-based ซึ่งต่างกัน)"""
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
    """Relative Volume ratio (ไม่มีใน Nautilus)"""
    n = len(volumes)
    if n < period + 1:
        return 0.0
    current = float(volumes[-1])
    avg = float(np.mean(volumes[-(period + 1):-1]))
    return current / avg if avg > 0 else 0.0


def detect_squeeze(closes: np.ndarray, bb_period: int,
                   bb_std: float, lookback: int) -> bool:
    """BB squeeze detection — bandwidth percentile < 15%"""
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
# Liquidity Sweep Detector
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
        recent_low  = np.min(lows[-needed:-self.reversal_bars])
        sweep_highs  = highs[-self.reversal_bars:]
        sweep_lows   = lows[-self.reversal_bars:]
        sweep_closes = closes[-self.reversal_bars:]
        sweep_vols   = volumes[-self.reversal_bars:]
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
# CVD Tracker — update จาก TradeTick จริง (ไม่ต้อง approximate แล้ว)
# ═══════════════════════════════════════════════════════════════════════

class CVDTracker:
    def __init__(self, window: int = 100):
        self.deltas: deque[float] = deque(maxlen=window)
        self.cumulative: float = 0.0

    def update(self, qty: float, is_buyer_maker: bool) -> float:
        """อัพเดทจาก TradeTick จริง — ใช้ใน on_trade_tick()"""
        delta = -qty if is_buyer_maker else qty
        self.deltas.append(delta)
        self.cumulative = sum(self.deltas)
        return self.cumulative


# ═══════════════════════════════════════════════════════════════════════
# Strategy
# ═══════════════════════════════════════════════════════════════════════

class LiveStrategy(Strategy):
    """
    Nautilus backtest strategy:
    - ใช้ Nautilus built-in: EMA, RSI, ATR, BollingerBands
    - ใช้ TradeTick → CVD จริง ไม่ approximate
    - ValueBar $50k = เหมือน live_engine ทุกประการ
    - Dynamic sizing จาก portfolio balance
    - กลยุทธ์การเทรด (signal logic) ไม่เปลี่ยน
    """

    def __init__(self, config: LiveStrategyConfig):
        super().__init__(config)
        self.cfg = config
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._venue = Venue("BINANCE")

        # ── Nautilus built-in indicators ──
        self.ema_fast   = ExponentialMovingAverage(config.ema_fast)
        self.ema_medium = ExponentialMovingAverage(config.ema_medium)
        self.ema_trend  = ExponentialMovingAverage(config.ema_trend)
        self.rsi        = RelativeStrengthIndex(config.rsi_period)
        self.atr        = AverageTrueRange(config.atr_period)
        self.bb         = BollingerBands(config.bb_period, config.bb_std)

        # ── Custom data buffers (ใช้กับ VWAP, RVOL, squeeze, regime, sweep) ──
        max_buf = (max(config.ema_trend, config.bb_period, config.atr_period,
                       config.vwap_period)
                   + config.bb_squeeze_lookback + 50)
        self._closes  = np.zeros(max_buf, dtype=np.float64)
        self._highs   = np.zeros(max_buf, dtype=np.float64)
        self._lows    = np.zeros(max_buf, dtype=np.float64)
        self._volumes = np.zeros(max_buf, dtype=np.float64)
        self._atr_history = np.zeros(200, dtype=np.float64)
        self._buf_idx = 0
        self._atr_idx = 0
        self._bar_count = 0

        # ── Custom detectors ──
        self.sweep_detector = LiquiditySweepDetector(
            lookback=config.sweep_lookback,
            vol_spike_mult=config.sweep_vol_spike_mult,
            reversal_bars=config.sweep_reversal_bars,
        )
        self.cvd = CVDTracker()

        # ── Previous bar state ──
        self._prev_ema_fast: float   = 0.0
        self._prev_ema_medium: float = 0.0
        self._prev_close: float      = 0.0
        self._prev_bb_upper: float   = 0.0
        self._prev_bb_lower: float   = 0.0
        self._was_squeezed: bool     = False

        # ── Position state ──
        self._position_open: bool        = False
        self._entry_price: float         = 0.0
        self._entry_side: OrderSide | None = None
        self._entry_bar: int             = 0
        self._entry_atr: float           = 0.0
        self._stop_loss: float           = 0.0
        self._take_profit: float         = 0.0
        self._trailing_active: bool      = False
        self._trailing_stop: float       = 0.0
        self._highest_since_entry: float = 0.0
        self._lowest_since_entry: float  = float("inf")
        self._entry_qty: float           = 0.001

        # ── Circuit breaker / cooldown ──
        self._consecutive_losses: int     = 0
        self._daily_trades: int           = 0
        self._current_day: int            = -1
        self._bars_since_last_close: int  = 9999
        self._pause_until_bar: int        = 0

        # ── Stats ──
        self._total_trades: int = 0
        self._wins: int  = 0
        self._losses: int = 0

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────

    def on_start(self):
        bar_type = BarType.from_str(self.cfg.bar_type)

        # Register Nautilus indicators — auto-update ทุก bar
        self.register_indicator_for_bars(bar_type, self.ema_fast)
        self.register_indicator_for_bars(bar_type, self.ema_medium)
        self.register_indicator_for_bars(bar_type, self.ema_trend)
        self.register_indicator_for_bars(bar_type, self.rsi)
        self.register_indicator_for_bars(bar_type, self.atr)
        self.register_indicator_for_bars(bar_type, self.bb)

        # Subscribe trade ticks → CVD จริง
        self.subscribe_trade_ticks(self._instrument_id)

        # Subscribe value bars → signal generation
        self.subscribe_bars(bar_type)

        self.log.info(
            f"[LiveStrategy] Started | instrument={self.cfg.instrument_id} "
            f"| bar={self.cfg.bar_type} | mode={self.cfg.entry_mode} "
            f"| SL={self.cfg.atr_sl_multiplier}x | TP={self.cfg.atr_tp_multiplier}x ATR"
        )

    def on_stop(self):
        if self._total_trades > 0:
            wr = self._wins / self._total_trades * 100
            self.log.info(
                f"[LiveStrategy] DONE: trades={self._total_trades} "
                f"W={self._wins} L={self._losses} WR={wr:.1f}%"
            )

    # ─────────────────────────────────────────────────────────────────
    # TradeTick → CVD จริง (ไม่ approximate)
    # ─────────────────────────────────────────────────────────────────

    def on_trade_tick(self, tick: TradeTick):
        """อัพเดท CVD จาก TradeTick จริง — เหมือน live_engine CVDTracker.update()"""
        qty = float(tick.size)
        is_buyer_maker = (tick.aggressor_side == AggressorSide.SELLER)
        self.cvd.update(qty, is_buyer_maker)

    # ─────────────────────────────────────────────────────────────────
    # Bar handler — Nautilus auto-updates indicators ก่อน call นี้
    # ─────────────────────────────────────────────────────────────────

    def on_bar(self, bar: Bar):
        close  = float(bar.close)
        high   = float(bar.high)
        low    = float(bar.low)
        volume = float(bar.volume)

        # Daily trade counter reset (UTC)
        bar_day = bar.ts_event // 86_400_000_000_000
        if bar_day != self._current_day:
            self._current_day = bar_day
            self._daily_trades = 0

        # Update circular buffer (สำหรับ custom indicators)
        idx = self._buf_idx % len(self._closes)
        self._closes[idx]  = close
        self._highs[idx]   = high
        self._lows[idx]    = low
        self._volumes[idx] = volume
        self._buf_idx += 1
        self._bar_count += 1
        self._bars_since_last_close += 1

        # Warmup — รอให้ Nautilus indicators พร้อมและ buffer มีพอ
        if self._bar_count < self.cfg.warmup_bars:
            return
        if not (self.ema_fast.initialized and self.rsi.initialized
                and self.atr.initialized and self.bb.initialized):
            return

        # Get ordered arrays for custom calculations
        n = min(self._buf_idx, len(self._closes))
        roll_off = max(0, self._buf_idx - len(self._closes))
        c  = np.roll(self._closes,  -roll_off)[:n]
        h  = np.roll(self._highs,   -roll_off)[:n]
        lo = np.roll(self._lows,    -roll_off)[:n]
        v  = np.roll(self._volumes, -roll_off)[:n]

        # ── Nautilus indicators (auto-updated, just read values) ──
        ema_f  = self.ema_fast.value
        ema_m  = self.ema_medium.value
        ema_t  = self.ema_trend.value
        rsi    = self.rsi.value
        atr    = self.atr.value
        bb_u   = self.bb.upper
        bb_l   = self.bb.lower

        # ── Custom indicators ──
        vwap   = calc_vwap(c, v, self.cfg.vwap_period)
        rvol   = calc_rvol(v, 20)
        is_sq  = detect_squeeze(c, self.cfg.bb_period, self.cfg.bb_std,
                                self.cfg.bb_squeeze_lookback)

        # ── ATR history for regime detection ──
        aidx = self._atr_idx % len(self._atr_history)
        self._atr_history[aidx] = atr
        self._atr_idx += 1
        atr_n = min(self._atr_idx, len(self._atr_history))

        # ── Position management or entry check ──
        if self._position_open:
            self._manage_position(close, high, low, ema_f, ema_m, ema_t, vwap)
        else:
            self._check_entry(
                c, h, lo, v, close, high, low,
                ema_f, ema_m, ema_t, vwap, rsi, atr,
                bb_u, bb_l, is_sq, rvol,
                self._atr_history[:atr_n], n,
            )

        # Save prev state
        self._prev_ema_fast   = ema_f
        self._prev_ema_medium = ema_m
        self._prev_close      = close
        self._prev_bb_upper   = bb_u
        self._prev_bb_lower   = bb_l
        self._was_squeezed    = is_sq

    # ─────────────────────────────────────────────────────────────────
    # Entry Logic (ไม่เปลี่ยน)
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

        if self._daily_trades >= cfg.max_daily_trades:
            return
        if self._bars_since_last_close < cfg.cooldown_bars:
            return
        if self._bar_count < self._pause_until_bar:
            return
        if close > 0 and (atr / close) < cfg.min_atr_pct:
            return

        # Regime filter
        regime = detect_regime(atr_hist, c, ema_f, ema_m, ema_t)
        if regime == MarketRegime.CHOPPY:
            return

        # Liquidity sweep (adversarial)
        avg_vol = float(np.mean(v[-20:])) if n >= 20 else 0.0
        sweep = self.sweep_detector.detect(h, lo, c, v, avg_vol)
        if sweep in (SignalType.SWEEP_LONG, SignalType.SWEEP_SHORT):
            side = OrderSide.BUY if sweep == SignalType.SWEEP_LONG else OrderSide.SELL
            size_mult = 0.5 if regime == MarketRegime.VOLATILE else 1.0
            self._enter(side, close, atr, sweep, size_mult)
            return

        # Trend bias (Layer 1)
        ema_spread_pct = abs(ema_f - ema_m) / close if close > 0 else 0.0
        bias_long  = (close > vwap and close > ema_t
                      and ema_f > ema_m
                      and ema_spread_pct >= cfg.min_ema_spread_pct)
        bias_short = (close < vwap and close < ema_t
                      and ema_f < ema_m
                      and ema_spread_pct >= cfg.min_ema_spread_pct)

        if not (bias_long or bias_short):
            return

        # Signal detection (Layer 2)
        signal = self._detect_signal(close, bias_long, bias_short,
                                     ema_f, ema_m, bb_u, bb_l, is_sq,
                                     cfg.entry_mode)
        if signal == SignalType.NONE:
            return

        # RSI confirmation (Layer 3)
        if signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG):
            if not (cfg.rsi_long_min <= rsi <= cfg.rsi_long_max):
                return
        else:
            if not (cfg.rsi_short_min <= rsi <= cfg.rsi_short_max):
                return

        # Volume confirmation (Layer 4)
        if rvol < cfg.rvol_threshold:
            return

        is_long = signal in (SignalType.BREAKOUT_LONG, SignalType.MEAN_REV_LONG)
        side = OrderSide.BUY if is_long else OrderSide.SELL
        size_mult = 0.5 if regime == MarketRegime.VOLATILE else 1.0
        self._enter(side, close, atr, signal, size_mult)

    def _detect_signal(
        self, close, bias_long, bias_short,
        ema_f, ema_m, bb_u, bb_l, is_sq, mode,
    ) -> SignalType:
        had_cross_up   = (self._prev_ema_fast > 0
                          and self._prev_ema_fast <= self._prev_ema_medium
                          and ema_f > ema_m)
        had_cross_down = (self._prev_ema_fast > 0
                          and self._prev_ema_fast >= self._prev_ema_medium
                          and ema_f < ema_m)

        if mode in ("breakout", "hybrid"):
            # ✅ ใช้ _was_squeezed (bar ก่อนหน้า) — ตรงกับ live_engine
            if self._was_squeezed:
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
    # Position Management (ไม่เปลี่ยน)
    # ─────────────────────────────────────────────────────────────────

    def _manage_position(self, close, high, low, ema_f, ema_m, ema_t, vwap):
        cfg = self.cfg
        bars_in_trade = self._bar_count - self._entry_bar

        if self._entry_side == OrderSide.BUY:
            self._highest_since_entry = max(self._highest_since_entry, high)

            unrealized_atr = ((high - self._entry_price) / self._entry_atr
                              if self._entry_atr > 0 else 0.0)
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = (self._highest_since_entry
                             - self._entry_atr * cfg.trailing_distance_atr)
                if new_trail > self._trailing_stop:
                    self._trailing_stop = new_trail

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

    def _calc_qty(self, atr: float, size_mult: float) -> float:
        """Dynamic position sizing จาก portfolio balance (แทน fixed trade_size)"""
        try:
            account = self.portfolio.account(self._venue)
            if account is None:
                return 0.001
            balance = account.balance_free(Currency.from_str("USDT"))
            if balance is None:
                return 0.001
            balance_usdt = float(balance.as_double())
        except Exception:
            return 0.001

        risk_amount = balance_usdt * self.cfg.risk_per_trade_pct
        sl_distance = atr * self.cfg.atr_sl_multiplier
        if sl_distance <= 0:
            return 0.001

        qty = (risk_amount / sl_distance) * size_mult
        return max(0.001, round(qty, 3))

    def _enter(self, side: OrderSide, price: float, atr: float,
               signal: SignalType, size_mult: float = 1.0):
        if atr <= 0:
            return

        qty = self._calc_qty(atr, size_mult)
        if qty < 0.001:
            return

        self._position_open = True
        self._entry_price   = price
        self._entry_side    = side
        self._entry_bar     = self._bar_count
        self._entry_atr     = atr
        self._entry_qty     = qty
        self._trailing_active = False
        self._trailing_stop   = 0.0
        self._highest_since_entry = price
        self._lowest_since_entry  = price
        self._total_trades += 1
        self._daily_trades += 1

        if side == OrderSide.BUY:
            self._stop_loss   = price - atr * self.cfg.atr_sl_multiplier
            self._take_profit = price + atr * self.cfg.atr_tp_multiplier
        else:
            self._stop_loss   = price + atr * self.cfg.atr_sl_multiplier
            self._take_profit = price - atr * self.cfg.atr_tp_multiplier

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
            quantity=Quantity.from_str(f"{self._entry_qty:.3f}"),
            reduce_only=True,
        )
        self.submit_order(order)
        self.log.info(
            f"[EXIT] {reason} @ {close_price:.2f} "
            f"PnL≈{pnl:.2f} streak={self._consecutive_losses}"
        )

        # Reset position state
        self._position_open   = False
        self._entry_price     = 0.0
        self._entry_side      = None
        self._entry_bar       = 0
        self._entry_atr       = 0.0
        self._stop_loss       = 0.0
        self._take_profit     = 0.0
        self._trailing_active = False
        self._trailing_stop   = 0.0
        self._highest_since_entry = 0.0
        self._lowest_since_entry  = float("inf")
        self._bars_since_last_close = 0
