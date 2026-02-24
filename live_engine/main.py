"""
main.py — Asyncio entrypoint for the live Directional Scalping system.
Orchestrates all subsystems: WS → SignalEngine → OMS → Risk → Execution.
"""

import asyncio
import logging
import signal
import time
import uuid

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass  # Windows: use default asyncio

from .config import TradingConfig
from .ws_manager import BinanceWSManager
from .signal_engine import SignalEngine, VolumeBarAggregator, MarketRegime
from .oms import OrderMonitor, ManagedOrder, RateLimitManager
from .risk import CircuitBreaker, dynamic_position_size

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


class LiveTradingSystem:
    """Main orchestrator — wires all subsystems together."""

    def __init__(self, config: TradingConfig):
        self.cfg = config
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
        self.shutdown_event = asyncio.Event()

        # Subsystems
        self.ws_manager = BinanceWSManager(config, self.event_queue)
        self.signal_engines: dict[str, SignalEngine] = {}
        self.bar_aggregators: dict[str, VolumeBarAggregator] = {}
        self.oms = OrderMonitor()
        self.rate_limiter = RateLimitManager(
            max_weight=config.api_weight_limit,
            window_sec=config.api_weight_window_sec,
        )
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss_pct=config.max_daily_loss_pct,
            max_drawdown_pct=config.max_drawdown_pct,
            max_consecutive_losses=config.max_consecutive_losses,
            max_daily_trades=config.max_daily_trades,
            max_latency_ms=config.max_latency_ms,
        )

        # Per-symbol setup
        for symbol in config.trading_pairs:
            self.signal_engines[symbol] = SignalEngine(config)
            self.bar_aggregators[symbol] = VolumeBarAggregator(
                threshold_usd=config.volume_bar_threshold_usd
            )

        # Cooldown tracking per symbol
        self._last_trade_ts: dict[str, float] = {}
        self._balance: float = 0.0

    async def run(self):
        """Main entry point — starts all tasks."""
        logger.info("=" * 60)
        logger.info("  Directional Scalping System — LIVE")
        logger.info(f"  Pairs: {self.cfg.trading_pairs}")
        logger.info(f"  Testnet: {self.cfg.binance_use_testnet}")
        logger.info("=" * 60)

        tasks = [
            asyncio.create_task(
                self.ws_manager.run_market_stream(), name="market_ws"
            ),
            asyncio.create_task(
                self.ws_manager.run_user_stream(), name="user_ws"
            ),
            asyncio.create_task(
                self._event_dispatcher(), name="dispatcher"
            ),
            asyncio.create_task(
                self._orphan_checker(), name="orphan_check"
            ),
            asyncio.create_task(
                self._daily_reset_scheduler(), name="daily_reset"
            ),
        ]

        # Graceful shutdown on SIGINT/SIGTERM
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.shutdown_event.set)
            except NotImplementedError:
                pass  # Windows doesn't support add_signal_handler

        logger.info("All tasks started. Waiting for shutdown signal...")
        await self.shutdown_event.wait()

        logger.info("Shutting down...")
        await self.ws_manager.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Shutdown complete.")

    # ─────────────────────────────────────────────────────────────
    # Event Dispatcher (single consumer for all events)
    # ─────────────────────────────────────────────────────────────

    async def _event_dispatcher(self):
        """Main event loop — processes all events from the queue."""
        while not self.shutdown_event.is_set():
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            etype = event.get("type")

            if etype == "agg_trade":
                await self._on_agg_trade(event)
            elif etype == "book_ticker":
                self._on_book_ticker(event)
            elif etype == "order_update":
                self.oms.on_user_data_update(event["data"])
            elif etype == "account_update":
                self._on_account_update(event["data"])

    async def _on_agg_trade(self, event: dict):
        symbol = event["symbol"]
        agg = self.bar_aggregators.get(symbol)
        engine = self.signal_engines.get(symbol)
        if not agg or not engine:
            return

        # Aggregate into volume bar
        bar = agg.on_trade(
            price=event["price"],
            qty=event["qty"],
            is_buyer_maker=event["is_buyer_maker"],
            ts=event["event_time"],
        )
        if bar is None:
            return  # Bar not yet complete

        # Process completed volume bar through signal engine
        sig = engine.on_volume_bar(bar)
        if sig is None:
            return

        # Circuit breaker check
        can_trade, reason = self.circuit_breaker.check()
        if not can_trade:
            logger.warning(f"[CB] Blocked signal {sig.type.name}: {reason}")
            return

        # Cooldown check
        last_ts = self._last_trade_ts.get(symbol, 0)
        if time.monotonic() - last_ts < self.cfg.cooldown_bars * 0.5:
            return  # Still in cooldown

        # Position sizing
        qty = dynamic_position_size(
            balance=self._balance,
            atr=sig.atr,
            price=bar.close,
            risk_pct=self.cfg.risk_per_trade_pct,
            sl_atr_mult=self.cfg.atr_sl_multiplier,
            max_position_pct=self.cfg.max_position_pct,
            leverage=self.cfg.leverage,
        )
        if sig.regime == MarketRegime.VOLATILE:
            qty *= 0.5  # Reduce size in volatile regime

        if qty <= 0.001:  # Binance BTC minimum
            return

        # Submit order via OMS
        order = ManagedOrder(
            client_order_id=f"DS-{uuid.uuid4().hex[:12]}",
            symbol=symbol,
            side=sig.side,
            order_type="MARKET",
            quantity=round(qty, 3),
            tags={
                "signal": sig.type.name,
                "atr": sig.atr,
                "confidence": sig.confidence,
            },
        )
        self.oms.on_order_submitted(order)
        self._last_trade_ts[symbol] = time.monotonic()

        logger.info(
            f"[SIGNAL] {sig.type.name} {sig.side} {symbol} "
            f"qty={qty:.3f} atr={sig.atr:.2f} "
            f"regime={sig.regime.name} conf={sig.confidence:.2f}"
        )
        # TODO: Execute via REST client (aiohttp POST to Binance)

    def _on_book_ticker(self, event: dict):
        symbol = event["symbol"]
        engine = self.signal_engines.get(symbol)
        if engine:
            engine.update_obi(event["bid_qty"], event["ask_qty"])

    def _on_account_update(self, data: dict):
        for balance in data.get("B", []):
            if balance.get("a") == "USDT":
                self._balance = float(balance.get("wb", 0))
                self.circuit_breaker.update_balance(self._balance)
                logger.debug(f"[ACCOUNT] Balance: {self._balance:.2f} USDT")

    # ─────────────────────────────────────────────────────────────
    # Background Tasks
    # ─────────────────────────────────────────────────────────────

    async def _orphan_checker(self):
        """Periodically check for orphaned orders."""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(10)
            await self.oms.check_orphans(rest_client=None)  # TODO: pass REST client
            self.oms.cleanup_terminal()

    async def _daily_reset_scheduler(self):
        """Reset CircuitBreaker counters at 00:00 UTC every day."""
        import datetime
        while not self.shutdown_event.is_set():
            now = datetime.datetime.now(datetime.timezone.utc)
            # คำนวณเวลาที่เหลือจนถึง 00:00 UTC วันถัดไป
            tomorrow = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=5, microsecond=0
            )
            wait_secs = (tomorrow - now).total_seconds()
            logger.info(f"[DAILY RESET] Next reset in {wait_secs/3600:.1f}h (at {tomorrow.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(), timeout=wait_secs
                )
            except asyncio.TimeoutError:
                pass  # ครบเวลา → reset

            if not self.shutdown_event.is_set():
                self.circuit_breaker.reset_daily()
                logger.info("[DAILY RESET] CircuitBreaker daily counters reset (00:00 UTC)")


def main():
    config = TradingConfig()
    system = LiveTradingSystem(config)
    asyncio.run(system.run())


if __name__ == "__main__":
    main()
