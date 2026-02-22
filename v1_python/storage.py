"""
Storage Layer — VORTEX-7 v2.0
================================
Hot  store : Redis  (orderbook, ticks, klines, positions, sentiment)
Cold store : Supabase (trade_logs, rejected_signals)

DB Write pattern (ALWAYS fire-and-forget in the caller):
    asyncio.create_task(storage.log_trade_open(data))
    asyncio.create_task(storage.log_trade_close(trade_id, data))
    asyncio.create_task(storage.log_rejected(data))
"""

import redis
import json
import asyncio
import logging
from typing import Optional, Dict, Any

from supabase import create_client, Client
from config import REDIS_HOST, REDIS_PORT, SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


class DataStorage:
    """Single entry point for all storage operations."""

    # ──────────────────────────────────────────────────────────────────────────
    # Init
    # ──────────────────────────────────────────────────────────────────────────

    def __init__(self):
        # ── Redis ─────────────────────────────────────────────────────────────
        try:
            self.r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self.r.ping()
            logger.info(f"✓ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
        except redis.ConnectionError as e:
            logger.error(f"✗ Redis connection failed: {e}")
            raise ConnectionError(f"Cannot connect to Redis at {REDIS_HOST}:{REDIS_PORT}") from e

        # ── Supabase ──────────────────────────────────────────────────────────
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                self.supabase: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY)
                # Lightweight ping — just verify the table exists
                self.supabase.table("trade_logs").select("id").limit(1).execute()
                logger.info(f"✓ Supabase connected: {SUPABASE_URL}")
            except Exception as e:
                logger.error(f"✗ Supabase connection failed: {e}")
                raise ConnectionError(f"Cannot connect to Supabase: {e}") from e
        else:
            self.supabase = None
            logger.warning("⚠  Supabase not configured — no trades will be persisted!")

        self._consecutive_failures = 0
        self._MAX_FAILURES = 5

    # ──────────────────────────────────────────────────────────────────────────
    # Redis Hot Store
    # ──────────────────────────────────────────────────────────────────────────

    def get_position(self, symbol: str) -> Optional[Dict]:
        data = self.r.hgetall(f"position:{symbol}")
        return data if data else None

    def set_position(self, symbol: str, data: Dict) -> None:
        self.r.hset(f"position:{symbol}", mapping=data)

    def delete_position(self, symbol: str) -> None:
        self.r.delete(f"position:{symbol}")

    # ── Ticks (ring buffer, last 2 000 trades) ────────────────────────────────
    def add_tick(self, symbol: str, tick_data: Dict) -> None:
        key = f"ticks:{symbol}"
        self.r.lpush(key, json.dumps(tick_data))
        self.r.ltrim(key, 0, 1999)

    def get_ticks(self, symbol: str, count: int = 100):
        ticks = self.r.lrange(f"ticks:{symbol}", 0, count - 1)
        return [json.loads(t) for t in ticks]

    # ── Orderbook ─────────────────────────────────────────────────────────────
    def set_orderbook(self, symbol: str, bids, asks) -> None:
        self.r.hset(
            f"orderbook:{symbol}",
            mapping={"bids": json.dumps(bids), "asks": json.dumps(asks)},
        )

    def get_orderbook(self, symbol: str) -> Dict:
        ob = self.r.hgetall(f"orderbook:{symbol}")
        if not ob:
            return {"bids": [], "asks": []}
        return {
            "bids": json.loads(ob.get("bids", "[]")),
            "asks": json.loads(ob.get("asks", "[]")),
        }

    # ── Engine Signals ────────────────────────────────────────────────────────
    def set_signals(self, symbol: str, engine_name: str, data: Dict) -> None:
        self.r.hset(f"engine_signals:{symbol}", engine_name, json.dumps(data))

    def get_signals(self, symbol: str) -> Dict:
        signals = self.r.hgetall(f"engine_signals:{symbol}")
        return {k: json.loads(v) for k, v in signals.items()}

    # ── Klines ────────────────────────────────────────────────────────────────
    def set_klines(self, symbol: str, timeframe: str, data) -> None:
        self.r.set(f"klines:{symbol}:{timeframe}", json.dumps(data))

    def get_klines(self, symbol: str, timeframe: str):
        v = self.r.get(f"klines:{symbol}:{timeframe}")
        return json.loads(v) if v else []

    # ── Sentiment ─────────────────────────────────────────────────────────────
    def set_sentiment(self, symbol: str, data: Dict) -> None:
        self.r.hset(f"sentiment:{symbol}", mapping=data)

    def get_sentiment(self, symbol: str) -> Dict:
        data = self.r.hgetall(f"sentiment:{symbol}")
        return {k: float(v) for k, v in data.items()} if data else {}

    # ──────────────────────────────────────────────────────────────────────────
    # Supabase Cold Store  (fire-and-forget — call via asyncio.create_task)
    # ──────────────────────────────────────────────────────────────────────────

    async def _sb_insert(self, table: str, payload: Dict[str, Any]) -> Optional[str]:
        """
        Insert one row into `table`.
        Returns the generated UUID string on success, None on failure.
        All exceptions are caught so the caller loop never dies.
        """
        if not self.supabase:
            return None
        try:
            result = await asyncio.to_thread(
                self.supabase.table(table).insert(payload).execute
            )
            self._consecutive_failures = 0
            # Supabase client returns data list; grab first row id
            rows = getattr(result, "data", []) or []
            return rows[0].get("id") if rows else None
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"⚠  Supabase INSERT [{table}] failed: {e}")
            if self._consecutive_failures >= self._MAX_FAILURES:
                logger.critical(
                    f"🔥 {self._consecutive_failures} consecutive Supabase failures! "
                    "Check network / credentials."
                )
                self._consecutive_failures = 0
            return None

    async def _sb_update(self, table: str, row_id: str, payload: Dict[str, Any]) -> bool:
        """
        Update a single row identified by `row_id` (UUID).
        Returns True on success, False on failure.
        """
        if not self.supabase or not row_id:
            return False
        try:
            await asyncio.to_thread(
                self.supabase.table(table).update(payload).eq("id", row_id).execute
            )
            self._consecutive_failures = 0
            return True
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"⚠  Supabase UPDATE [{table}] id={row_id} failed: {e}")
            return False

    # ── Public API ────────────────────────────────────────────────────────────

    async def log_trade_open(self, data: Dict[str, Any]) -> Optional[str]:
        """
        INSERT a new OPEN row into trade_logs when an order is filled.

        Expected keys in `data`:
            symbol, side, status="OPEN",
            order_id, strategy, execution_type, api_latency_ms,
            entry_price, quantity, leverage, margin_used,
            sl_price, tp_price, open_fee_usdt,
            confidence, final_score, e1_direction, e5_regime

        Returns the newly created UUID (store in Redis so log_trade_close can use it).
        """
        payload = {**data, "status": "OPEN"}
        trade_id = await self._sb_insert("trade_logs", payload)
        if trade_id:
            logger.info(
                f"✓ trade_logs INSERT [{payload.get('symbol')} {payload.get('side')}] "
                f"id={trade_id}"
            )
        return trade_id

    async def log_trade_close(self, trade_id: str, data: Dict[str, Any]) -> None:
        """
        UPDATE the existing OPEN row with exit + PnL data.

        Expected keys in `data`:
            exit_price, closed_at, hold_time_s, close_reason,
            close_fee_usdt,
            pnl_gross_usdt, pnl_net_usdt, pnl_pct,
            status="CLOSED"
        """
        payload = {**data, "status": "CLOSED"}
        ok = await self._sb_update("trade_logs", trade_id, payload)
        if ok:
            logger.info(
                f"✓ trade_logs UPDATE [CLOSED] id={trade_id} "
                f"pnl_net={data.get('pnl_net_usdt')} USDT "
                f"({data.get('pnl_pct', 0)*100:.3f}%)"
            )

    async def log_trade_failed(self, trade_id: str, error_msg: str) -> None:
        """Mark a trade row as FAILED with an error message."""
        await self._sb_update(
            "trade_logs",
            trade_id,
            {"status": "FAILED", "error_msg": error_msg},
        )

    async def log_rejected(self, data: Dict[str, Any]) -> None:
        """
        INSERT into rejected_signals when RiskManager rejects an order.

        Expected keys in `data`:
            symbol, action, strategy, confidence,
            rejection_reason, current_price, daily_pnl
        """
        await self._sb_insert("rejected_signals", data)
        logger.debug(
            f"✓ rejected_signals INSERT [{data.get('symbol')}] "
            f"reason={data.get('rejection_reason')}"
        )
