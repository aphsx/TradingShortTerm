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
    # Position Monitor — Trailing Stop, Breakeven, Auto-Close
    # ──────────────────────────────────────────────────────────────────────────

    async def position_monitor_loop(self) -> None:
        """
        Monitors open positions and manages them:
        1. Sync with exchange to get actual fill status
        2. Trailing stop: move SL up as price moves in our favor
        3. Breakeven: move SL to entry price when profitable enough
        4. Time-based exit: close stale positions after max hold time
        5. Record PnL for Kelly Criterion / drawdown tracking
        """
        logger.info("Position monitor started…")
        max_hold_seconds = 300  # Max 5 minutes for scalp positions

        while not self._shutdown_event.is_set():
            try:
                for symbol in self.ccxt_symbols:
                    if self._shutdown_event.is_set():
                        break

                    raw_sym = symbol.replace('/','').replace(':USDT','')
                    pos_data = self.storage.get_position(raw_sym)

                    if not pos_data:
                        continue

                    # Fetch current price from orderbook
                    ob = self.storage.get_orderbook(raw_sym)
                    bids = ob.get("bids", [])
                    asks = ob.get("asks", [])
                    if not bids or not asks:
                        continue

                    current_price = (float(bids[0][0]) + float(asks[0][0])) / 2

                    entry_price = float(pos_data.get('price', 0))
                    side = pos_data.get('side', '')
                    sl_price = float(pos_data.get('sl_price', 0))
                    tp_price = float(pos_data.get('tp_price', 0))
                    open_time = float(pos_data.get('open_time', time.time()))

                    if entry_price <= 0:
                        continue

                    # Calculate unrealized PnL
                    if side == 'LONG':
                        pnl_pct = (current_price - entry_price) / entry_price
                        tp_distance = tp_price - entry_price if tp_price > 0 else entry_price * 0.005
                        hit_sl = current_price <= sl_price if sl_price > 0 else False
                        hit_tp = current_price >= tp_price if tp_price > 0 else False
                    elif side == 'SHORT':
                        pnl_pct = (entry_price - current_price) / entry_price
                        tp_distance = entry_price - tp_price if tp_price > 0 else entry_price * 0.005
                        hit_sl = current_price >= sl_price if sl_price > 0 else False
                        hit_tp = current_price <= tp_price if tp_price > 0 else False
                    else:
                        continue

                    # === CHECK SL/TP HIT ===
                    if hit_sl or hit_tp:
                        reason = "TP_HIT" if hit_tp else "SL_HIT"
                        leverage   = float(pos_data.get('leverage', 10))
                        quantity   = float(pos_data.get('quantity', 0))
                        margin     = (entry_price * quantity) / max(leverage, 1)
                        pnl_gross  = pnl_pct * entry_price * quantity
                        open_fee   = float(pos_data.get('open_fee_usdt', 0))
                        # Estimate close fee: notional × 0.05% (taker)
                        close_fee  = current_price * quantity * 0.0005
                        pnl_net    = pnl_gross - open_fee - close_fee
                        pnl_pct_margin = (pnl_net / margin * 100) if margin > 0 else 0
                        hold_s     = int(time.time() - open_time)

                        logger.info(
                            f"📊 POSITION CLOSED [{reason}] {raw_sym} {side} | "
                            f"Entry: {entry_price:.2f} → Exit: {current_price:.2f} | "
                            f"Net PnL: {pnl_net:.4f} USDT ({pnl_pct_margin:.3f}%)"
                        )

                        # Record result for Kelly / drawdown tracking
                        self.risk.record_trade_result(pnl_net)

                        # ── DB write (fire-and-forget, never blocks loop) ─
                        trade_id = pos_data.get('trade_id', '')
                        asyncio.create_task(self.storage.log_trade_close(trade_id, {
                            "exit_price":     current_price,
                            "closed_at":      datetime.datetime.utcnow().isoformat(),
                            "hold_time_s":    hold_s,
                            "close_reason":   reason,
                            "close_fee_usdt": round(close_fee, 8),
                            "pnl_gross_usdt": round(pnl_gross, 8),
                            "pnl_net_usdt":   round(pnl_net, 8),
                            "pnl_pct":        round(pnl_pct_margin, 6),
                        }))

                        self.storage.delete_position(raw_sym)
                        continue

                    # === TRAILING STOP ===
                    # When profit > 50% of TP distance, trail SL behind price
                    if tp_distance > 0 and pnl_pct > 0:
                        profit_ratio = pnl_pct * entry_price / tp_distance

                        if profit_ratio >= 0.5:
                            # Trail SL at 40% of current profit
                            trail_distance = abs(current_price - entry_price) * 0.40
                            if side == 'LONG':
                                new_sl = current_price - trail_distance
                                if new_sl > sl_price:
                                    pos_data['sl_price'] = str(round(new_sl, 2))
                                    self.storage.set_position(raw_sym, pos_data)
                                    logger.info(f"📈 TRAIL SL {raw_sym}: {sl_price:.2f} → {new_sl:.2f}")
                            elif side == 'SHORT':
                                new_sl = current_price + trail_distance
                                if new_sl < sl_price or sl_price <= 0:
                                    pos_data['sl_price'] = str(round(new_sl, 2))
                                    self.storage.set_position(raw_sym, pos_data)
                                    logger.info(f"📈 TRAIL SL {raw_sym}: {sl_price:.2f} → {new_sl:.2f}")

                        # === BREAKEVEN ===
                        # Move SL to entry when profit > 30% of TP distance
                        elif profit_ratio >= 0.3:
                            if side == 'LONG' and sl_price < entry_price:
                                pos_data['sl_price'] = str(round(entry_price, 2))
                                self.storage.set_position(raw_sym, pos_data)
                                logger.info(f"🔒 BREAKEVEN {raw_sym}: SL moved to entry {entry_price:.2f}")
                            elif side == 'SHORT' and (sl_price > entry_price or sl_price <= 0):
                                pos_data['sl_price'] = str(round(entry_price, 2))
                                self.storage.set_position(raw_sym, pos_data)
                                logger.info(f"🔒 BREAKEVEN {raw_sym}: SL moved to entry {entry_price:.2f}")

                    # === TIME-BASED EXIT ===
                    # Close stale positions (scalps shouldn't be held > 5 min)
                    hold_time = time.time() - open_time
                    if hold_time > max_hold_seconds:
                        quantity   = float(pos_data.get('quantity', 0))
                        leverage   = float(pos_data.get('leverage', 10))
                        margin     = (entry_price * quantity) / max(leverage, 1)
                        pnl_gross  = pnl_pct * entry_price * quantity
                        open_fee   = float(pos_data.get('open_fee_usdt', 0))
                        close_fee  = current_price * quantity * 0.0005
                        pnl_net    = pnl_gross - open_fee - close_fee
                        pnl_pct_margin = (pnl_net / margin * 100) if margin > 0 else 0

                        logger.warning(
                            f"⏰ TIME EXIT {raw_sym}: Held {hold_time:.0f}s > {max_hold_seconds}s limit. "
                            f"Net PnL: {pnl_net:.4f} USDT ({pnl_pct_margin:.3f}%)"
                        )
                        self.risk.record_trade_result(pnl_net)

                        trade_id = pos_data.get('trade_id', '')
                        asyncio.create_task(self.storage.log_trade_close(trade_id, {
                            "exit_price":     current_price,
                            "closed_at":      datetime.datetime.utcnow().isoformat(),
                            "hold_time_s":    int(hold_time),
                            "close_reason":   "TIME_EXIT",
                            "close_fee_usdt": round(close_fee, 8),
                            "pnl_gross_usdt": round(pnl_gross, 8),
                            "pnl_net_usdt":   round(pnl_net, 8),
                            "pnl_pct":        round(pnl_pct_margin, 6),
                        }))

                        self.storage.delete_position(raw_sym)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Position Monitor Error: {e}", exc_info=True)

            # Check positions every 2 seconds
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def trade_loop(self) -> None:
        logger.info("Trading loop started…")
        last_reset_day = -1
        while not self._shutdown_event.is_set():
            try:
                # === Daily PnL Reset (UTC midnight) ===
                current_day = datetime.datetime.utcnow().day
                if current_day != last_reset_day:
                    self.risk.reset_daily()
                    last_reset_day = current_day
                    logger.info(f"📅 Daily PnL reset. New trading day (UTC day {current_day})")

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

                            # Skip if RiskManager rejects (Fee/Spread/RR/Drawdown/Cooldown)
                            if risk_params is not None and risk_params.get("action") == "NO_TRADE":
                                logger.info(
                                    f"[{current_time}] {raw_sym} | P: {price:.2f} | "
                                    f"RGM: {regime_info} | RISK_REJECT: {risk_params.get('reason')}"
                                )
                                # ── Fire-and-forget: log rejection (never blocks) ──
                                asyncio.create_task(self.storage.log_rejected({
                                    "symbol":           raw_sym,
                                    "action":           dec["action"],
                                    "strategy":         dec.get("strategy", ""),
                                    "confidence":       dec.get("confidence", 0),
                                    "rejection_reason": risk_params.get("reason", ""),
                                    "current_price":    price,
                                    "daily_pnl":        risk_params.get("daily_pnl", 0),
                                }))
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
                                entry_p  = float(order.get("price", price))
                                qty      = float(order.get("quantity", 0))
                                lev      = int(risk_params.get("leverage", 10))
                                margin   = (entry_p * qty) / max(lev, 1)
                                # Estimate open fee: notional × 0.05% (taker)
                                open_fee = entry_p * qty * 0.0005

                                # ── Step 1: INSERT trade_logs row (fire-and-forget) ──
                                # We await inside the task so we can stash the returned UUID.
                                # The lambda trick keeps the outer loop non-blocking.
                                async def _open_and_store(o=order, ep=entry_p, q=qty,
                                                           lv=lev, mg=margin, of=open_fee,
                                                           sym=raw_sym):
                                    trade_id = await self.storage.log_trade_open({
                                        "symbol":         sym,
                                        "side":           o.get("side", dec["action"]),
                                        "order_id":       o.get("order_id"),
                                        "strategy":       dec.get("strategy", ""),
                                        "execution_type": o.get("execution_type"),
                                        "api_latency_ms": o.get("api_latency_ms"),
                                        "entry_price":    ep,
                                        "quantity":       q,
                                        "leverage":       lv,
                                        "margin_used":    round(mg, 8),
                                        "sl_price":       o.get("sl_price", 0),
                                        "tp_price":       o.get("tp_price", 0),
                                        "open_fee_usdt":  round(of, 8),
                                        "confidence":     dec.get("confidence", 0),
                                        "final_score":    dec.get("final_score", 0),
                                        "e1_direction":   s1.get("direction"),
                                        "e5_regime":      s5.get("regime"),
                                        "error_msg":      o.get("error_msg"),
                                    })
                                    return trade_id

                                # ── Step 2: Update Redis hot state (sync, instant) ──
                                if order.get("status", "SUCCESS") == "SUCCESS":
                                    order['open_time']    = str(time.time())
                                    order['leverage']     = str(lev)
                                    order['open_fee_usdt'] = str(round(open_fee, 8))
                                    # trade_id stored after INSERT completes via callback
                                    async def _store_and_bind(o=order, sym=raw_sym):
                                        tid = await _open_and_store()
                                        if tid:
                                            o['trade_id'] = tid
                                            self.storage.set_position(sym, o)
                                    asyncio.create_task(_store_and_bind())
                                else:
                                    # FAILED order — still log it, no need to store position
                                    asyncio.create_task(_open_and_store())

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
        self._tasks.append(asyncio.create_task(self.position_monitor_loop(), name="position_monitor"))

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
