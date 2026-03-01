"""
strategy.py — Strategy-Agnostic Multi-Asset Base Class
=======================================================
Architecture:
    MultiAssetStrategy  ← base class (this file — DO NOT modify for trading logic)
        └── YourStrategy(MultiAssetStrategy)  ← subclass (your logic goes here)

The base class handles:
  - Subscribing to data feeds for all instruments
  - Routing events (tick / bar / custom data) to per-instrument state
  - Automatic position management (SL / TP / trailing stop / timeout)
  - Circuit breakers (cooldown / daily limit / loss streak pause)
  - Order submission helpers (market / limit / entry / exit)
  - Portfolio balance and position sizing

YOU only override:
  - on_trade_tick_logic(tick, state)      ← tick processing (CVD, large trades)
  - on_bar_logic(bar, bar_type, state)    ← bar processing (your entry/exit signals)
  - on_custom_data_logic(data, state)     ← bookDepth / metrics reactions

Quick-start example (see bottom of file):
    class MyStrategy(MultiAssetStrategy):
        def on_bar_logic(self, bar, bar_type, state):
            if self.is_warmup(state):
                return
            # your entry logic here
            self.enter_position(state, OrderSide.BUY, atr=10.0, reason="my_signal")
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow importing live_engine from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType, TradeTick, GenericData
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.trading.strategy import Strategy


# ═══════════════════════════════════════════════════════════════════════════════
# InstrumentState — per-instrument mutable state container
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class InstrumentState:
    """
    All mutable state for ONE instrument.
    Completely isolated from other instruments' states.

    Access this via the `state` parameter in all *_logic() override methods.
    Store your custom indicator values in `state.custom` dict.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    instrument_id: InstrumentId
    symbol: str                       # e.g. "SOLUSDT"
    price_precision: int              # decimal places for price formatting
    size_precision: int               # decimal places for qty formatting

    # ── Position Tracking ───────────────────────────────────────────────────
    position_open: bool = False
    entry_price: float = 0.0
    entry_side: OrderSide | None = None
    entry_bar_count: int = 0          # bar_count value when position opened
    entry_atr: float = 0.0            # ATR at entry time (for trailing)
    entry_qty: float = 0.0            # size entered

    # ── Stop Loss / Take Profit / Trailing ──────────────────────────────────
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_active: bool = False
    trailing_stop: float = 0.0
    highest_since_entry: float = 0.0
    lowest_since_entry: float = float("inf")

    # ── Bar Counters ────────────────────────────────────────────────────────
    bar_count: int = 0                # total bars received for this instrument
    bars_since_last_close: int = 9999

    # ── Circuit Breaker State ───────────────────────────────────────────────
    daily_trades: int = 0
    current_day: int = -1             # nanosecond day (ts_event // 86_400e9)
    consecutive_losses: int = 0
    pause_until_bar: int = 0          # resume entry after this bar_count

    # ── Statistics ──────────────────────────────────────────────────────────
    total_trades: int = 0
    wins: int = 0
    losses: int = 0

    # ── Latest Bar Cache ────────────────────────────────────────────────────
    last_close: float = 0.0
    last_high: float = 0.0
    last_low: float = 0.0
    last_volume: float = 0.0

    # ── Market Data from Custom Feeds ───────────────────────────────────────
    # bookDepth: percentage level → notional (USD)
    # negative percentage = ask side (above mid), positive = bid side (below mid)
    depth_bid: dict[float, float] = field(default_factory=dict)   # pct → notional
    depth_ask: dict[float, float] = field(default_factory=dict)   # pct → notional
    # metrics
    open_interest: float = 0.0
    open_interest_value: float = 0.0
    taker_buy_sell_ratio: float = 0.0  # >1 = more buying, <1 = more selling
    global_ls_ratio: float = 0.0       # all accounts long/short ratio
    top_trader_ls_count: float = 0.0
    top_trader_ls_pos: float = 0.0

    # ── User-Defined Storage ────────────────────────────────────────────────
    # Store anything here: indicator buffers, signal state, counters, etc.
    # Example: state.custom["cvd"] = 0.0
    #          state.custom["ema9"] = deque(maxlen=100)
    custom: dict = field(default_factory=dict)

    # ── Derived helpers ──────────────────────────────────────────────────────

    @property
    def bid_ask_depth_imbalance(self) -> float:
        """
        Depth imbalance at ±0.2% level: +1.0 = all bids, -1.0 = all asks.
        Returns 0.0 if depth data not yet available.
        """
        bid = self.depth_bid.get(0.2, 0.0)
        ask = self.depth_ask.get(0.2, 0.0)
        total = bid + ask
        if total == 0:
            return 0.0
        return (bid - ask) / total

    @property
    def total_bid_notional(self) -> float:
        """Total notional USD across all bid depth levels."""
        return sum(self.depth_bid.values())

    @property
    def total_ask_notional(self) -> float:
        """Total notional USD across all ask depth levels."""
        return sum(self.depth_ask.values())


# ═══════════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════════

class MultiAssetStrategyConfig(StrategyConfig, frozen=True):
    """
    Configuration for MultiAssetStrategy.

    instrument_ids : list of "SYMBOL-PERP.BINANCE" strings
    bar_types      : dict mapping each instrument_id_str to list of bar_type_strs
                     The strategy subscribes to all listed bar types.

    Example:
        MultiAssetStrategyConfig(
            instrument_ids=["SOLUSDT-PERP.BINANCE", "BNBUSDT-PERP.BINANCE"],
            bar_types={
                "SOLUSDT-PERP.BINANCE": [
                    "SOLUSDT-PERP.BINANCE-50000-VALUE-LAST-INTERNAL",
                    "SOLUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL",
                ],
                "BNBUSDT-PERP.BINANCE": [
                    "BNBUSDT-PERP.BINANCE-50000-VALUE-LAST-INTERNAL",
                ],
            },
        )
    """

    # ── Instruments ──────────────────────────────────────────────────────────
    instrument_ids: tuple[str, ...] = ()
    bar_types: dict[str, tuple[str, ...]] = {}

    # ── Risk Parameters ──────────────────────────────────────────────────────
    risk_per_trade_pct: float = 0.01       # 1% of account per trade
    atr_sl_multiplier: float = 2.0         # SL = entry ± (ATR × 2.0)
    atr_tp_multiplier: float = 4.0         # TP = entry ± (ATR × 4.0)
    trailing_activate_atr: float = 2.0     # Start trailing at +2.0 ATR unrealized
    trailing_distance_atr: float = 1.0     # Trail by 1.0 ATR from highest/lowest

    # ── Circuit Breakers ─────────────────────────────────────────────────────
    cooldown_bars: int = 10                # Min bars between trades (per instrument)
    max_consecutive_losses: int = 5        # Losses before forced pause
    pause_bars_after_streak: int = 60      # Bars to pause after loss streak
    max_bars_in_trade: int = 120           # Force close after N bars (timeout)
    max_daily_trades: int = 50             # Max entries per instrument per day

    # ── Warmup ───────────────────────────────────────────────────────────────
    warmup_bars: int = 80                  # Bars before strategy can trade


# ═══════════════════════════════════════════════════════════════════════════════
# MultiAssetStrategy — Base Class
# ═══════════════════════════════════════════════════════════════════════════════

class MultiAssetStrategy(Strategy):
    """
    Strategy-agnostic base class for multi-instrument Nautilus backtests.

    Data routing (internal — do not override):
        on_trade_tick()  →  on_trade_tick_logic(tick, state)
        on_bar()         →  _manage_position() → on_bar_logic(bar, bar_type, state)
        on_data()        →  _update_depth_state() / _update_metrics_state()
                         →  on_custom_data_logic(data, state)

    Override these for your strategy:
        on_trade_tick_logic()   — process ticks (CVD, large trade detection)
        on_bar_logic()          — entry/exit signals (call enter_position / close_position)
        on_custom_data_logic()  — react to bookDepth / metrics

    Built-in helpers:
        enter_position()        — enters with auto SL/TP
        close_position()        — exits with reduce_only market order
        submit_market_order()   — raw market order
        submit_limit_order()    — raw limit order
        calc_position_size()    — ATR-based risk sizing
        get_balance()           — free USDT from portfolio
        is_warmup()             — check if instrument is still warming up
    """

    def __init__(self, config: MultiAssetStrategyConfig):
        super().__init__(config)
        self.cfg    = config
        self._venue = Venue("BINANCE")

        # Per-instrument state: InstrumentId → InstrumentState
        self._states: dict[InstrumentId, InstrumentState] = {}

        # BarType → InstrumentId mapping for routing on_bar
        self._bar_type_to_iid: dict[str, InstrumentId] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def on_start(self) -> None:
        """Subscribe to all instruments and initialize per-instrument state."""
        for iid_str in self.cfg.instrument_ids:
            iid        = InstrumentId.from_str(iid_str)
            instrument = self.cache.instrument(iid)
            if instrument is None:
                self.log.error(f"[INIT] Instrument not found in cache: {iid}")
                continue

            symbol = iid_str.split("-PERP.")[0]
            self._states[iid] = InstrumentState(
                instrument_id=iid,
                symbol=symbol,
                price_precision=instrument.price_precision,
                size_precision=instrument.size_precision,
            )

            # Subscribe to trade ticks
            self.subscribe_trade_ticks(iid)

            # Subscribe to all configured bar types
            for bt_str in self.cfg.bar_types.get(iid_str, ()):
                bt = BarType.from_str(bt_str)
                self._bar_type_to_iid[bt_str] = iid
                self.subscribe_bars(bt)
                self.log.info(f"[INIT] {symbol}: subscribed {bt_str}")

        self.log.info(
            f"[MultiAssetStrategy] Started | "
            f"instruments={len(self._states)} | "
            f"warmup={self.cfg.warmup_bars} bars | "
            f"risk={self.cfg.risk_per_trade_pct*100:.1f}% | "
            f"SL={self.cfg.atr_sl_multiplier}x ATR | "
            f"TP={self.cfg.atr_tp_multiplier}x ATR"
        )

    def on_stop(self) -> None:
        """Log final statistics for all instruments."""
        self.log.info("=" * 60)
        self.log.info("[MultiAssetStrategy] Final Statistics")
        self.log.info("=" * 60)

        total_trades = total_wins = total_losses = 0
        for iid, state in self._states.items():
            if state.total_trades > 0:
                wr = state.wins / state.total_trades * 100
                self.log.info(
                    f"  {state.symbol:10s} | "
                    f"trades={state.total_trades:4d} | "
                    f"W={state.wins:3d} L={state.losses:3d} | "
                    f"WR={wr:5.1f}%"
                )
                total_trades += state.total_trades
                total_wins   += state.wins
                total_losses += state.losses

        if total_trades > 0:
            portfolio_wr = total_wins / total_trades * 100
            self.log.info("─" * 60)
            self.log.info(
                f"  PORTFOLIO  | "
                f"trades={total_trades:4d} | "
                f"W={total_wins:3d} L={total_losses:3d} | "
                f"WR={portfolio_wr:5.1f}%"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Event Routing (infrastructure — do not override)
    # ─────────────────────────────────────────────────────────────────────────

    def on_trade_tick(self, tick: TradeTick) -> None:
        """Route tick to correct instrument state, then delegate to logic."""
        state = self._states.get(tick.instrument_id)
        if state is None:
            return
        self.on_trade_tick_logic(tick, state)

    def on_bar(self, bar: Bar) -> None:
        """
        Route bar to correct instrument state.
        Order of operations:
          1. Increment bar counter and update last price cache
          2. Reset daily trade counter if new calendar day
          3. If position open → auto SL/TP/trailing/timeout management
          4. Delegate to on_bar_logic() for entry signal detection
        """
        iid   = bar.bar_type.instrument_id
        state = self._states.get(iid)
        if state is None:
            return

        # Update counters and cache
        state.bar_count += 1
        state.bars_since_last_close += 1
        state.last_close  = float(bar.close)
        state.last_high   = float(bar.high)
        state.last_low    = float(bar.low)
        state.last_volume = float(bar.volume)

        # Daily counter reset
        bar_day = bar.ts_event // 86_400_000_000_000
        if bar_day != state.current_day:
            state.current_day  = bar_day
            state.daily_trades = 0

        # Built-in position management (runs before user logic)
        if state.position_open:
            self._manage_position(bar, state)
            if not state.position_open:
                return   # position just closed — skip entry logic this bar

        # User-defined bar logic (entry/exit signals)
        self.on_bar_logic(bar, bar.bar_type, state)

    def on_data(self, data: GenericData) -> None:
        """
        Route custom data (BookDepthData / MarketMetrics) to correct state.
        Updates state fields automatically before calling on_custom_data_logic().
        """
        item = data.data
        instrument_id_str = getattr(item, "instrument_id", None)
        if instrument_id_str is None:
            return

        iid   = InstrumentId.from_str(instrument_id_str)
        state = self._states.get(iid)
        if state is None:
            return

        # Route to the correct updater based on data class type
        class_name = type(item).__name__
        if class_name == "BookDepthData":
            self._update_depth_state(item, state)
        elif class_name == "MarketMetrics":
            self._update_metrics_state(item, state)

        # Delegate to user logic
        self.on_custom_data_logic(data, state)

    # ─────────────────────────────────────────────────────────────────────────
    # Override Points — YOUR LOGIC GOES HERE
    # ─────────────────────────────────────────────────────────────────────────

    def on_trade_tick_logic(self, tick: TradeTick, state: InstrumentState) -> None:
        """
        Override: process a single trade tick for this instrument.

        Common uses:
          - Build CVD (cumulative volume delta)
          - Detect large block trades
          - Maintain tick-level VWAP

        Args:
            tick  : the TradeTick event
            state : this instrument's mutable state

        Example:
            # Track CVD in state.custom
            cvd = state.custom.get("cvd", 0.0)
            is_buy = tick.aggressor_side == AggressorSide.BUYER
            delta = float(tick.size) if is_buy else -float(tick.size)
            state.custom["cvd"] = cvd + delta
        """
        pass

    def on_bar_logic(
        self,
        bar: Bar,
        bar_type: BarType,
        state: InstrumentState,
    ) -> None:
        """
        Override: implement your entry and exit logic here.

        This is called after the base class has:
          - Updated state.bar_count, state.last_close, etc.
          - Run SL/TP/trailing/timeout management

        Args:
            bar      : OHLCV bar event
            bar_type : which bar type (VALUE, 1m, 5m, etc.)
            state    : this instrument's mutable state

        Example:
            if self.is_warmup(state):
                return

            # Check which bar type triggered this
            is_value_bar = "VALUE" in str(bar_type)

            # Your signal logic here
            # ...

            if long_signal:
                self.enter_position(state, OrderSide.BUY, atr=5.0,
                                    reason="breakout")
            elif short_signal:
                self.enter_position(state, OrderSide.SELL, atr=5.0,
                                    reason="breakdown")
        """
        pass

    def on_custom_data_logic(
        self,
        data: GenericData,
        state: InstrumentState,
    ) -> None:
        """
        Override: react to bookDepth or metrics updates.

        State is already updated before this call:
          - state.depth_bid / state.depth_ask (from BookDepthData)
          - state.open_interest, state.taker_buy_sell_ratio, etc. (from MarketMetrics)

        Args:
            data  : the GenericData object (access data.data for raw values)
            state : this instrument's mutable state

        Example:
            # React when open interest spikes
            if state.open_interest > state.custom.get("prev_oi", 0) * 1.05:
                state.custom["oi_expanding"] = True
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Helper Methods — call these from your logic
    # ─────────────────────────────────────────────────────────────────────────

    def enter_position(
        self,
        state: InstrumentState,
        side: OrderSide,
        atr: float,
        reason: str,
        size_mult: float = 1.0,
    ) -> None:
        """
        Enter a position with automatic SL and TP calculation.

        Pre-checks (all must pass):
          - No position already open for this instrument
          - Circuit breakers not triggered (cooldown / daily limit / loss streak)
          - ATR > 0
          - Calculated quantity >= instrument minimum (size_precision)

        Actions:
          - Calculate qty = calc_position_size(state, atr, size_mult)
          - Set stop_loss  = entry ± (ATR × atr_sl_multiplier)
          - Set take_profit = entry ± (ATR × atr_tp_multiplier)
          - Submit market order
          - Update state

        Args:
            state     : instrument state
            side      : OrderSide.BUY or OrderSide.SELL
            atr       : current ATR value (used for SL/TP and sizing)
            reason    : label for log (e.g. "breakout", "sweep")
            size_mult : position size multiplier (e.g. 0.5 in volatile regimes)
        """
        if state.position_open:
            return
        if self._is_circuit_open(state):
            return
        if atr <= 0:
            return

        # Get last price from cache
        price = state.last_close
        if price <= 0:
            return

        qty = self.calc_position_size(state, atr, size_mult)
        if qty <= 0:
            return

        # Update state
        state.position_open          = True
        state.entry_price            = price
        state.entry_side             = side
        state.entry_bar_count        = state.bar_count
        state.entry_atr              = atr
        state.entry_qty              = qty
        state.trailing_active        = False
        state.trailing_stop          = 0.0
        state.highest_since_entry    = price
        state.lowest_since_entry     = price
        state.total_trades          += 1
        state.daily_trades          += 1

        cfg = self.cfg
        if side == OrderSide.BUY:
            state.stop_loss   = price - atr * cfg.atr_sl_multiplier
            state.take_profit = price + atr * cfg.atr_tp_multiplier
        else:
            state.stop_loss   = price + atr * cfg.atr_sl_multiplier
            state.take_profit = price - atr * cfg.atr_tp_multiplier

        self.submit_market_order(state, side, qty)
        self.log.info(
            f"[{state.symbol}] ENTRY {reason} {side.name} @ {price:.{state.price_precision}f} "
            f"SL={state.stop_loss:.{state.price_precision}f} "
            f"TP={state.take_profit:.{state.price_precision}f} "
            f"qty={qty:.{state.size_precision}f} ATR={atr:.4f}"
        )

    def close_position(self, state: InstrumentState, reason: str) -> None:
        """
        Close an open position with a reduce_only market order.

        Actions:
          - Calculate approximate PnL (before fees)
          - Update win/loss counters
          - Trigger loss-streak pause if threshold reached
          - Submit reduce_only market order
          - Reset all position state fields

        Args:
            state  : instrument state
            reason : label for log (e.g. "SL", "TP", "TRAILING", "TIMEOUT")
        """
        if not state.position_open or state.entry_side is None:
            return

        price = state.last_close
        pnl = (
            (price - state.entry_price)
            if state.entry_side == OrderSide.BUY
            else (state.entry_price - price)
        )

        # Update counters
        if pnl > 0:
            state.wins += 1
            state.consecutive_losses = 0
        else:
            state.losses += 1
            state.consecutive_losses += 1
            if state.consecutive_losses >= self.cfg.max_consecutive_losses:
                state.pause_until_bar    = state.bar_count + self.cfg.pause_bars_after_streak
                state.consecutive_losses = 0
                self.log.warning(
                    f"[{state.symbol}] Loss streak → pausing until bar {state.pause_until_bar}"
                )

        # Submit close order
        close_side = (
            OrderSide.SELL if state.entry_side == OrderSide.BUY else OrderSide.BUY
        )
        qty_str = f"{state.entry_qty:.{state.size_precision}f}"
        order = self.order_factory.market(
            instrument_id=state.instrument_id,
            order_side=close_side,
            quantity=Quantity.from_str(qty_str),
            reduce_only=True,
        )
        self.submit_order(order)
        self.log.info(
            f"[{state.symbol}] EXIT {reason} @ {price:.{state.price_precision}f} "
            f"PnL≈{pnl:.4f} USDT"
        )

        # Reset position state
        state.position_open          = False
        state.entry_price            = 0.0
        state.entry_side             = None
        state.entry_bar_count        = 0
        state.entry_atr              = 0.0
        state.entry_qty              = 0.0
        state.stop_loss              = 0.0
        state.take_profit            = 0.0
        state.trailing_active        = False
        state.trailing_stop          = 0.0
        state.highest_since_entry    = 0.0
        state.lowest_since_entry     = float("inf")
        state.bars_since_last_close  = 0

    def submit_market_order(
        self,
        state: InstrumentState,
        side: OrderSide,
        qty: float,
    ) -> None:
        """
        Submit a raw market order with correct precision.
        Prefer enter_position() / close_position() for managed entries/exits.
        """
        qty_str = f"{qty:.{state.size_precision}f}"
        order = self.order_factory.market(
            instrument_id=state.instrument_id,
            order_side=side,
            quantity=Quantity.from_str(qty_str),
        )
        self.submit_order(order)

    def submit_limit_order(
        self,
        state: InstrumentState,
        side: OrderSide,
        qty: float,
        price: float,
    ) -> None:
        """
        Submit a limit order (maker fee rate) with correct precision.
        Use for strategies that want 0.02% maker fees instead of 0.04/0.05% taker.
        """
        qty_str   = f"{qty:.{state.size_precision}f}"
        price_str = f"{price:.{state.price_precision}f}"
        order = self.order_factory.limit(
            instrument_id=state.instrument_id,
            order_side=side,
            quantity=Quantity.from_str(qty_str),
            price=Price.from_str(price_str),
        )
        self.submit_order(order)

    def calc_position_size(
        self,
        state: InstrumentState,
        atr: float,
        size_mult: float = 1.0,
    ) -> float:
        """
        ATR-based position sizing respecting instrument precision.

        Formula:
            qty = (balance × risk_per_trade_pct) / (ATR × atr_sl_multiplier) × size_mult
            qty = round(qty, state.size_precision)

        Returns 0.0 if sizing fails (insufficient balance or zero ATR).
        """
        balance = self.get_balance()
        if balance <= 0:
            return 0.0
        sl_distance = atr * self.cfg.atr_sl_multiplier
        if sl_distance <= 0:
            return 0.0
        raw_qty = (balance * self.cfg.risk_per_trade_pct / sl_distance) * size_mult
        return round(raw_qty, state.size_precision)

    def get_balance(self) -> float:
        """Return current free USDT balance from portfolio. Returns 0.0 on error."""
        try:
            account = self.portfolio.account(self._venue)
            if account is None:
                return 0.0
            balance = account.balance_free(Currency.from_str("USDT"))
            return float(balance.as_double()) if balance else 0.0
        except Exception:
            return 0.0

    def is_warmup(self, state: InstrumentState) -> bool:
        """Return True if instrument has not yet received enough bars to trade."""
        return state.bar_count < self.cfg.warmup_bars

    # ─────────────────────────────────────────────────────────────────────────
    # Internal — Position Management
    # ─────────────────────────────────────────────────────────────────────────

    def _manage_position(self, bar: Bar, state: InstrumentState) -> None:
        """
        Automatic SL / TP / trailing stop / timeout management.
        Called by on_bar() before on_bar_logic().
        """
        cfg  = self.cfg
        high = float(bar.high)
        low  = float(bar.low)
        atr  = state.entry_atr
        bars_in_trade = state.bar_count - state.entry_bar_count

        if state.entry_side == OrderSide.BUY:
            # Track highest for trailing stop
            state.highest_since_entry = max(state.highest_since_entry, high)

            # Trailing stop activation and ratchet
            if atr > 0:
                unrealized_atr = (state.highest_since_entry - state.entry_price) / atr
                if unrealized_atr >= cfg.trailing_activate_atr:
                    state.trailing_active = True
                    new_trail = state.highest_since_entry - atr * cfg.trailing_distance_atr
                    state.trailing_stop = max(state.trailing_stop, new_trail)

            if state.trailing_active and low <= state.trailing_stop:
                state.last_close = state.trailing_stop  # close at trail level
                self.close_position(state, "TRAILING")
                return
            if low <= state.stop_loss:
                state.last_close = state.stop_loss
                self.close_position(state, "SL")
                return
            if high >= state.take_profit:
                state.last_close = state.take_profit
                self.close_position(state, "TP")
                return

        elif state.entry_side == OrderSide.SELL:
            # Track lowest for trailing stop
            state.lowest_since_entry = min(state.lowest_since_entry, low)

            if atr > 0:
                unrealized_atr = (state.entry_price - state.lowest_since_entry) / atr
                if unrealized_atr >= cfg.trailing_activate_atr:
                    state.trailing_active = True
                    new_trail = state.lowest_since_entry + atr * cfg.trailing_distance_atr
                    if state.trailing_stop <= 0 or new_trail < state.trailing_stop:
                        state.trailing_stop = new_trail

            if state.trailing_active and high >= state.trailing_stop:
                state.last_close = state.trailing_stop
                self.close_position(state, "TRAILING")
                return
            if high >= state.stop_loss:
                state.last_close = state.stop_loss
                self.close_position(state, "SL")
                return
            if low <= state.take_profit:
                state.last_close = state.take_profit
                self.close_position(state, "TP")
                return

        # Timeout exit
        if bars_in_trade >= cfg.max_bars_in_trade:
            self.close_position(state, "TIMEOUT")

    def _is_circuit_open(self, state: InstrumentState) -> bool:
        """Return True if entry is blocked by any circuit breaker."""
        cfg = self.cfg
        return (
            state.daily_trades >= cfg.max_daily_trades
            or state.bars_since_last_close < cfg.cooldown_bars
            or state.bar_count < state.pause_until_bar
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal — Custom Data State Updates
    # ─────────────────────────────────────────────────────────────────────────

    def _update_depth_state(self, item, state: InstrumentState) -> None:
        """Update state.depth_bid / state.depth_ask from a BookDepthData object."""
        pct = item.percentage
        if pct < 0:
            # Ask side: negative percentage = above mid-price
            state.depth_ask[abs(pct)] = item.notional
        else:
            # Bid side: positive percentage = below mid-price
            state.depth_bid[pct] = item.notional

    def _update_metrics_state(self, item, state: InstrumentState) -> None:
        """Update state metrics fields from a MarketMetrics object."""
        state.open_interest        = item.open_interest
        state.open_interest_value  = item.open_interest_value
        state.top_trader_ls_count  = item.top_trader_ls_count
        state.top_trader_ls_pos    = item.top_trader_ls_pos
        state.global_ls_ratio      = item.global_ls_ratio
        state.taker_buy_sell_ratio = item.taker_buy_sell_ratio


# ═══════════════════════════════════════════════════════════════════════════════
# SignalEngineStrategy — Example subclass using live_engine's SignalEngine
# ═══════════════════════════════════════════════════════════════════════════════

class SignalEngineStrategy(MultiAssetStrategy):
    """
    Example: connects the existing live_engine/signal_engine.py to the
    multi-asset base class. One SignalEngine instance per instrument.

    This demonstrates how to plug ANY custom logic into MultiAssetStrategy.
    The infrastructure (state, SL/TP, circuit breakers) is unchanged.
    """

    def __init__(self, config: MultiAssetStrategyConfig):
        super().__init__(config)
        self._signal_engines: dict[InstrumentId, object] = {}

    def on_start(self) -> None:
        super().on_start()
        # Import here to avoid hard dependency when using other strategies
        try:
            from live_engine.signal_engine import SignalEngine, CVDTracker
            from live_engine.config import TradingConfig

            for iid in self._states:
                live_cfg = TradingConfig()
                engine   = SignalEngine(live_cfg)
                self._signal_engines[iid] = engine
                # Store CVD tracker in custom state
                self._states[iid].custom["cvd_tracker"] = CVDTracker()

            self.log.info(
                f"[SignalEngineStrategy] Created {len(self._signal_engines)} "
                f"SignalEngine instances"
            )
        except ImportError as e:
            self.log.error(f"[SignalEngineStrategy] Cannot import live_engine: {e}")

    def on_trade_tick_logic(
        self, tick: TradeTick, state: InstrumentState
    ) -> None:
        """Feed ticks to CVD tracker."""
        tracker = state.custom.get("cvd_tracker")
        if tracker is None:
            return
        is_buyer_maker = (tick.aggressor_side == AggressorSide.SELLER)
        tracker.update(float(tick.size), is_buyer_maker)

    def on_bar_logic(
        self, bar: Bar, bar_type: BarType, state: InstrumentState
    ) -> None:
        """Feed VALUE bars to SignalEngine and act on returned signals."""
        if "VALUE" not in str(bar_type):
            return   # only process VALUE bars; ignore kline bars here

        engine = self._signal_engines.get(state.instrument_id)
        if engine is None:
            return

        # Feed bar to signal engine
        from live_engine.signal_engine import VolumeBar
        signal = engine.on_volume_bar(VolumeBar(
            open=state.last_close,
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
        ))

        if signal is None or self.is_warmup(state):
            return
        if self._is_circuit_open(state):
            return
        if state.position_open:
            return

        side      = OrderSide.BUY if signal.side == "BUY" else OrderSide.SELL
        size_mult = 0.5 if signal.regime.name == "VOLATILE" else 1.0
        self.enter_position(
            state, side, signal.atr,
            reason=signal.type.name,
            size_mult=size_mult,
        )
