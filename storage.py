import redis
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from supabase import create_client, Client
from config import REDIS_HOST, REDIS_PORT, SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

class DataStorage:
    def __init__(self):
        # Redis connection with validation
        try:
            self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=5)
            self.r.ping()  # Test connection
            logger.info(f"✓ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
        except redis.ConnectionError as e:
            logger.error(f"✗ Redis connection failed: {e}")
            raise ConnectionError(f"Cannot connect to Redis at {REDIS_HOST}:{REDIS_PORT}") from e

        # Supabase connection with validation
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
                # Test connection by querying a table
                self.supabase.table("trades").select("*").limit(1).execute()
                logger.info(f"✓ Supabase connected: {SUPABASE_URL}")
            except Exception as e:
                logger.error(f"✗ Supabase connection failed: {e}")
                raise ConnectionError(f"Cannot connect to Supabase at {SUPABASE_URL}") from e
        else:
            self.supabase = None
            logger.warning("⚠ Supabase not configured - no trade data will be saved!")

        # Alert counters for monitoring
        self.failed_saves = 0
        self.max_failed_saves_before_alert = 5
            
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

    async def _retry_with_backoff(self, func, *args, max_retries=3, **kwargs):
        """Retry async function with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

    async def _alert_database_failure(self, operation: str, error: str, data: Dict[str, Any]):
        """Alert on critical database failures"""
        self.failed_saves += 1
        logger.error(f"🚨 DATABASE FAILURE [{operation}]: {error}")
        logger.error(f"Failed data: {json.dumps(data, default=str)[:200]}...")

        if self.failed_saves >= self.max_failed_saves_before_alert:
            logger.critical(f"🔥 CRITICAL: {self.failed_saves} consecutive DB save failures!")
            # TODO: Send Telegram/email alert here
            self.failed_saves = 0  # Reset counter after alert

    # --- Supabase Cold Data ---
    async def save_trade(self, trade_data):
        """Save executed trade to database with retry logic (Non-blocking)"""
        if not self.supabase:
            logger.warning("⚠ Skipping save_trade - Supabase not configured")
            return

        try:
            # Run blocking Supabase call in a separate thread with retry
            await self._retry_with_backoff(
                lambda: asyncio.to_thread(self.supabase.table("trades").insert(trade_data).execute),
                max_retries=3
            )
            self.failed_saves = 0  # Reset on success
            logger.info(f"✓ Trade saved: {trade_data.get('symbol')} {trade_data.get('direction')}")
        except Exception as e:
            await self._alert_database_failure("save_trade", str(e), trade_data)

    async def save_signal_snapshot(self, signal_data):
        """
        Save complete signal snapshot (including NO_TRADE decisions) (Non-blocking)
        """
        if not self.supabase:
            return

        try:
            await self._retry_with_backoff(
                lambda: asyncio.to_thread(self.supabase.table("signals_snapshots").insert(signal_data).execute),
                max_retries=2  # Lower retries for signals (less critical than trades)
            )
        except Exception as e:
            logger.error(f"⚠ Failed to save signal snapshot: {e}")

    async def save_rejected_signal(self, rejection_data):
        """
        Save rejected signal with reason (Non-blocking)
        """
        if not self.supabase:
            return

        try:
            await self._retry_with_backoff(
                lambda: asyncio.to_thread(self.supabase.table("rejected_signals").insert(rejection_data).execute),
                max_retries=2
            )
        except Exception as e:
            logger.error(f"⚠ Failed to save rejected signal: {e}")

    async def save_trade_outcome(self, outcome_data):
        """
        Save trade result/PnL (Non-blocking)
        """
        if not self.supabase:
            return

        try:
            await self._retry_with_backoff(
                lambda: asyncio.to_thread(self.supabase.table("trade_outcomes").insert(outcome_data).execute),
                max_retries=3  # Critical data - more retries
            )
            logger.info(f"✓ Trade outcome saved: PnL={outcome_data.get('pnl')}")
        except Exception as e:
            await self._alert_database_failure("save_trade_outcome", str(e), outcome_data)

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
            logger.error(f"⚠ Error updating performance metrics: {e}")
