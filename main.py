import asyncio
from binance import AsyncClient, BinanceSocketManager
from config import API_KEY, SECRET_KEY, TESTNET, TRADING_PAIRS
from storage import DataStorage
from engines import Engine1OrderFlow, Engine2Tick, Engine3Technical, Engine4Sentiment, Engine5Regime
from core import DecisionEngine, RiskManager, Executor

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
        self.executor = Executor()
        
    async def process_message(self, msg):
        if not msg: return
        try:
            stream = msg.get('stream', '')
            data = msg.get('data', {})
            
            if '@depth' in stream:
                symbol = data.get('s', '').upper()
                self.storage.set_orderbook(symbol, data.get('b', []), data.get('a', []))
            elif '@aggTrade' in stream:
                symbol = data.get('s', '').upper()
                self.storage.add_tick(symbol, data)
        except Exception as e:
            print(f"WS Error: {e}")

    async def trade_loop(self):
        print("Trading loop started...")
        while True:
            for symbol in TRADING_PAIRS:
                ob = self.storage.get_orderbook(symbol)
                ticks = self.storage.get_ticks(symbol)
                klines = [] # Klines via WS logic in real app
                
                s1 = self.e1.process(ob, ticks)
                s2 = self.e2.process(ticks)
                s3 = self.e3.process(klines)
                s4 = self.e4.process({})
                s5 = self.e5.process(klines)
                
                signals = {"e1": s1, "e2": s2, "e3": s3, "e4": s4}
                dec = self.decision.evaluate(signals, s5)
                
                if dec["action"] != "NO_TRADE":
                    current_price = s1.get("micro_price", 0)
                    if current_price > 0:
                        risk_params = self.risk.calculate(dec, current_price, s3.get('atr', 0), s5.get('param_overrides', {}))
                        order = self.executor.execute_trade(symbol, dec, risk_params, current_price)
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
            
            await asyncio.sleep(1)

    async def run(self):
        print("Starting VORTEX-7 Engine...")
        self.client = await AsyncClient.create(API_KEY, SECRET_KEY, testnet=TESTNET)
        self.bm = BinanceSocketManager(self.client)
        
        streams = []
        for pair in TRADING_PAIRS:
            s_lower = pair.lower()
            streams.extend([f"{s_lower}@aggTrade", f"{s_lower}@depth20@100ms"])
            
        print(f"Connecting to streams: {streams}")
        self.ts = self.bm.multiplex_socket(streams)
        
        asyncio.create_task(self.trade_loop())
        
        async with self.ts as tscm:
            print("Listening for marketplace data...")
            while True:
                msg = await tscm.recv()
                await self.process_message(msg)

if __name__ == "__main__":
    bot = VortexBot()
    asyncio.run(bot.run())
