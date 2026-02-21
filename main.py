import asyncio
from binance import AsyncClient, BinanceSocketManager
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
        self.executor = Executor(testnet=TESTNET)
        
    async def process_message(self, msg):
        if not msg: return
        try:
            stream = msg.get('stream', '')
            data = msg.get('data', {})
            
            if '@depth' in stream:
                symbol = data.get('s', stream.split('@')[0]).upper()
                self.storage.set_orderbook(symbol, data.get('b', []), data.get('a', []))
            elif '@aggTrade' in stream:
                symbol = data.get('s', stream.split('@')[0]).upper()
                self.storage.add_tick(symbol, data)
        except Exception as e:
            pass

    async def trade_loop(self):
        print("Trading loop started...")
        while True:
            try:
                for symbol in TRADING_PAIRS:
                    ob = self.storage.get_orderbook(symbol)
                    ticks = self.storage.get_ticks(symbol)
                    # Fetch recent Klines (1m candles) for Engine 3
                    try:
                        kline_data = await self.client.futures_klines(symbol=symbol, interval='1m', limit=30)
                        klines = kline_data
                    except Exception as e:
                        klines = []
                    
                    s1 = self.e1.process(ob, ticks)
                    s2 = self.e2.process(ticks)
                    s3 = self.e3.process(klines)
                    s4 = self.e4.process({})
                    s5 = self.e5.process(klines)
                    
                    signals = {"e1": s1, "e2": s2, "e3": s3, "e4": s4}
                    dec = self.decision.evaluate(signals, s5)
                    
                    # --- LOGGING ---
                    current_time = datetime.datetime.now().strftime('%H:%M:%S')
                    price = s1.get("micro_price", 0)
                    
                    if dec["action"] == "NO_TRADE":
                        # ตรวจสอบสาเหตุ
                        reason = "Wait"
                        if not ticks: reason = "No Ticks"
                        elif not ob.get("bids"): reason = "No Orderbook"
                        elif abs(dec.get("final_score", 0)) < 0.55: reason = f"Low Score ({dec.get('final_score',0):.2f})"
                        
                        print(f"[{current_time}] {symbol} | P: {price:.2f} | Action: SKIP | R: {reason}")
                    else:
                        print(f"[{current_time}] {symbol} | P: {price:.2f} | Action: {dec['action']} | Strat: {dec['strategy']} | Score: {dec['final_score']:.2f} | Conf: {dec['confidence']:.1f}%")
                        
                        if price > 0:
                            risk_params = self.risk.calculate(dec, price, s3.get('atr', 0), s5.get('param_overrides', {}))
                            order = await self.executor.execute_trade(symbol, dec, risk_params, price)
                            if order:
                                self.storage.set_position(symbol, order)
                                # Save to Supabase
                                self.storage.save_trade({
                                    "symbol": order["symbol"],
                                    "side": order["side"],
                                    "strategy": order["strategy"],
                                    "size_usdt": order["quantity"] * order["price"],
                                    "entry_price": order["price"],
                                    "sl_price": order["sl_price"],
                                    "tp1_price": order["tp_price"],
                                    "leverage": risk_params["leverage"]
                                })
            except Exception as e:
                print(f"Trade Loop Error: {e}")
                traceback.print_exc()
            
            await asyncio.sleep(2)  # Check every 2 seconds

    async def run(self):
        print(f"Starting VORTEX-7 Engine... (TESTNET: {TESTNET})")
        # ดึงข้อมูลและส่งออร์เดอร์ตามสถานะ TESTNET
        self.client = await AsyncClient.create(API_KEY, SECRET_KEY, testnet=TESTNET)
        self.executor.client = self.client
        self.bm = BinanceSocketManager(self.client)
        
        streams = []
        for pair in TRADING_PAIRS:
            s_lower = pair.lower()
            streams.extend([f"{s_lower}@aggTrade", f"{s_lower}@depth20@100ms"])
            
        print(f"Connecting to streams: {streams}")
        self.ts = self.bm.futures_multiplex_socket(streams)
        
        asyncio.create_task(self.trade_loop())
        
        async with self.ts as tscm:
            print("Listening for marketplace data...")
            while True:
                try:
                    msg = await tscm.recv()
                    await self.process_message(msg)
                except Exception as e:
                    print(f"WS Recv Error: {e}")

if __name__ == "__main__":
    bot = VortexBot()
    asyncio.run(bot.run())
