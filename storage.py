import redis
import json
from supabase import create_client, Client
from config import REDIS_HOST, REDIS_PORT, SUPABASE_URL, SUPABASE_KEY

class DataStorage:
    def __init__(self):
        self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        if SUPABASE_URL and SUPABASE_KEY:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            self.supabase = None
            
    # --- Redis Hot Data ---
    def get_position(self, symbol):
        data = self.r.hgetall(f"position:{symbol}")
        return data if data else None
        
    def set_position(self, symbol, data):
        self.r.hset(f"position:{symbol}", mapping=data)
        
    def delete_position(self, symbol):
        self.r.delete(f"position:{symbol}")
        
    def add_tick(self, symbol, tick_data):
        key = f"ticks:{symbol}"
        self.r.lpush(key, json.dumps(tick_data))
        self.r.ltrim(key, 0, 1999)
        
    def get_ticks(self, symbol, count=100):
        ticks = self.r.lrange(f"ticks:{symbol}", 0, count-1)
        return [json.loads(t) for t in ticks]
        
    def set_orderbook(self, symbol, bids, asks):
        self.r.hset(f"orderbook:{symbol}", mapping={
            "bids": json.dumps(bids),
            "asks": json.dumps(asks)
        })
        
    def get_orderbook(self, symbol):
        ob = self.r.hgetall(f"orderbook:{symbol}")
        if not ob:
            return {"bids": [], "asks": []}
        return {
            "bids": json.loads(ob.get("bids", "[]")),
            "asks": json.loads(ob.get("asks", "[]"))
        }

    def set_signals(self, symbol, engine_name, data):
        self.r.hset(f"engine_signals:{symbol}", engine_name, json.dumps(data))
        
    def get_signals(self, symbol):
        signals = self.r.hgetall(f"engine_signals:{symbol}")
        return {k: json.loads(v) for k, v in signals.items()}

    def set_klines(self, symbol, timeframe, data):
        self.r.set(f"klines:{symbol}:{timeframe}", json.dumps(data))
        
    def get_klines(self, symbol, timeframe):
        v = self.r.get(f"klines:{symbol}:{timeframe}")
        return json.loads(v) if v else []

    # --- Supabase Cold Data ---
    def save_trade(self, trade_data):
        if self.supabase:
            try:
                self.supabase.table("trades").insert(trade_data).execute()
            except Exception as e:
                print(f"Error saving to Supabase: {e}")
