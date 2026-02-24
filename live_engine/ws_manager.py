"""
ws_manager.py — Binance Futures WebSocket Manager (The Observer).
Handles Market Data (aggTrade, bookTicker) + User Data Stream
with reconnection, sequence tracking, and listenKey renewal.
"""

import time
import asyncio
import logging

import aiohttp
import orjson

logger = logging.getLogger(__name__)


class BinanceWSManager:
    """
    Manages dual WebSocket connections:
    1. Market Data: aggTrade + bookTicker (combined stream)
    2. User Data:   ORDER_TRADE_UPDATE + ACCOUNT_UPDATE
    """

    def __init__(self, config, event_queue: asyncio.Queue):
        self.cfg = config
        self.event_queue = event_queue
        self._last_agg_trade_id: dict[str, int] = {}
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._listen_key: str = ""
        self._running = True

    async def stop(self):
        self._running = False

    # ─────────────────────────────────────────────────────────────
    # Market Data Stream
    # ─────────────────────────────────────────────────────────────

    async def run_market_stream(self):
        """Connect to combined market data stream with auto-reconnect."""
        streams = []
        for s in self.cfg.trading_pairs:
            sl = s.lower()
            streams.extend([f"{sl}@aggTrade", f"{sl}@bookTicker"])

        url = f"{self.cfg.ws_base}/stream?streams={'/'.join(streams)}"

        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    logger.info(f"[WS] Connecting market stream: {url[:80]}...")
                    async with session.ws_connect(
                        url, heartbeat=15, max_msg_size=0
                    ) as ws:
                        self._reconnect_delay = 1.0
                        logger.info("[WS] Market stream connected")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_market_msg(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                              aiohttp.WSMsgType.ERROR):
                                logger.warning(f"[WS] Market stream: {msg.type}")
                                break
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"[WS] Market stream error: {e}")

            if self._running:
                logger.info(f"[WS] Reconnecting in {self._reconnect_delay:.0f}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    async def _handle_market_msg(self, raw: str):
        ts_recv = time.monotonic_ns()
        data = orjson.loads(raw)
        stream = data.get("stream", "")
        payload = data.get("data", {})

        if "aggTrade" in stream:
            symbol = payload["s"]
            trade_id = payload["a"]

            # Sequence gap detection
            last = self._last_agg_trade_id.get(symbol, trade_id - 1)
            if trade_id > last + 1:
                gap = trade_id - last - 1
                logger.warning(f"[WS] {symbol} aggTrade gap: {gap} trades missed")
            self._last_agg_trade_id[symbol] = trade_id

            await self.event_queue.put({
                "type": "agg_trade",
                "symbol": symbol,
                "price": float(payload["p"]),
                "qty": float(payload["q"]),
                "is_buyer_maker": payload["m"],
                "trade_id": trade_id,
                "event_time": payload["E"],
                "ts_recv": ts_recv,
            })

        elif "bookTicker" in stream:
            await self.event_queue.put({
                "type": "book_ticker",
                "symbol": payload["s"],
                "bid": float(payload["b"]),
                "bid_qty": float(payload["B"]),
                "ask": float(payload["a"]),
                "ask_qty": float(payload["A"]),
                "ts_recv": ts_recv,
            })

    # ─────────────────────────────────────────────────────────────
    # User Data Stream
    # ─────────────────────────────────────────────────────────────

    async def run_user_stream(self):
        """Connect to user data stream with listenKey auto-renewal."""
        while self._running:
            try:
                self._listen_key = await self._get_listen_key()
                if not self._listen_key:
                    logger.error("[WS] Failed to get listenKey")
                    await asyncio.sleep(5)
                    continue

                # Start renewal task
                renew_task = asyncio.create_task(self._renew_listen_key_loop())

                url = f"{self.cfg.ws_base}/ws/{self._listen_key}"
                async with aiohttp.ClientSession() as session:
                    logger.info("[WS] Connecting user data stream...")
                    async with session.ws_connect(
                        url, heartbeat=15, max_msg_size=0
                    ) as ws:
                        logger.info("[WS] User data stream connected")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_user_msg(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                              aiohttp.WSMsgType.ERROR):
                                break
                renew_task.cancel()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"[WS] User stream error: {e}")

            if self._running:
                await asyncio.sleep(2)

    async def _handle_user_msg(self, raw: str):
        data = orjson.loads(raw)
        event_type = data.get("e")

        if event_type == "ORDER_TRADE_UPDATE":
            await self.event_queue.put({
                "type": "order_update",
                "data": data["o"],
            })
        elif event_type == "ACCOUNT_UPDATE":
            await self.event_queue.put({
                "type": "account_update",
                "data": data["a"],
            })
        elif event_type == "listenKeyExpired":
            logger.warning("[WS] listenKey expired, reconnecting...")

    async def _get_listen_key(self) -> str:
        headers = {"X-MBX-APIKEY": self.cfg.binance_api_key}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self.cfg.rest_base}/fapi/v1/listenKey",
                    headers=headers,
                ) as r:
                    resp = await r.json()
                    return resp.get("listenKey", "")
        except Exception as e:
            logger.error(f"[WS] listenKey error: {e}")
            return ""

    async def _renew_listen_key_loop(self):
        """Renew listenKey every 30 minutes (expires after 60 min)."""
        headers = {"X-MBX-APIKEY": self.cfg.binance_api_key}
        while self._running:
            await asyncio.sleep(30 * 60)
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.put(
                        f"{self.cfg.rest_base}/fapi/v1/listenKey",
                        headers=headers,
                    ) as r:
                        if r.status == 200:
                            logger.info("[WS] listenKey renewed")
                        else:
                            logger.warning(f"[WS] listenKey renew failed: {r.status}")
            except Exception as e:
                logger.error(f"[WS] listenKey renew error: {e}")
