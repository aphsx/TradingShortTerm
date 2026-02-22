from datetime import timedelta
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
        
        # 3. Last known signals to prevent AttributeError
        self.last_e1 = {"vpin": 0.5, "ofi_velocity": 2.0} # Backtest pass defaults
        self.last_e2 = {"alignment": 0.5}
        
        self.bar_count = 0
        self.rejection_reasons = {}

    def on_start(self):
        """Called when backtest or live starts"""
        self.instrument_id = self.config.instrument_id
        
        # Define BarType for 1-minute bars
        bar_type = BarType.from_str(f"{self.instrument_id}-1-MINUTE-LAST-EXTERNAL")
        
        # Subscribe to necessary data streams
        self.subscribe_bars(bar_type)
        # Order book/ticks won't data feed in this bar-only backtest, 
        # but kept for live-code compatibility
        self.subscribe_order_book_depth(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        
        self.log.info(f"VORTEX-7 Nautilus Adapter started for {self.instrument_id}")

    def on_stop(self):
        """Called when backtest ends"""
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

        # Run Regime and Technical indicators
        e5_filter = self.e5.process(self.klines_history)
        e3_signal = self.e3.process(self.klines_history)
        
        # Trigger evaluation if we have enough data
        if len(self.klines_history) >= 30:
            self._evaluate_and_execute(e3=e3_signal, e5=e5_filter)

    def on_order_book(self, order_book):
        """Called on every L2 update"""
        # Convert to format expected by E1
        book_dict = nautilus_book_to_dict(order_book)
        
        # Engine 1 needs orderbook and recent ticks
        e1_signal = self.e1.process(book_dict, self.tick_history, str(self.instrument_id))
        
        # We don't trigger trade on EVERY book update to save CPU, 
        # but we use it for signal preparation
        self.last_e1 = e1_signal

    def on_quote_tick(self, tick):
        """Called on every tick/trade"""
        # Logic for E2 (Tick Engine)
        # Format: {'q': volume, 'm': is_buyer_maker, 'p': price}
        tick_data = {
            'q': float(tick.ask_size + tick.bid_size) / 2, # Approximation for quote tick
            'm': False, # Nautilus QuoteTicks don't have side, TradeTicks do
            'p': float(tick.mid_price()) if hasattr(tick, 'mid_price') else float((tick.ask_price + tick.bid_price) / 2)
        }
        self.tick_history.append(tick_data)
        if len(self.tick_history) > self.max_tick_history:
            self.tick_history.pop(0)
            
        e2_signal = self.e2.process(self.tick_history, str(self.instrument_id))
        self.last_e2 = e2_signal

    def _evaluate_and_execute(self, **signals_override):
        """Core decision loop triggered by bars or high-conviction ticks"""
        # Prepare signal bundle for DecisionEngine
        signals = {
            'e1': getattr(self, 'last_e1', {}),
            'e2': getattr(self, 'last_e2', {}),
            'e3': signals_override.get('e3', {}),
            'e4': {} # Sentiment often missing in backtests
        }
        
        e5_filter = signals_override.get('e5', {})
        
        # 1. Decision
        decision = self.decision_engine.evaluate(signals, e5_filter)
        
        if decision.get('action') == "NO_TRADE":
            reason = decision['reason']
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
            # Log each unique reason up to 3 times to explain why backtest is quiet
            if self.rejection_reasons[reason] <= 3:
                self.log.info(f"Decision Reject [{self.bar_count}]: {reason}")
            return

        # 2. Risk Check
        price_obj = self.cache.price(self.instrument_id, PriceType.LAST)
        current_price = float(price_obj) if price_obj else signals['e3'].get('close', 0.0)
        
        if current_price == 0:
            return # Cannot trade without price
            
        atr = signals['e3'].get('atr', current_price * 0.002)
        params = e5_filter.get('param_overrides', {})
        
        risk_results = self.risk_manager.calculate(decision, current_price, atr, params)
        
        if risk_results.get('action') == "NO_TRADE":
            self.log.info(f"Risk Rejected: {risk_results['reason']}")
            return

        # 3. Execution via Nautilus
        self._submit_order(decision, risk_results)

    def _submit_order(self, decision, risk):
        side = OrderSide.BUY if decision['action'] == "LONG" else OrderSide.SELL
        
        # Calculate quantity based on position_size_usdt
        px = float(self.cache.price(self.instrument_id, PriceType.LAST))
        qty = risk['position_size_usdt'] / px
        
        # Get instrument for quantity formatting
        instrument = self.cache.instrument(self.instrument_id)
        
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=instrument.make_qty(qty),
        )
        
        self.submit_order(order)
        self.log.info(f"VORTEX-7 Order Submitted: {decision['action']} | Strategy: {decision['strategy']} | Confidence: {decision['confidence']:.1f}%")

