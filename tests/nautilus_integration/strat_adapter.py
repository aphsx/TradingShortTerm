from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.enums import OrderSide, TimeInForce, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import BarType

# Import existing logic
from engines import Engine1OrderFlow, Engine2Tick, Engine3Technical, Engine4Sentiment, Engine5Regime
from core import DecisionEngine, RiskManager
from .data_utils import nautilus_bar_to_list, nautilus_book_to_dict

class VortexNautilusAdapter(Strategy):
    """
    Adapter strategy that plugs VORTEX-7 engines into NautilusTrader.
    This allows running the EXACT same logic in backtests and live.

    Bar-only backtest mode:
    - E3 (Technical) + E5 (Regime) run on real bar data
    - E2 is simulated from OHLCV bar structure (bullish/bearish momentum)
    - E1/E4 use neutral defaults (no orderbook/sentiment data available)
    - Positions are managed internally with TP/SL hit check per bar
    """
    def __init__(self, config):
        super().__init__(config)

        # 1. Initialize VORTEX-7 Brains
        self.e1 = Engine1OrderFlow()
        self.e2 = Engine2Tick()
        self.e3 = Engine3Technical()
        self.e4 = Engine4Sentiment()
        self.e5 = Engine5Regime()
        self.decision_engine = DecisionEngine()
        self.risk_manager = RiskManager()

        # 2. State tracking
        self.instrument_id = None
        self.klines_history = []
        self.tick_history = []
        self.max_kline_history = 100
        self.max_tick_history = 1000

        # 3. Neutral defaults for signals not available in bar-only backtest
        self.last_e1 = {"direction": None, "strength": 0.0, "conviction": 1.0, "vpin": 0.5, "ofi_velocity": 2.0}
        self.last_e4 = {}

        self.bar_count = 0
        self.rejection_reasons = {}

        # 4. Position management for backtest
        # Nautilus backtest won't auto-close on SL/TP — we manage this ourselves per bar
        self.in_position = False
        self.position_side = None   # "LONG" or "SHORT"
        self.entry_price = 0.0
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.entry_bar = 0
        self.max_hold_bars = 20     # Up to 20 bars (20 min): let winners run
        self.bars_since_close = 99  # Start ready to trade immediately
        self.min_bars_between_trades = 3  # 3-bar cooldown: reduce over-trading frequency

        # 5. E2 streak tracking — counts consecutive same-direction bars for bar-only backtest
        self._bull_streak = 0
        self._bear_streak = 0

    def on_start(self):
        """Called when backtest or live starts"""
        self.instrument_id = self.config.instrument_id

        # Define BarType for 1-minute bars
        bar_type = BarType.from_str(f"{self.instrument_id}-1-MINUTE-LAST-EXTERNAL")

        # Subscribe to necessary data streams
        self.subscribe_bars(bar_type)
        # Order book/ticks won't feed in bar-only backtest,
        # but kept for live-code compatibility
        self.subscribe_order_book_depth(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)

        self.log.info(f"VORTEX-7 Nautilus Adapter started for {self.instrument_id}")

    def on_stop(self):
        """Called when backtest ends"""
        # Close any open position at end
        if self.in_position:
            self._close_position("End of backtest")

        self.log.info("--- Backtest Complete Summary ---")
        self.log.info(f"Total Bars Processed: {self.bar_count}")
        self.log.info("Rejection Summary:")
        for reason, count in self.rejection_reasons.items():
            self.log.info(f"  - {reason}: {count}")
        self.log.info("---------------------------------")

    def on_bar(self, bar):
        """Called every time a 1m candle closes"""
        self.bar_count += 1
        if self.bar_count % 5000 == 0:
            self.log.info(f"Backtest Progress: {self.bar_count} bars processed...")

        # Convert to format expected by E3 & E5
        kline = nautilus_bar_to_list(bar)
        self.klines_history.append(kline)

        if len(self.klines_history) > self.max_kline_history:
            self.klines_history.pop(0)

        # --- Step 1: Manage open position (check TP/SL/timeout) ---
        if self.in_position:
            self._manage_position(bar)
            # After managing, if still in position don't enter new one
            if self.in_position:
                return

        # --- Step 2: Count cooldown between trades ---
        self.bars_since_close += 1
        if self.bars_since_close < self.min_bars_between_trades:
            return

        # --- Step 3: Run indicators and evaluate entry ---
        if len(self.klines_history) >= 30:
            e5_filter = self.e5.process(self.klines_history)
            e3_signal = self.e3.process(self.klines_history)
            # Simulate E2 from bar structure (bar-only backtest mode)
            simulated_e2 = self._simulate_e2_from_bar(bar)
            self._evaluate_and_execute(e3=e3_signal, e5=e5_filter, e2_sim=simulated_e2)

    def _simulate_e2_from_bar(self, bar):
        """
        Simulate tick-derived E2 momentum signal from bar OHLCV.
        In bar-only backtest, real tick data is unavailable.

        Key improvements for scalping backtest:
        - Tracks actual consecutive same-direction bars (streak) using instance state.
        - Detects volume spikes vs recent average volume (last 20 bars).
        - Computes velocity_ratio from current bar body vs recent average body.
        - All values match the live E2 format so strategies can fire properly.
        """
        if len(self.klines_history) < 2:
            return {"direction": "NEUTRAL", "strength": 0.0, "velocity_ratio": 1.0,
                    "aggressor_ratio": 0.5, "alignment": 0.0, "streak": 0,
                    "volume_spike": False, "spike_ratio": 1.0}

        curr_open  = float(bar.open)
        curr_close = float(bar.close)
        curr_vol   = float(bar.volume)
        prev_close = float(self.klines_history[-2][4])

        body_pct = abs(curr_close - curr_open) / curr_open if curr_open > 0 else 0
        strength  = min(1.0, body_pct * 200)   # 0.5% body → strength 1.0

        bull = curr_close > curr_open and curr_close > prev_close
        bear = curr_close < curr_open and curr_close < prev_close

        # --- Streak tracking (consecutive same-direction bars) ---
        if bull:
            self._bull_streak += 1
            self._bear_streak = 0
            direction = "MOMENTUM_LONG"
            streak = self._bull_streak
            aggressor_ratio = min(0.9, 0.55 + strength * 0.3)
            alignment = min(1.0, 0.4 + self._bull_streak * 0.12)
        elif bear:
            self._bear_streak += 1
            self._bull_streak = 0
            direction = "MOMENTUM_SHORT"
            streak = self._bear_streak
            aggressor_ratio = max(0.1, 0.45 - strength * 0.3)
            alignment = min(1.0, 0.4 + self._bear_streak * 0.12)
        else:
            self._bull_streak = 0
            self._bear_streak = 0
            direction = "NEUTRAL"
            streak = 0
            aggressor_ratio = 0.5
            alignment = 0.0

        # --- Volume spike detection vs recent 20-bar average ---
        recent_vols = [float(k[5]) for k in self.klines_history[-20:] if float(k[5]) > 0]
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else curr_vol
        spike_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
        volume_spike = spike_ratio > 1.5

        # --- Velocity ratio: current body vs recent 10-bar average body ---
        recent_bodies = [
            abs(float(k[4]) - float(k[1])) / float(k[1])
            for k in self.klines_history[-10:]
            if float(k[1]) > 0
        ]
        avg_body = sum(recent_bodies) / len(recent_bodies) if recent_bodies else body_pct
        velocity_ratio = (body_pct / avg_body) if avg_body > 0 else 1.0
        velocity_ratio = max(0.1, min(5.0, velocity_ratio))

        return {
            "direction": direction,
            "strength": strength,
            "velocity_ratio": velocity_ratio,
            "aggressor_ratio": aggressor_ratio,
            "alignment": alignment,
            "streak": streak,
            "volume_spike": volume_spike,
            "spike_ratio": spike_ratio
        }

    def on_order_book(self, order_book):
        """Called on every L2 update"""
        book_dict = nautilus_book_to_dict(order_book)
        e1_signal = self.e1.process(book_dict, self.tick_history, str(self.instrument_id))
        self.last_e1 = e1_signal

    def on_quote_tick(self, tick):
        """Called on every tick/trade"""
        tick_data = {
            'q': float(tick.ask_size + tick.bid_size) / 2,
            'm': False,
            'p': float(tick.mid_price()) if hasattr(tick, 'mid_price') else float((tick.ask_price + tick.bid_price) / 2)
        }
        self.tick_history.append(tick_data)
        if len(self.tick_history) > self.max_tick_history:
            self.tick_history.pop(0)

        e2_signal = self.e2.process(self.tick_history, str(self.instrument_id))
        self.last_e2_live = e2_signal

    def _manage_position(self, bar):
        """
        Check bar high/low against TP/SL and check max hold time.
        For LONG: SL if bar.low <= sl_price, TP if bar.high >= tp_price.
        For SHORT: SL if bar.high >= sl_price, TP if bar.low <= tp_price.

        Scalping enhancement: move SL to breakeven once 50% of TP distance is covered.
        This locks in a no-loss exit even if the trade reverses before hitting TP.
        """
        bar_high  = float(bar.high)
        bar_low   = float(bar.low)
        bar_close = float(bar.close)
        bars_held = self.bar_count - self.entry_bar

        # --- Trailing stop: two-stage profit protection ---
        # Stage 1 (≥50% TP): move SL to entry (breakeven — no loss possible)
        # Stage 2 (≥75% TP): trail SL to 50% of TP distance (lock partial profit)
        if self.position_side == "LONG":
            tp_dist = self.tp_price - self.entry_price
            if tp_dist > 0:
                profit_pct = (bar_close - self.entry_price) / tp_dist
                if profit_pct >= 0.75:
                    new_sl = self.entry_price + tp_dist * 0.50  # Lock 50% of move
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl
                elif profit_pct >= 0.50:
                    new_sl = self.entry_price  # Breakeven
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl
        elif self.position_side == "SHORT":
            tp_dist = self.entry_price - self.tp_price
            if tp_dist > 0:
                profit_pct = (self.entry_price - bar_close) / tp_dist
                if profit_pct >= 0.75:
                    new_sl = self.entry_price - tp_dist * 0.50  # Lock 50% of move
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl
                elif profit_pct >= 0.50:
                    new_sl = self.entry_price  # Breakeven
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl

        close_reason = None

        if self.position_side == "LONG":
            if bar_low <= self.sl_price:
                close_reason = f"SL hit @ {self.sl_price:.2f} (low={bar_low:.2f})"
            elif bar_high >= self.tp_price:
                close_reason = f"TP hit @ {self.tp_price:.2f} (high={bar_high:.2f})"
        elif self.position_side == "SHORT":
            if bar_high >= self.sl_price:
                close_reason = f"SL hit @ {self.sl_price:.2f} (high={bar_high:.2f})"
            elif bar_low <= self.tp_price:
                close_reason = f"TP hit @ {self.tp_price:.2f} (low={bar_low:.2f})"

        if bars_held >= self.max_hold_bars and close_reason is None:
            close_reason = f"Max hold {self.max_hold_bars} bars (close={bar_close:.2f})"

        if close_reason:
            self._close_position(close_reason)

    def _close_position(self, reason):
        """Close the current open position using Nautilus close_position() API."""
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            self.in_position  = False
            self.position_side = None
            return

        pnl_estimate = ""
        price_obj = self.cache.price(self.instrument_id, PriceType.LAST)
        if price_obj:
            current_price = float(price_obj)
            if self.position_side == "LONG":
                pnl_estimate = f" | est PnL: {(current_price - self.entry_price) / self.entry_price * 100:.2f}%"
            else:
                pnl_estimate = f" | est PnL: {(self.entry_price - current_price) / self.entry_price * 100:.2f}%"

        # Use Nautilus Strategy.close_position() — works correctly in NETTING mode
        for position in positions:
            self.close_position(position)

        self.log.info(f"CLOSE {self.position_side} | {reason}{pnl_estimate}")

        self.in_position      = False
        self.position_side    = None
        self.bars_since_close = 0

    def _evaluate_and_execute(self, **signals_override):
        """Core decision loop triggered by bars"""
        e2_sim    = signals_override.get('e2_sim', {})
        e5_filter = signals_override.get('e5', {})

        # Use simulated E2 for bar-only backtest; live E2 if real ticks exist
        e2_to_use = getattr(self, 'last_e2_live', e2_sim) if self.tick_history else e2_sim

        signals = {
            'e1': self.last_e1,             # Neutral defaults (no orderbook in bar backtest)
            'e2': e2_to_use,                # Simulated or live tick momentum
            'e3': signals_override.get('e3', {}),
            'e4': self.last_e4              # No sentiment data in backtest
        }

        # --- Bar-only backtest weight redistribution ---
        # E1 weight is normally 15-45% but provides zero signal without orderbook data.
        # Redistribute its weight to E3 (70%) and E2 (30%) so signals are meaningful.
        if not self.tick_history:
            raw_weights = dict(e5_filter.get('weight_overrides', {
                'e1': 0.35, 'e2': 0.25, 'e3': 0.20, 'e4': 0.12
            }))
            e1_w = raw_weights.get('e1', 0.35)
            raw_weights['e3'] = raw_weights.get('e3', 0.20) + e1_w * 0.70
            raw_weights['e2'] = raw_weights.get('e2', 0.25) + e1_w * 0.30
            raw_weights['e1'] = 0.0
            e5_filter = dict(e5_filter)
            e5_filter['weight_overrides'] = raw_weights

        # 1. Decision
        decision = self.decision_engine.evaluate(signals, e5_filter)

        if decision.get('action') == "NO_TRADE":
            reason = decision['reason']
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
            if self.rejection_reasons[reason] <= 3:
                self.log.info(f"Decision Reject [{self.bar_count}]: {reason}")
            return

        # Minimum confidence gate: only trade when signals are genuinely strong.
        # Raising from 10 → 35 dramatically reduces noise trades and fee bleed.
        MIN_CONFIDENCE = 35.0
        if decision.get('confidence', 0) < MIN_CONFIDENCE:
            reason = f"Low confidence ({decision['confidence']:.1f}% < {MIN_CONFIDENCE}%)"
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
            return

        # 2. Risk Check
        price_obj = self.cache.price(self.instrument_id, PriceType.LAST)
        current_price = float(price_obj) if price_obj else signals['e3'].get('close', 0.0)

        if current_price == 0:
            return

        atr    = signals['e3'].get('atr', current_price * 0.002)
        params = e5_filter.get('param_overrides', {})

        # ATR filter: only trade when market is volatile enough for TP to clear fees.
        # Need ATR > 0.35% of price so that 1.2–1.5× ATR TP covers round-trip cost (0.45%).
        min_atr_pct = 0.0035  # 0.35% of price
        if current_price > 0 and atr < current_price * min_atr_pct:
            reason = f"ATR too small ({atr/current_price*100:.3f}% < {min_atr_pct*100:.2f}% — market too quiet)"
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
            return

        risk_results = self.risk_manager.calculate(decision, current_price, atr, params)

        if risk_results.get('action') == "NO_TRADE":
            self.log.info(f"Risk Rejected: {risk_results['reason']}")
            return

        # 3. Execution via Nautilus
        self._submit_order(decision, risk_results)

    def _submit_order(self, decision, risk):
        from config import BASE_BALANCE

        side = OrderSide.BUY if decision['action'] == "LONG" else OrderSide.SELL

        px = float(self.cache.price(self.instrument_id, PriceType.LAST))

        # Cap position size to 2× account balance to limit absolute fee exposure.
        # With correct min_tp (0.45%) enforced in RiskManager, TP will always
        # exceed fees — but keeping notional tighter ensures fee-to-profit ratio stays sane.
        max_notional  = BASE_BALANCE * 2
        pos_size_usdt = min(risk['position_size_usdt'], max_notional)
        qty = pos_size_usdt / px

        instrument = self.cache.instrument(self.instrument_id)

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=instrument.make_qty(qty),
        )

        self.submit_order(order)

        # Record entry info for position management
        self.in_position   = True
        self.position_side = decision['action']
        self.entry_price   = px
        self.entry_bar     = self.bar_count

        sl_dist = risk['sl_distance']
        tp_dist = risk['tp1_distance']

        if decision['action'] == "LONG":
            self.sl_price = px - sl_dist
            self.tp_price = px + tp_dist
        else:
            self.sl_price = px + sl_dist
            self.tp_price = px - tp_dist

        self.log.info(
            f"OPEN {decision['action']} @ {px:.2f} | "
            f"TP={self.tp_price:.2f} SL={self.sl_price:.2f} | "
            f"Strategy={decision['strategy']} Conf={decision['confidence']:.1f}%"
        )
