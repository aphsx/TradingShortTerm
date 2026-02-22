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
        
        # Pre-fetch historical candles to bootstrap indicator math
        try:
            hist = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=96)
            self.storage.set_klines(raw_sym, timeframe, hist)
        except Exception as e:
            print(f"Prefetch Kline Error for {symbol}: {e}")
            
        while True:
            try:
                new_klines = await self.exchange.watch_ohlcv(symbol, timeframe)
                current_klines = self.storage.get_klines(raw_sym, timeframe)
                
                curr_dict = {k[0]: k for k in current_klines}
                for k in new_klines:
                    curr_dict[k[0]] = k
                    
                merged = sorted(curr_dict.values(), key=lambda x: x[0])[-96:]
                self.storage.set_klines(raw_sym, timeframe, merged)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"WS Kline {symbol} {timeframe} Error: {e}")
                await asyncio.sleep(2)

    async def poll_sentiment_data(self, symbol):
        """Polls REST endpoints every 30 seconds for Engine 4."""
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        
        while True:
            try:
                # 1. Fetch Open Interest
                try:
                    oi_res = await self.exchange.fetch_open_interest(symbol)
                    oi = oi_res.get('openInterestAmount', 0) if oi_res else 0
                except Exception:
                    oi = 0
                
                # Fetching Long/Short ratios typically requires implicit API calls in CCXT 
                # binance futures specific endpoints:
                
                try:
                    # 2. Fetch Global Long/Short Ratio
                    ls_ratio_res = await self.exchange.fapiData_get_globallongshortaccountratio({'symbol': raw_sym, 'period': '5m', 'limit': 1})
                    ls_ratio = float(ls_ratio_res[0].get('longShortRatio', 1.0)) if ls_ratio_res else 1.0
                    long_pct = float(ls_ratio_res[0].get('longAccount', 0.5)) if ls_ratio_res else 0.5
                    short_pct = float(ls_ratio_res[0].get('shortAccount', 0.5)) if ls_ratio_res else 0.5
                    
                    # 3. Fetch Top Trader Long/Short Ratio
                    top_ls_res = await self.exchange.fapiData_get_toplongshortaccountratio({'symbol': raw_sym, 'period': '5m', 'limit': 1})
                    top_long_pct = float(top_ls_res[0].get('longAccount', 0.5)) if top_ls_res else 0.5
                except Exception:
                    # Binance Testnet does not support fapiData endpoints
                    ls_ratio, long_pct, short_pct, top_long_pct = 1.0, 0.5, 0.5, 0.5
                
                # 4. Fetch Funding Rate
                try:
                    funding_res = await self.exchange.fetch_funding_rate(symbol)
                    funding_rate = funding_res.get('fundingRate', 0) if funding_res else 0
                except Exception:
                    funding_rate = 0
                
                data = {
                    "open_interest": oi,
                    "ls_ratio": ls_ratio,
                    "long_account_pct": long_pct,
                    "short_account_pct": short_pct,
                    "top_trader_long_pct": top_long_pct,
                    "funding_rate": funding_rate
                }
                
                self.storage.set_sentiment(raw_sym, data)
                if symbol == "ETH/USDT:USDT" or symbol == "BTC/USDT:USDT":
                    print(f"DEBUG: Successfully stored SNT for {symbol}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Sentiment Poll Error for {symbol}: {e}")
                
            # Wait 30 seconds before next poll to conserve weight limits
            await asyncio.sleep(30)

    async def trade_loop(self):
        print("Trading loop started...")
        while True:
            try:
                for symbol in self.ccxt_symbols:
                    raw_sym = symbol.replace('/', '').replace(':USDT', '')
                    ob = self.storage.get_orderbook(raw_sym)
                    ticks = self.storage.get_ticks(raw_sym)
                    
                    # Fast local memory access (0ms latency, Zero API limit hit)
                    klines_1m = self.storage.get_klines(raw_sym, '1m')
                    klines_15m = self.storage.get_klines(raw_sym, '15m')
                    sentiment_data = self.storage.get_sentiment(raw_sym)
                        
                    s1 = self.e1.process(ob, ticks, symbol=raw_sym)
                    s2 = self.e2.process(ticks, symbol=raw_sym)
                    s3 = self.e3.process(klines_1m)
                    s4 = self.e4.process(sentiment_data)
                    s5 = self.e5.process(klines_15m)
                    
                    signals = {"e1": s1, "e2": s2, "e3": s3, "e4": s4}
                    dec = self.decision.evaluate(signals, s5)
                    
                    current_time = datetime.datetime.now().strftime('%H:%M:%S')
                    price = s1.get("micro_price", 0)
                    
                    if dec["action"] == "NO_TRADE":
                        reason = "Wait"
                        if not ticks: reason = "No Ticks"
                        elif not ob.get("bids"): reason = "No Orderbook"
                        elif abs(dec.get("final_score", 0)) < 0.45: reason = f"Low Score ({dec.get('final_score',0):.2f})"
                        
                        regime_info = f"{s5.get('regime', 'UNK')}|{s5.get('vol_phase', 'UNK')}"
                        sent_info = f"{s4.get('direction', 'UNK')}"
                        
                        print(f"[{current_time}] {raw_sym} | P: {price:.2f} | RGM: {regime_info} | SNT: {sent_info} | SKIP: {reason}")
                    else:
                        regime_info = f"{s5.get('regime', 'UNK')}|{s5.get('vol_phase', 'UNK')}"
                        print(f"[{current_time}] {raw_sym} | P: {price:.2f} | RGM: {regime_info} | Action: {dec['action']} | Strat: {dec['strategy']} | Score: {dec['final_score']:.2f} | Conf: {dec['confidence']:.1f}%")
                        
                        if price > 0:
                            risk_params = self.risk.calculate(dec, price, s3.get('atr', 0), s5.get('param_overrides', {}))
                            
                            # Catch Fee/Spread Rejections from RiskManager
                            if risk_params is not None and risk_params.get("action") == "NO_TRADE":
                                print(f"[{current_time}] {raw_sym} | P: {price:.2f} | RGM: {regime_info} | SNT: {s4.get('direction', 'UNK')} | SKIP: {risk_params.get('reason')}")
                                continue
                                
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
            loop_tasks.append(asyncio.create_task(self.watch_klines_for_symbol(sym, '15m')))
            loop_tasks.append(asyncio.create_task(self.poll_sentiment_data(sym)))
        
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
