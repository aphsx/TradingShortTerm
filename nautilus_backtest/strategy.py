"""
strategy.py — Nautilus adapter for live_engine
===============================================
Nautilus provides the environment (SimulatedExchange, order execution, account).
All signal logic runs directly from live_engine/signal_engine.py.

Architecture:
    run.py          → Nautilus environment (BacktestEngine, venue, data)
    strategy.py     → thin adapter: Nautilus hooks → live_engine calls
    live_engine/    → your actual bot (tune here; backtest picks it up automatically)

When you change signal_engine.py or indicators.py in live_engine,
the backtest uses the updated logic with zero changes here.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Allow importing live_engine from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency, Quantity
from nautilus_trader.trading.strategy import Strategy

from live_engine.config import TradingConfig
from live_engine.signal_engine import SignalEngine, VolumeBar


# ═══════════════════════════════════════════════════════════════════════
# Config  (mirrors live_engine/config.py — tune values here for backtest)
# ═══════════════════════════════════════════════════════════════════════

class LiveStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: str = "BTCUSDT-PERP.BINANCE"
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
    rvol_threshold: float = 0.0   # VALUE bars: notional is fixed → RVOL ≈ 1.0
    min_ema_spread_pct: float = 0.0005
    min_atr_pct: float = 0.001
    entry_mode: str = "hybrid"

    # ── Risk Management ──
    risk_per_trade_pct: float = 0.01
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

    # ── Warmup (bars before trading) ──
    warmup_bars: int = 80


# ═══════════════════════════════════════════════════════════════════════
# Strategy  (thin Nautilus adapter — no signal logic here)
# ═══════════════════════════════════════════════════════════════════════

class LiveStrategy(Strategy):
    """
    Nautilus adapter that routes:
      TradeTick  →  signal_engine.cvd.update()
      Bar        →  signal_engine.on_volume_bar()  →  submit_order()

    Signal logic, indicators, regime detection, and sweep detection all
    run from live_engine/signal_engine.py — identical to live trading.
    """

    def __init__(self, config: LiveStrategyConfig):
        super().__init__(config)
        self.cfg = config
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._venue = Venue("BINANCE")

        # ── Wire live_engine's SignalEngine ──────────────────────────
        live_cfg = TradingConfig(
            ema_fast=config.ema_fast,
            ema_medium=config.ema_medium,
            ema_trend=config.ema_trend,
            rsi_period=config.rsi_period,
            atr_period=config.atr_period,
            bb_period=config.bb_period,
            bb_std=config.bb_std,
            bb_squeeze_lookback=config.bb_squeeze_lookback,
            vwap_period=config.vwap_period,
            rsi_long_min=config.rsi_long_min,
            rsi_long_max=config.rsi_long_max,
            rsi_short_min=config.rsi_short_min,
            rsi_short_max=config.rsi_short_max,
            rvol_threshold=config.rvol_threshold,
            min_ema_spread_pct=config.min_ema_spread_pct,
            min_atr_pct=config.min_atr_pct,
            entry_mode=config.entry_mode,
            risk_per_trade_pct=config.risk_per_trade_pct,
            atr_sl_multiplier=config.atr_sl_multiplier,
            atr_tp_multiplier=config.atr_tp_multiplier,
            trailing_activate_atr=config.trailing_activate_atr,
            trailing_distance_atr=config.trailing_distance_atr,
            cooldown_bars=config.cooldown_bars,
            max_consecutive_losses=config.max_consecutive_losses,
            max_daily_trades=config.max_daily_trades,
            pause_bars_after_streak=config.pause_bars_after_streak,
        )
        self.signal_engine = SignalEngine(live_cfg)

        # ── Position state (Nautilus order submission) ───────────────
        self._position_open: bool = False
        self._entry_price: float = 0.0
        self._entry_side: OrderSide | None = None
        self._entry_bar: int = 0
        self._entry_atr: float = 0.0
        self._entry_qty: float = 0.001
        self._stop_loss: float = 0.0
        self._take_profit: float = 0.0
        self._trailing_active: bool = False
        self._trailing_stop: float = 0.0
        self._highest_since_entry: float = 0.0
        self._lowest_since_entry: float = float("inf")

        # ── Circuit breaker state ────────────────────────────────────
        self._consecutive_losses: int = 0
        self._daily_trades: int = 0
        self._current_day: int = -1
        self._bars_since_last_close: int = 9999
        self._pause_until_bar: int = 0
        self._bar_count: int = 0

        # ── Stats ────────────────────────────────────────────────────
        self._total_trades: int = 0
        self._wins: int = 0
        self._losses: int = 0

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────

    def on_start(self):
        bar_type = BarType.from_str(self.cfg.bar_type)
        self.subscribe_trade_ticks(self._instrument_id)
        self.subscribe_bars(bar_type)
        self.log.info(
            f"[LiveStrategy] Started | {self.cfg.instrument_id} "
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
    # TradeTick → CVD (routed into live_engine's CVDTracker)
    # ─────────────────────────────────────────────────────────────────

    def on_trade_tick(self, tick: TradeTick):
        is_buyer_maker = (tick.aggressor_side == AggressorSide.SELLER)
        self.signal_engine.cvd.update(float(tick.size), is_buyer_maker)

    # ─────────────────────────────────────────────────────────────────
    # Bar → signal_engine (identical to live trading)
    # ─────────────────────────────────────────────────────────────────

    def on_bar(self, bar: Bar):
        self._bar_count += 1
        self._bars_since_last_close += 1

        bar_day = bar.ts_event // 86_400_000_000_000
        if bar_day != self._current_day:
            self._current_day = bar_day
            self._daily_trades = 0

        if self._bar_count % 1000 == 0:
            self.log.info(f"[LiveStrategy] Progress: {self._bar_count} bars...")

        close = float(bar.close)
        high  = float(bar.high)
        low   = float(bar.low)

        # Manage open position first
        if self._position_open:
            self._manage_position(close, high, low)
            # Always feed bar to signal_engine to keep indicators current
            self.signal_engine.on_volume_bar(
                VolumeBar(open=float(bar.open), high=high, low=low,
                          close=close, volume=float(bar.volume))
            )
            return

        # Warmup: feed bars to signal_engine but skip entry logic
        if self._bar_count < self.cfg.warmup_bars:
            self.signal_engine.on_volume_bar(
                VolumeBar(open=float(bar.open), high=high, low=low,
                          close=close, volume=float(bar.volume))
            )
            return

        # Circuit breakers — still feed bar for indicator continuity
        circuit_open = (
            self._daily_trades >= self.cfg.max_daily_trades
            or self._bars_since_last_close < self.cfg.cooldown_bars
            or self._bar_count < self._pause_until_bar
        )

        # Feed bar to live_engine's SignalEngine (same as live trading)
        signal = self.signal_engine.on_volume_bar(
            VolumeBar(open=float(bar.open), high=high, low=low,
                      close=close, volume=float(bar.volume))
        )

        if signal is not None and not circuit_open:
            side = OrderSide.BUY if signal.side == "BUY" else OrderSide.SELL
            size_mult = 0.5 if signal.regime.name == "VOLATILE" else 1.0
            self._enter(side, close, signal.atr, signal.type.name, size_mult)

    # ─────────────────────────────────────────────────────────────────
    # Position management (SL / TP / Trailing / Timeout)
    # ─────────────────────────────────────────────────────────────────

    def _manage_position(self, close: float, high: float, low: float):
        cfg = self.cfg
        bars_in_trade = self._bar_count - self._entry_bar
        atr = self._entry_atr

        if self._entry_side == OrderSide.BUY:
            self._highest_since_entry = max(self._highest_since_entry, high)
            unrealized_atr = (high - self._entry_price) / atr if atr > 0 else 0.0
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = self._highest_since_entry - atr * cfg.trailing_distance_atr
                self._trailing_stop = max(self._trailing_stop, new_trail)
            if self._trailing_active and low <= self._trailing_stop:
                self._close_position(close, "TRAILING"); return
            if low <= self._stop_loss:
                self._close_position(close, "SL"); return
            if high >= self._take_profit:
                self._close_position(close, "TP"); return
            if bars_in_trade >= cfg.max_bars_in_trade:
                self._close_position(close, "TIMEOUT")

        elif self._entry_side == OrderSide.SELL:
            self._lowest_since_entry = min(self._lowest_since_entry, low)
            unrealized_atr = (self._entry_price - low) / atr if atr > 0 else 0.0
            if unrealized_atr >= cfg.trailing_activate_atr:
                self._trailing_active = True
                new_trail = self._lowest_since_entry + atr * cfg.trailing_distance_atr
                if self._trailing_stop <= 0 or new_trail < self._trailing_stop:
                    self._trailing_stop = new_trail
            if self._trailing_active and high >= self._trailing_stop:
                self._close_position(close, "TRAILING"); return
            if high >= self._stop_loss:
                self._close_position(close, "SL"); return
            if low <= self._take_profit:
                self._close_position(close, "TP"); return
            if bars_in_trade >= cfg.max_bars_in_trade:
                self._close_position(close, "TIMEOUT")

    # ─────────────────────────────────────────────────────────────────
    # Order helpers
    # ─────────────────────────────────────────────────────────────────

    def _calc_qty(self, atr: float, size_mult: float) -> float:
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
        return max(0.001, round((risk_amount / sl_distance) * size_mult, 3))

    def _enter(self, side: OrderSide, price: float, atr: float,
               signal_name: str, size_mult: float = 1.0):
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
            f"[ENTRY] {signal_name} {side.name} @ {price:.2f} "
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
                self._pause_until_bar = self._bar_count + self.cfg.pause_bars_after_streak
                self._consecutive_losses = 0
                self.log.warning(
                    f"[CB] Loss streak → pausing until bar {self._pause_until_bar}"
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
            f"[EXIT] {reason} @ {close_price:.2f} PnL≈{pnl:.2f}"
        )

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
