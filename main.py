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
        
        from config import BINANCE_FUTURES_REST_URL, BINANCE_FUTURES_WS_URL
        
        # Initialize CCXT Pro Exchange (supports REST and WebSockets natively)
        exchange_config = {
            'apiKey': API_KEY,
            'secret': SECRET_KEY,
            'options': {
                'defaultType': 'future',
                'warnOnFetchOpenOrdersWithoutSymbol': False
            },
            'enableRateLimit': True
        }
        
        # Override URLs if user specified them in .env
        if BINANCE_FUTURES_REST_URL:
            exchange_config['urls'] = {
                'api': {
                    'public': BINANCE_FUTURES_REST_URL.rstrip('/') + '/fapi/v1',
                    'private': BINANCE_FUTURES_REST_URL.rstrip('/') + '/fapi/v1',
                },
                'test': {
                    'public': BINANCE_FUTURES_REST_URL.rstrip('/') + '/fapi/v1',
                    'private': BINANCE_FUTURES_REST_URL.rstrip('/') + '/fapi/v1',
                }
            }
            
        self.exchange = ccxtpro.binance(exchange_config)
        
        if TESTNET:
            print("🚀 Configuring Testnet Sandbox Mode on CCXT")
            self.exchange.set_sandbox_mode(True)
            
        self.executor = Executor(exchange_instance=self.exchange, testnet=TESTNET)
        # Prepare trading symbols for CCXT format (e.g., BTCUSDT -> BTC/USDT:USDT or BTC/USDT)
        # Linear futures on CCXT Binance typically use BASE/QUOTE
        self.ccxt_symbols = [s.replace('USDT', '/USDT') for s in TRADING_PAIRS]

    async def watch_ob_for_symbol(self, symbol):
        raw_sym = symbol.replace('/', '')
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
        raw_sym = symbol.replace('/', '')
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
        raw_sym = symbol.replace('/', '')
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
                    raw_sym = symbol.replace('/', '')
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
                                # Save to Supabase (Record all outcomes)
                                self.storage.save_trade({
                                    "symbol": order["symbol"],
                                    "side": order["side"],
                                    "strategy": order["strategy"],
                                    "size_usdt": order["quantity"] * order["price"],
                                    "entry_price": order["price"],
                                    "sl_price": order["sl_price"],
                                    "tp1_price": order["tp_price"],
                                    "leverage": risk_params["leverage"],
                                    "status": order.get("status", "SUCCESS"),
                                    "error_msg": order.get("error_msg", "")
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
