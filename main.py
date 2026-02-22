import asyncio
import signal
import sys
import ccxt.pro as ccxtpro
from config import API_KEY, SECRET_KEY, TESTNET, TRADING_PAIRS, DB_LOG_INTERVAL
from storage import DataStorage
from engines import Engine1OrderFlow, Engine2Tick, Engine3Technical, Engine4Sentiment, Engine5Regime
from core import DecisionEngine, RiskManager, Executor
from logger_config import setup_logging, get_logger
import datetime
import time
import traceback

# Initialize logging
setup_logging(console_level="INFO")
logger = get_logger(__name__)


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

        # Track last database save time per symbol to reduce write frequency
        self.last_db_log = {}

        # Shutdown flag – set True by signal handler to gracefully stop all loops
        self._shutdown_event = asyncio.Event()

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

        # Websocket reconnection tracking
        self.ws_reconnect_delays = {}  # Track delays per symbol/type
        self.ws_max_reconnect_delay = 60  # Max 60 seconds between retries

        # All background tasks, stored so we can cancel them cleanly
        self._tasks: list[asyncio.Task] = []

    # ──────────────────────────────────────────────────────────────────────────
    # Graceful shutdown helpers
    # ──────────────────────────────────────────────────────────────────────────

    def register_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Register SIGINT / SIGTERM handlers that gracefully stop the bot.

        On Windows, only SIGINT (Ctrl-C) is available at the OS level;
        SIGTERM is handled via the asyncio fallback path below.
        """
        def _request_shutdown(signame: str) -> None:
            if not self._shutdown_event.is_set():
                logger.warning(f"🛑  Signal {signame} received – requesting graceful shutdown…")
                self._shutdown_event.set()

        try:
            # Unix / macOS: hook directly into the event loop
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _request_shutdown, sig.name)
            logger.info("Signal handlers registered (SIGINT, SIGTERM)")
        except NotImplementedError:
            # Windows: asyncio does not support add_signal_handler for most signals
            # Fall back to the standard library signal module which works for SIGINT
            import signal as _sig

            def _win_handler(signum, frame):  # type: ignore[type-arg]
                _request_shutdown("SIGINT/CTRL_C")

            _sig.signal(_sig.SIGINT, _win_handler)
            logger.info("Signal handlers registered (Windows Ctrl-C fallback)")

    async def _cancel_all_tasks(self) -> None:
        """Cancel every background task and wait for them to finish."""
        if not self._tasks:
            return

        logger.info(f"Cancelling {len(self._tasks)} background task(s)…")
        for task in self._tasks:
            if not task.done():
                task.cancel()

        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        for task, result in zip(self._tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.warning(f"Task {task.get_name()} raised during shutdown: {result}")

        logger.info("All tasks cancelled.")

    # ──────────────────────────────────────────────────────────────────────────
    # WebSocket reconnection helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _exponential_backoff_sleep(self, key: str) -> None:
        """Exponential backoff for websocket reconnections with circuit breaker."""
        if key not in self.ws_reconnect_delays:
            self.ws_reconnect_delays[key] = 1  # Start with 1 second
        else:
            self.ws_reconnect_delays[key] = min(
                self.ws_reconnect_delays[key] * 2,
                self.ws_max_reconnect_delay
            )

        delay = self.ws_reconnect_delays[key]
        logger.warning(f"WebSocket reconnecting in {delay}s (key: {key})")

        # Use wait_for so that a shutdown signal can interrupt the sleep
        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=delay
            )
        except asyncio.TimeoutError:
            pass  # Normal case – timeout elapsed, no shutdown yet

    def _reset_backoff(self, key: str) -> None:
        """Reset backoff delay on successful connection."""
        if key in self.ws_reconnect_delays:
            del self.ws_reconnect_delays[key]

    # ──────────────────────────────────────────────────────────────────────────
    # WebSocket streaming coroutines
    # ──────────────────────────────────────────────────────────────────────────

    async def watch_ob_for_symbol(self, symbol: str) -> None:
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        backoff_key = f"ob_{symbol}"
        consecutive_errors = 0
        max_consecutive_errors = 10  # Circuit breaker threshold

        while not self._shutdown_event.is_set():
            try:
                ob = await self.exchange.watch_order_book(symbol)
                # Parse to ensure values are string/float arrays matching Engine expectations
                bids = [[str(b[0]), str(b[1])] for b in ob.get('bids', [])[:20]]
                asks = [[str(a[0]), str(a[1])] for a in ob.get('asks', [])[:20]]
                self.storage.set_orderbook(raw_sym, bids, asks)

                # Reset on success
                self._reset_backoff(backoff_key)
                consecutive_errors = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"WS OB {symbol} Error ({consecutive_errors}/{max_consecutive_errors}): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"CIRCUIT BREAKER: Orderbook WS for {symbol} failed "
                        f"{max_consecutive_errors} times, stopping"
                    )
                    break

                await self._exponential_backoff_sleep(backoff_key)

    async def watch_tr_for_symbol(self, symbol: str) -> None:
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        backoff_key = f"tr_{symbol}"
        consecutive_errors = 0
        max_consecutive_errors = 10

        while not self._shutdown_event.is_set():
            try:
                trades = await self.exchange.watch_trades(symbol)
                for t in trades:
                    # Tick format: {'q': qty, 'm': isBuyerMaker (True if sell)}
                    tick_data = {'q': t.get('amount', 0), 'm': t.get('side', 'buy') == 'sell'}
                    self.storage.add_tick(raw_sym, tick_data)

                # Reset on success
                self._reset_backoff(backoff_key)
                consecutive_errors = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"WS TR {symbol} Error ({consecutive_errors}/{max_consecutive_errors}): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"CIRCUIT BREAKER: Trades WS for {symbol} failed "
                        f"{max_consecutive_errors} times, stopping"
                    )
                    break

                await self._exponential_backoff_sleep(backoff_key)

    async def watch_klines_for_symbol(self, symbol: str, timeframe: str = '1m') -> None:
        raw_sym = symbol.replace('/', '').replace(':USDT', '')
        backoff_key = f"kline_{symbol}_{timeframe}"
        consecutive_errors = 0
        max_consecutive_errors = 10

        # Pre-fetch historical candles to bootstrap indicator math
        try:
            hist = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=96)
            self.storage.set_klines(raw_sym, timeframe, hist)
        except Exception as e:
            logger.error(f"Prefetch Kline Error for {symbol}: {e}")

        while not self._shutdown_event.is_set():
            try:
                new_klines = await self.exchange.watch_ohlcv(symbol, timeframe)
                current_klines = self.storage.get_klines(raw_sym, timeframe)

                curr_dict = {k[0]: k for k in current_klines}
                for k in new_klines:
                    curr_dict[k[0]] = k

                merged = sorted(curr_dict.values(), key=lambda x: x[0])[-96:]
                self.storage.set_klines(raw_sym, timeframe, merged)

                # Reset on success
                self._reset_backoff(backoff_key)
                consecutive_errors = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"WS Kline {symbol} {timeframe} Error "
                    f"({consecutive_errors}/{max_consecutive_errors}): {e}"
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"CIRCUIT BREAKER: Kline WS for {symbol} {timeframe} failed "
                        f"{max_consecutive_errors} times, stopping"
                    )
                    break

                await self._exponential_backoff_sleep(backoff_key)

    async def poll_sentiment_data(self, symbol: str) -> None:
        """Polls REST endpoints every 30 seconds for Engine 4."""
        raw_sym = symbol.replace('/', '').replace(':USDT', '')

        while not self._shutdown_event.is_set():
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
                    ls_ratio_res = await self.exchange.fapiData_get_globallongshortaccountratio(
                        {'symbol': raw_sym, 'period': '5m', 'limit': 1}
                    )
                    ls_ratio = float(ls_ratio_res[0].get('longShortRatio', 1.0)) if ls_ratio_res else 1.0
                    long_pct = float(ls_ratio_res[0].get('longAccount', 0.5)) if ls_ratio_res else 0.5
                    short_pct = float(ls_ratio_res[0].get('shortAccount', 0.5)) if ls_ratio_res else 0.5

                    # 3. Fetch Top Trader Long/Short Ratio
                    top_ls_res = await self.exchange.fapiData_get_toplongshortaccountratio(
                        {'symbol': raw_sym, 'period': '5m', 'limit': 1}
                    )
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
                if symbol in ("ETH/USDT:USDT", "BTC/USDT:USDT"):
                    logger.debug(f"Successfully stored SNT for {symbol}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sentiment Poll Error for {symbol}: {e}")

            # Wait 30 seconds before next poll; interruptible by shutdown event
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass  # Normal – keep polling

    # ──────────────────────────────────────────────────────────────────────────
    # Core trading loop
    # ──────────────────────────────────────────────────────────────────────────

    async def trade_loop(self) -> None:
        logger.info("Trading loop started…")
        while not self._shutdown_event.is_set():
            try:
                for symbol in self.ccxt_symbols:
                    if self._shutdown_event.is_set():
                        break

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

                    # === SUPABASE LOGGING (STRICTLY ON TRADE ONLY) ===
                    # บันทึกข้อมูลลง Database เฉพาะเมื่อมีการตัดสินใจเทรด (LONG/SHORT) เท่านั้น
                    # เพื่อป้องกันการเซฟข้อมูลถี่เกินไป (เดิมเซฟทุก 150ms)
                    if dec["action"] == "NO_TRADE":
                        regime_info = f"{s5.get('regime', 'UNK')}|{s5.get('vol_phase', 'UNK')}"
                        sent_info = f"{s4.get('direction', 'UNK')}"
                        logger.info(
                            f"[{current_time}] {raw_sym} | P: {price:.2f} | "
                            f"RGM: {regime_info} | SNT: {sent_info} | SKIP: {dec.get('reason', 'Wait')}"
                        )
                    else:
                        regime_info = f"{s5.get('regime', 'UNK')}|{s5.get('vol_phase', 'UNK')}"
                        logger.info(
                            f"[{current_time}] {raw_sym} | P: {price:.2f} | RGM: {regime_info} | "
                            f"Action: {dec['action']} | Strat: {dec['strategy']} | "
                            f"Score: {dec['final_score']:.2f} | Conf: {dec['confidence']:.1f}%"
                        )

                        if price > 0:
                            risk_params = self.risk.calculate(
                                dec, price, s3.get('atr', 0), s5.get('param_overrides', {})
                            )

                            # Skip if RiskManager rejects (Fee/Spread/RR issues)
                            if risk_params is not None and risk_params.get("action") == "NO_TRADE":
                                logger.info(
                                    f"[{current_time}] {raw_sym} | P: {price:.2f} | "
                                    f"RGM: {regime_info} | SKIP: {risk_params.get('reason')}"
                                )
                                continue

                            # --- POSITION GUARD: Prevent duplicate trades ---
                            existing_position = self.storage.get_position(raw_sym)
                            if existing_position:
                                logger.info(
                                    f"SKIP: {raw_sym} already has open position: "
                                    f"{existing_position.get('side')} @ {existing_position.get('price')}"
                                )
                                continue

                            # --- ACTUAL TRADE ATTEMPT ---
                            # จุดนี้คือจุดที่ Bot "ตัดสินใจยิงจริง" จะบันทึกข้อมูลลง Database เฉพาะที่จุดนี้
                            order = await self.executor.execute_trade(raw_sym, dec, risk_params, price)

                            if order:
                                # 1. Save Signal Snapshot (เหตุผลที่ยิงไม้่นี้)
                                asyncio.create_task(self.storage.save_signal_snapshot({
                                    "symbol": raw_sym,
                                    "action": dec["action"],
                                    "reason": dec.get("reason", ""),
                                    "final_score": dec.get("final_score", 0),
                                    "confidence": dec.get("confidence", 0),
                                    "strategy": dec.get("strategy", ""),
                                    "current_price": price,
                                    "atr": s3.get("atr", 0),
                                    "e1_direction": s1.get("direction"),
                                    "e1_strength": s1.get("strength"),
                                    "e1_vpin": s1.get("vpin", 0),
                                    "e2_direction": s2.get("direction"),
                                    "e2_strength": s2.get("strength"),
                                    "e2_alignment": s2.get("alignment", 0),
                                    "e3_direction": s3.get("direction"),
                                    "e3_rsi": s3.get("rsi"),
                                    "e4_direction": s4.get("direction"),
                                    "e5_regime": s5.get("regime")
                                }))

                                # 2. Update Local Redis State (If success)
                                if order.get("status", "SUCCESS") == "SUCCESS":
                                    self.storage.set_position(raw_sym, order)

                                # 3. Save Trade Results (Success หรือ Error ก็จะเซฟลงตาราง trades)
                                asyncio.create_task(self.storage.save_trade({
                                    "symbol": order.get("symbol", raw_sym),
                                    "side": order.get("side", dec["action"]),
                                    "strategy": order.get("strategy", dec["strategy"]),
                                    "order_id": order.get("order_id"),
                                    "client_order_id": order.get("client_order_id"),
                                    "execution_type": order.get("execution_type"),
                                    "api_latency_ms": order.get("api_latency_ms"),
                                    "status": order.get("status"),       # SUCCESS หรือ API_ERROR
                                    "error_type": order.get("error_type"),
                                    "error_msg": order.get("error_msg"),
                                    "entry_price": order.get("price", 0),
                                    "size_usdt": order.get("quantity", 0) * order.get("price", 0),
                                    "leverage": risk_params.get("leverage", 1),
                                    "sl_price": order.get("sl_price", 0),
                                    "tp1_price": order.get("tp_price", 0),
                                    "confidence": dec.get("confidence", 0),
                                    "final_score": dec.get("final_score", 0)
                                }))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Trade Loop Error: {e}", exc_info=True)

            # === OPTIMIZED LOOP INTERVAL FOR SCALPING ===
            # Research shows optimal interval for scalping is 100-200ms
            # - Fast enough to catch momentum (signals update every 200ms)
            # - Slow enough to avoid hitting rate limits
            # Interruptible by the shutdown event so we stop promptly.
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=0.15)
            except asyncio.TimeoutError:
                pass  # Normal – keep looping

    # ──────────────────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        logger.info(f"Starting VORTEX-7 Engine via CCXT.PRO… (TESTNET: {TESTNET})")
        logger.info(f"Connecting to streams: {self.ccxt_symbols}")

        for sym in self.ccxt_symbols:
            self._tasks.append(asyncio.create_task(
                self.watch_ob_for_symbol(sym), name=f"ob_{sym}"
            ))
            self._tasks.append(asyncio.create_task(
                self.watch_tr_for_symbol(sym), name=f"tr_{sym}"
            ))
            self._tasks.append(asyncio.create_task(
                self.watch_klines_for_symbol(sym, '1m'), name=f"kline_1m_{sym}"
            ))
            self._tasks.append(asyncio.create_task(
                self.watch_klines_for_symbol(sym, '15m'), name=f"kline_15m_{sym}"
            ))
            self._tasks.append(asyncio.create_task(
                self.poll_sentiment_data(sym), name=f"snt_{sym}"
            ))

        self._tasks.append(asyncio.create_task(self.trade_loop(), name="trade_loop"))

        print("Listening for marketplace data… (press Ctrl-C to stop)")
        try:
            # Wait until the shutdown event is triggered by a signal
            await self._shutdown_event.wait()
        finally:
            logger.info("Shutdown sequence started…")
            await self._cancel_all_tasks()
            logger.info("Releasing CCXT sessions safely…")
            await self.exchange.close()
            logger.info("✅  Bot shut down cleanly.")


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

async def _main() -> None:
    bot = VortexBot()
    loop = asyncio.get_running_loop()
    bot.register_signal_handlers(loop)
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        # On Windows, KeyboardInterrupt may still bubble up before our handler
        # fires; catch it here so the terminal output stays clean.
        print("\n⛔  Bot stopped by user (KeyboardInterrupt). Goodbye!")
