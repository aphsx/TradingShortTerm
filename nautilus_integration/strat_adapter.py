from datetime import timedelta
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

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

    def on_start(self):
        """Called when backtest or live starts"""
        self.instrument_id = self.config.instrument_id
        
        # Subscribe to necessary data streams
        self.subscribe_bars(self.instrument_id, interval="1m")
        self.subscribe_order_book(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        
        self.log.info(f"VORTEX-7 Nautilus Adapter started for {self.instrument_id}")

    def on_bar(self, bar):
        """Called every time a 1m candle closes"""
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
            'p': float(tick.mid_price())
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
        
        if decision['action'] == "NO_TRADE":
            return

        # 2. Risk Check
        current_price = self.cache.price(self.instrument_id)
        atr = signals['e3'].get('atr', current_price * 0.002)
        params = e5_filter.get('param_overrides', {})
        
        risk_results = self.risk_manager.calculate(decision, current_price, atr, params)
        
        if risk_results['action'] == "NO_TRADE":
            self.log.info(f"Risk Rejected: {risk_results['reason']}")
            return

        # 3. Execution via Nautilus
        self._submit_order(decision, risk_results)

    def _submit_order(self, decision, risk):
        side = OrderSide.BUY if decision['action'] == "LONG" else OrderSide.SELL
        
        # Calculate quantity based on position_size_usdt
        px = self.cache.price(self.instrument_id)
        qty = risk['position_size_usdt'] / px
        
        # Nautilus handles precision automatically if configured properly
        order = self.order_factory.market_order(
            instrument_id=self.instrument_id,
            side=side,
            quantity=self.instrument_id.make_quantity(qty),
        )
        
        self.submit_order(order)
        self.log.info(f"VORTEX-7 Order Submitted: {decision['action']} | Strategy: {decision['strategy']} | Confidence: {decision['confidence']:.1f}%")

