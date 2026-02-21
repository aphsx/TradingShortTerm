import asyncio
import ccxt.pro as ccxtpro
from config import API_KEY, SECRET_KEY, TESTNET, TRADING_PAIRS
from storage import DataStorage
from engines import Engine1OrderFlow, Engine2Tick, Engine3Technical, Engine4Sentiment, Engine5Regime
from core import DecisionEngine, RiskManager, Executor
import datetime
import traceback

class VortexBot:
    def __init__(self):
        self.storage = DataStorage()
        self.e1 = Engine1OrderFlow()
        self.e2 = Engine2Tick()
        self.e3 = Engine3Technical()
        self.e4 = Engine4Sentiment()
        self.e5 = Engine5Regime()
        self.decision = DecisionEngine()
        self.risk = RiskManager()
        
        # Initialize CCXT Pro using the specific Futures exchange class
        exchange_config = {
            'apiKey': API_KEY,
            'secret': SECRET_KEY,
            'enableRateLimit': True
        }
            
        self.exchange = ccxtpro.binanceusdm(exchange_config)
        
        if TESTNET:
            print("🚀 Connecting to Binance Futures Demo Trading (CCXT Natively Supported)")
            self.exchange.enable_demo_trading(True)
            
        self.executor = Executor(exchange_instance=self.exchange, testnet=TESTNET)
        # For ccxt.binanceusdm, Linear Futures use BASE/QUOTE:SETTLE standard (BTC/USDT:USDT)
        self.ccxt_symbols = [f"{s.replace('USDT', '')}/USDT:USDT" for s in TRADING_PAIRS]

    async def watch_ob_for_symbol(self, symbol):
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        while True:
            try:
                ob = await self.exchange.watch_order_book(symbol)
                # Parse to ensure values are string/float arrays matching Engine expectations
                bids = [[str(b[0]), str(b[1])] for b in ob.get('bids', [])[:20]]
                asks = [[str(a[0]), str(a[1])] for a in ob.get('asks', [])[:20]]
                self.storage.set_orderbook(raw_sym, bids, asks)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"WS OB {symbol} Error: {e}")
                await asyncio.sleep(2)

    async def watch_tr_for_symbol(self, symbol):
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        while True:
            try:
                trades = await self.exchange.watch_trades(symbol)
                for t in trades:
                    # Tick format: {'q': qty, 'm': isBuyerMaker (True if sell)}
                    tick_data = {'q': t.get('amount', 0), 'm': t.get('side', 'buy') == 'sell'}
                    self.storage.add_tick(raw_sym, tick_data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"WS TR {symbol} Error: {e}")
                await asyncio.sleep(2)
                
    async def watch_klines_for_symbol(self, symbol, timeframe='1m'):
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        while True:
            try:
                klines = await self.exchange.watch_ohlcv(symbol, timeframe)
                # Store the most recent 100 candles locally
                self.storage.set_klines(raw_sym, timeframe, klines[-100:])
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"WS Kline {symbol} Error: {e}")
                await asyncio.sleep(2)

    async def trade_loop(self):
        print("Trading loop started...")
        while True:
            try:
                for symbol in self.ccxt_symbols:
                    raw_sym = symbol.replace('/', '').replace(':USDT', '')
                    ob = self.storage.get_orderbook(raw_sym)
                    ticks = self.storage.get_ticks(raw_sym)
                    
                    # Fast local memory access (0ms latency, Zero API limit hit)
                    klines = self.storage.get_klines(raw_sym, '1m')
                        
                    s1 = self.e1.process(ob, ticks)
                    s2 = self.e2.process(ticks)
                    s3 = self.e3.process(klines)
                    s4 = self.e4.process({})
                    s5 = self.e5.process(klines)
                    
                    signals = {"e1": s1, "e2": s2, "e3": s3, "e4": s4}
                    dec = self.decision.evaluate(signals, s5)
                    
                    current_time = datetime.datetime.now().strftime('%H:%M:%S')
                    price = s1.get("micro_price", 0)
                    
                    if dec["action"] == "NO_TRADE":
                        reason = "Wait"
                        if not ticks: reason = "No Ticks"
                        elif not ob.get("bids"): reason = "No Orderbook"
                        elif abs(dec.get("final_score", 0)) < 0.55: reason = f"Low Score ({dec.get('final_score',0):.2f})"
                        
                        print(f"[{current_time}] {raw_sym} | P: {price:.2f} | Action: SKIP | R: {reason}")
                    else:
                        print(f"[{current_time}] {raw_sym} | P: {price:.2f} | Action: {dec['action']} | Strat: {dec['strategy']} | Score: {dec['final_score']:.2f} | Conf: {dec['confidence']:.1f}%")
                        
                        if price > 0:
                            risk_params = self.risk.calculate(dec, price, s3.get('atr', 0), s5.get('param_overrides', {}))
                            order = await self.executor.execute_trade(raw_sym, dec, risk_params, price)
                            if order:
                                if order.get("status", "SUCCESS") == "SUCCESS":
                                    self.storage.set_position(raw_sym, order)
                                # Save to Supabase (Granular Order/Execution Metrics)
                                self.storage.save_trade({
                                    "symbol": order.get("symbol", raw_sym),
                                    "side": order.get("side", dec["action"]),
                                    "strategy": order.get("strategy", dec["strategy"]),
                                    
                                    "order_id": order.get("order_id"),
                                    "client_order_id": order.get("client_order_id"),
                                    "execution_type": order.get("execution_type"),
                                    "api_latency_ms": order.get("api_latency_ms"),
                                    "status": order.get("status"),
                                    "error_type": order.get("error_type"),
                                    "error_msg": order.get("error_msg"),
                                    
                                    "entry_price": order.get("price", 0),
                                    "size_usdt": order.get("quantity", 0) * order.get("price", 0),
                                    "leverage": risk_params.get("leverage", 1),
                                    "sl_price": order.get("sl_price", 0),
                                    "tp1_price": order.get("tp_price", 0),
                                    
                                    "confidence": dec.get("confidence", 0),
                                    "final_score": dec.get("final_score", 0)
                                })
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Trade Loop Error: {e}")
                traceback.print_exc()
            
            await asyncio.sleep(2)

    async def run(self):
        print(f"Starting VORTEX-7 Engine via CCXT.PRO... (TESTNET: {TESTNET})")
        print(f"Connecting to streams: {self.ccxt_symbols}")
        
        loop_tasks = []
        for sym in self.ccxt_symbols:
            loop_tasks.append(asyncio.create_task(self.watch_ob_for_symbol(sym)))
            loop_tasks.append(asyncio.create_task(self.watch_tr_for_symbol(sym)))
            loop_tasks.append(asyncio.create_task(self.watch_klines_for_symbol(sym, '1m')))
        
        loop_tasks.append(asyncio.create_task(self.trade_loop()))
        
        print("Listening for marketplace data...")
        try:
            await asyncio.gather(*loop_tasks)
        except asyncio.CancelledError:
            print("Shutdown requested...")
        finally:
            print("Releasing CCXT sessions safely...")
            await self.exchange.close()

if __name__ == "__main__":
    bot = VortexBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nBot gracefully shut down by user. Goodbye!")
