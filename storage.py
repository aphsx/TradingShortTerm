import redis
import json
import asyncio
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

    def set_sentiment(self, symbol, data):
        self.r.hset(f"sentiment:{symbol}", mapping=data)
        
    def get_sentiment(self, symbol):
        data = self.r.hgetall(f"sentiment:{symbol}")
        # Convert strings back to floats
        return {k: float(v) for k, v in data.items()} if data else {}

    # --- Supabase Cold Data ---
    async def save_trade(self, trade_data):
        """Save executed trade to database (Non-blocking)"""
        if self.supabase:
            try:
                # Run blocking Supabase call in a separate thread to avoid blocking the event loop
                await asyncio.to_thread(self.supabase.table("trades").insert(trade_data).execute)
            except Exception as e:
                print(f"Error saving trade to Supabase: {e}")

    async def save_signal_snapshot(self, signal_data):
        """
        Save complete signal snapshot (including NO_TRADE decisions) (Non-blocking)
        """
        if self.supabase:
            try:
                await asyncio.to_thread(self.supabase.table("signals_snapshots").insert(signal_data).execute)
            except Exception as e:
                print(f"Error saving signal snapshot to Supabase: {e}")

    async def save_rejected_signal(self, rejection_data):
        """
        Save rejected signal with reason (Non-blocking)
        """
        if self.supabase:
            try:
                await asyncio.to_thread(self.supabase.table("rejected_signals").insert(rejection_data).execute)
            except Exception as e:
                print(f"Error saving rejected signal to Supabase: {e}")

    async def save_trade_outcome(self, outcome_data):
        """
        Save trade result/PnL (Non-blocking)
        """
        if self.supabase:
            try:
                await asyncio.to_thread(self.supabase.table("trade_outcomes").insert(outcome_data).execute)
            except Exception as e:
                print(f"Error saving trade outcome to Supabase: {e}")

    def update_performance_metrics(self, period_type="HOURLY"):
        """
        Calculate and store aggregated performance metrics

        Should be called periodically (e.g., every hour)
        """
        if not self.supabase:
            return

        try:
            # This would typically be a stored procedure or complex query
            # For now, just a placeholder for the concept
            pass
        except Exception as e:
            print(f"Error updating performance metrics: {e}")
