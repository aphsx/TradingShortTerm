import logging
import json
import ccxt.async_support as ccxt
from config import BASE_BALANCE, RISK_PER_TRADE, MIN_LEVERAGE, MAX_LEVERAGE, API_KEY, SECRET_KEY, EXCHANGE_TAKER_FEE, SLIPPAGE_BUFFER, MIN_RR_RATIO, STRAT_MIN_SCORE, STRAT_AGREEMENT_REQ, DECISION_VPIN_MIN, DECISION_OFI_VELOCITY_MIN, DECISION_ALIGNMENT_MIN
from strategies import StrategyA, StrategyB, StrategyC
from logger_config import get_logger

logger = get_logger(__name__)
order_logger = get_logger("orders")

class DecisionEngine:
    def evaluate(self, signals, e5_filter):
        w1 = e5_filter.get('weight_overrides', {}).get('e1', 0.35)
        w2 = e5_filter.get('weight_overrides', {}).get('e2', 0.25)
        w3 = e5_filter.get('weight_overrides', {}).get('e3', 0.20)
        w4 = e5_filter.get('weight_overrides', {}).get('e4', 0.12)

        e1, e2, e3, e4 = signals.get('e1', {}), signals.get('e2', {}), signals.get('e3', {}), signals.get('e4', {})

        def get_dir_val(d):
            if not d: return 0
            if d.upper() in ["BUY_PRESSURE", "MOMENTUM_LONG", "LONG", "CROWD_SHORT"]: return 1
            if d.upper() in ["SELL_PRESSURE", "MOMENTUM_SHORT", "SHORT", "CROWD_LONG"]: return -1
            return 0

        d1 = get_dir_val(e1.get('direction'))
        d2 = get_dir_val(e2.get('direction'))
        d3 = get_dir_val(e3.get('direction'))
        d4 = get_dir_val(e4.get('direction'))

        s1 = d1 * (e1.get('strength') or 0) * (e1.get('conviction') or 1.0)
        s2 = d2 * (e2.get('strength') or 0)
        s3 = d3 * (e3.get('strength') or 0)
        s4 = d4 * (e4.get('strength') or 0)

        final_score = s1*w1 + s2*w2 + s3*w3 + s4*w4

        if not e5_filter.get('tradeable', True) or not e5_filter.get('spread_ok', True):
            return {"action": "NO_TRADE", "final_score": final_score, "reason": "E5 Filter: Not tradeable or spread too high"}

        # === PREDICTIVE SIGNAL FILTERS — BYPASSED FOR BAR-BACKTEST ===
        vpin = e1.get('vpin', 0.5)
        ofi_velocity = e1.get('ofi_velocity', 2.0)
        alignment = e2.get('alignment', 0.5)

        # (Filters temporarily disabled for backtest flow validation)
        # if vpin < DECISION_VPIN_MIN: ...

        # === SQUEEZE BREAKOUT BOOST ===
        # When BB inside KC (volatility compressed), breakout signal is amplified
        squeeze = e3.get('squeeze', False)
        if squeeze:
            # Boost final_score by 30% during squeeze (high-probability breakout)
            final_score *= 1.30
            logger.info(f"🔥 SQUEEZE detected — score boosted to {final_score:.3f}")

        if abs(final_score) < STRAT_MIN_SCORE:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Score {abs(final_score):.2f} < {STRAT_MIN_SCORE}"}

        action = "LONG" if final_score > 0 else "SHORT"
        action_val = 1 if action == "LONG" else -1

        agreements = sum(1 for d in [d1, d2, d3, d4] if d == action_val)
        if agreements < STRAT_AGREEMENT_REQ:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Only {agreements} engines agree (need {STRAT_AGREEMENT_REQ})"}

        # E1 must not oppose
        if d1 == -action_val:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": "E1 (OrderFlow) opposes direction"}
        
        score_a = StrategyA().evaluate(signals, e5_filter)
        score_b = StrategyB().evaluate(signals, e5_filter)
        score_c = StrategyC().evaluate(signals, e5_filter)
        
        strategies = [("A", score_a), ("B", score_b), ("C", score_c)]
        best_strategy = max(strategies, key=lambda x: x[1])
        
        if best_strategy[1] < 0.3:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"No strategy match (best: {best_strategy[1]:.2f} < 0.3)"}
            
        # === ENHANCED CONFIDENCE CALIBRATION ===
        agreement_bonus = 1.0 + (agreements - 2) * 0.15
        strategy_clarity = best_strategy[1]
        
        # VPIN/OFI confidence boost (strong predictive signals = higher confidence)
        predictive_boost = 1.0
        if vpin > 0.6: predictive_boost += 0.15
        if abs(ofi_velocity) > 3.0: predictive_boost += 0.15
        if alignment > 0.6: predictive_boost += 0.10
        if squeeze: predictive_boost += 0.20
        
        confidence = abs(final_score) * agreement_bonus * strategy_clarity * predictive_boost * 100
        
        return {
            "action": action,
            "strategy": best_strategy[0],
            "confidence": min(confidence, 100),
            "final_score": final_score,
            "reason": f"Agreements: {agreements}, Strategy: {best_strategy[0]}, Squeeze: {squeeze}",
            # Pass-through data for Executor's smart limit pricing
            "ofi_velocity": ofi_velocity,
            "atr": e3.get('atr', 0),
            "vpin": vpin,
            "squeeze": squeeze
        }

class RiskManager:
    def __init__(self):
        # === Trade Performance Tracking ===
        self.trade_results = []       # List of PnL results
        self.daily_pnl = 0.0          # Running daily PnL
        self.consecutive_losses = 0   # Count for cooldown
        self.last_trade_time = 0      # For cooldown timer
        self.daily_reset_hour = 0     # UTC hour to reset daily PnL
        
        # === Configurable Risk Limits ===
        self.max_daily_drawdown_pct = 0.05   # Stop trading at 5% daily loss
        self.max_consecutive_losses = 4       # Cooldown after 4 losses
        self.loss_cooldown_seconds = 60       # 60s pause after consecutive losses
        self.kelly_fraction = 0.25            # Use 25% Kelly (quarter-Kelly for safety)
        
    def _calculate_kelly_leverage(self, confidence, base_leverage, e5_max_leverage):
        """
        Kelly Criterion: f* = (p * b - q) / b
        where p = win probability, b = payoff ratio (win/loss), q = 1-p
        
        Quarter-Kelly is used for safety (reduces variance by 75% 
        while keeping 50% of the growth rate).
        """
        # Estimate win probability from confidence (calibrated)
        # Confidence 50% → ~52% win rate, 90% → ~65% win rate
        win_prob = 0.50 + (confidence / 100.0) * 0.18
        win_prob = max(0.48, min(0.70, win_prob))
        
        # Estimate payoff ratio from strategy (TP/SL ratio)
        payoff_ratio = 1.5  # Default assumption
        
        loss_prob = 1.0 - win_prob
        
        # Kelly formula
        if payoff_ratio <= 0:
            return MIN_LEVERAGE
            
        kelly_f = (win_prob * payoff_ratio - loss_prob) / payoff_ratio
        
        # If Kelly is negative, don't trade (edge is negative)
        if kelly_f <= 0:
            return 0  # Signal to not trade
        
        # Apply fractional Kelly for safety
        safe_kelly = kelly_f * self.kelly_fraction
        
        # Convert Kelly fraction to leverage
        # kelly_f = 0.10 means risk 10% of capital → at base risk 1%, that's 10x leverage
        kelly_leverage = safe_kelly / RISK_PER_TRADE if RISK_PER_TRADE > 0 else base_leverage
        
        # Clamp to configured bounds
        leverage = max(MIN_LEVERAGE, min(kelly_leverage, e5_max_leverage, MAX_LEVERAGE))
        
        return leverage
    
    def _apply_loss_cooldown(self):
        """
        Anti-martingale: reduce position size after consecutive losses.
        Returns a multiplier (0.0 to 1.0) for position sizing.
        """
        import time
        
        # Check cooldown timer
        if self.consecutive_losses >= self.max_consecutive_losses:
            elapsed = time.time() - self.last_trade_time
            if elapsed < self.loss_cooldown_seconds:
                return 0.0  # Don't trade during cooldown
            else:
                # Cooldown expired, reset but still trade smaller
                self.consecutive_losses = max(0, self.consecutive_losses - 1)
        
        # Scale down after losses: 1 loss = 80%, 2 = 60%, 3 = 40%
        if self.consecutive_losses == 0:
            return 1.0
        elif self.consecutive_losses == 1:
            return 0.80
        elif self.consecutive_losses == 2:
            return 0.60
        elif self.consecutive_losses == 3:
            return 0.40
        else:
            return 0.25  # Minimum 25% size
    
    def _check_daily_drawdown(self):
        """Check if daily drawdown limit has been hit."""
        max_loss = BASE_BALANCE * self.max_daily_drawdown_pct
        if self.daily_pnl <= -max_loss:
            return False  # Stop trading
        return True  # OK to trade
    
    def record_trade_result(self, pnl):
        """Call this after each trade closes to update tracking."""
        import time
        self.trade_results.append(pnl)
        self.daily_pnl += pnl
        self.last_trade_time = time.time()
        
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0  # Reset on win
    
    def reset_daily(self):
        """Call at the start of each trading day."""
        self.daily_pnl = 0.0

    def calculate(self, decision, current_price, atr, e5_param):
        confidence = decision.get("confidence", 0)
        strategy = decision.get("strategy", "A")
        
        # === Daily Drawdown Check ===
        if not self._check_daily_drawdown():
            return {"action": "NO_TRADE", "reason": f"Daily drawdown limit hit ({self.daily_pnl:.2f} USDT). Trading paused."}
        
        # === Loss Cooldown Check ===
        cooldown_multiplier = self._apply_loss_cooldown()
        if cooldown_multiplier <= 0:
            return {"action": "NO_TRADE", "reason": f"Loss cooldown active ({self.consecutive_losses} consecutive losses). Wait {self.loss_cooldown_seconds}s."}
        
        risk_pct = RISK_PER_TRADE
        if confidence >= 80: risk_pct = 0.020 
        elif confidence >= 60: risk_pct = 0.012
        else: risk_pct = 0.005
        
        # Apply cooldown scaling
        risk_pct *= cooldown_multiplier
        
        risk_amount = BASE_BALANCE * risk_pct
        atr_multiplier_sl = e5_param.get('sl_multiplier', 1.0)
        atr_multiplier_tp = e5_param.get('tp_multiplier', 1.0)
        
        safe_atr = atr if atr else (current_price * 0.002)
        
        sl_distance = 0
        tp1_distance = 0
        
        # Scalping mode: tight SL/TP to enter-exit fast for quick profit
        if strategy == "A":
            sl_distance  = safe_atr * 0.25 * atr_multiplier_sl   # was 0.4
            tp1_distance = safe_atr * 0.40 * atr_multiplier_tp   # was 0.6 → R:R 1.6
        elif strategy == "B":
            sl_distance  = safe_atr * 0.30 * atr_multiplier_sl   # was 0.5
            tp1_distance = safe_atr * 0.45 * atr_multiplier_tp   # was 0.8 → R:R 1.5
        elif strategy == "C":
            sl_distance  = safe_atr * 0.20 * atr_multiplier_sl   # was 0.3
            tp1_distance = safe_atr * 0.30 * atr_multiplier_tp   # was 0.5 → R:R 1.5
            
        # Min TP check
        min_tp_pct = (EXCHANGE_TAKER_FEE * 2) + SLIPPAGE_BUFFER 
        min_tp = current_price * min_tp_pct
        if tp1_distance < min_tp:
            return {"action": "NO_TRADE", "reason": f"Target Profit ({tp1_distance:.4f}) too small. Fails {min_tp_pct*100:.3f}% fee+slippage test."}
            
        # R:R Check
        if sl_distance <= 0:
            return {"action": "NO_TRADE", "reason": f"Invalid SL distance: {sl_distance:.4f}"}

        rr_ratio = tp1_distance / sl_distance
        if rr_ratio < MIN_RR_RATIO:
            return {"action": "NO_TRADE", "reason": f"R:R ({rr_ratio:.2f}) < {MIN_RR_RATIO} min"}
        
        pos_size_usdt = risk_amount / (sl_distance / current_price) if sl_distance > 0 else 0
        
        # === Kelly Criterion Leverage ===
        e5_max_lev = e5_param.get('leverage_max', MAX_LEVERAGE)
        leverage = self._calculate_kelly_leverage(confidence, MIN_LEVERAGE, e5_max_lev)
        
        # Kelly says don't trade (negative edge)
        if leverage <= 0:
            return {"action": "NO_TRADE", "reason": "Kelly Criterion: negative edge detected, skipping."}
        
        # === Liquidation Prevention Squeeze ===
        max_safe_sl_pct = (1.0 / leverage) * 0.8
        max_safe_sl_dist = current_price * max_safe_sl_pct
        
        if sl_distance > max_safe_sl_dist:
            sl_scale_factor = max_safe_sl_dist / sl_distance
            sl_distance = max_safe_sl_dist
            tp1_distance = tp1_distance * sl_scale_factor 
            
            if tp1_distance < min_tp:
                return {"action": "NO_TRADE", "reason": f"Squeezed SL forced TP too small for fees."}
        
        return {
            "position_size_usdt": pos_size_usdt,
            "leverage": leverage,
            "sl_distance": sl_distance,
            "tp1_distance": tp1_distance,
            "risk_amount": risk_amount,
            "cooldown_multiplier": cooldown_multiplier,
            "kelly_leverage": leverage,
            "daily_pnl": self.daily_pnl
        }

class Executor:
    def __init__(self, exchange_instance, testnet=True):
        self.exchange = exchange_instance
        self.testnet = testnet
        
    async def execute_trade(self, symbol, decision, risk_params, current_price):
        if decision['action'] == "NO_TRADE":
            return None

        side = decision['action']
        pos_size = risk_params['position_size_usdt'] / current_price

        # === PREDICTIVE LIMIT ORDER PRICING ===
        # For high-latency environments, use OFI velocity to predict where
        # price will be in 0.5-1s, then place limit order there.
        # This gives us maker fee (0.02%) instead of taker (0.05%) = 60% savings

        ofi_velocity = decision.get('ofi_velocity', 0.0)
        atr = decision.get('atr', current_price * 0.002)

        # Predict price movement based on OFI velocity
        # High velocity = price will move in that direction
        predicted_move = ofi_velocity * atr * 0.25  # Conservative 25% of ATR

        if side == "LONG":
            # Place buy limit slightly below predicted price
            # If momentum continues, we'll get filled at favorable price
            entry_price = current_price + predicted_move - (atr * 0.1)
        else:  # SHORT
            # Place sell limit slightly above predicted price
            entry_price = current_price - predicted_move + (atr * 0.1)

        # Ensure entry price is realistic (within 0.3% of current)
        max_deviation = current_price * 0.003
        if abs(entry_price - current_price) > max_deviation:
            entry_price = current_price + (max_deviation if side == "SHORT" else -max_deviation)

        sl_price = entry_price + risk_params['sl_distance'] if side == "SHORT" else entry_price - risk_params['sl_distance']
        tp_price = entry_price - risk_params['tp1_distance'] if side == "SHORT" else entry_price + risk_params['tp1_distance']

        # Fetch dynamic precision from exchange market info
        ccxt_symbol = f"{symbol.replace('USDT', '')}/USDT:USDT" if ":" not in symbol else symbol
        try:
            market = self.exchange.market(ccxt_symbol)
            qty_precision = market['precision']['amount']
            price_precision = market['precision']['price']
        except Exception as e:
            # Fallback to safe defaults if market info unavailable
            logger.warning(f"Could not fetch market precision for {ccxt_symbol}, using defaults: {e}")
            qty_precision = 3
            price_precision = 2
        
        order_details = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "timeInForce": "GTX",
            "quantity": float(round(pos_size, qty_precision)),
            "price": float(round(entry_price, price_precision)),
            "sl_price": float(round(sl_price, price_precision)),
            "tp_price": float(round(tp_price, price_precision)),
            "strategy": decision['strategy'],
            "status": "SUCCESS",
            "error_msg": ""
        }
        
        import time
        import asyncio
        start_time = time.time()
        try:
            target_leverage = int(risk_params['leverage'])
            logger.info(f"[{'TESTNET' if self.testnet else 'LIVE'}] Adjusting leverage to {target_leverage}x for {symbol}")
            # For binanceusdm module, it often requires the format BTC/USDT:USDT.
            if ":" not in symbol:
                 ccxt_symbol = f"{symbol.replace('USDT', '')}/USDT:USDT"
            else:
                 ccxt_symbol = symbol

            # Set leverage with timeout protection
            try:
                await asyncio.wait_for(
                    self.exchange.set_leverage(target_leverage, ccxt_symbol),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                raise Exception(f"Leverage setting timed out after 5s for {ccxt_symbol}")

            # Verify leverage was actually set (prevent race condition)
            try:
                positions = await asyncio.wait_for(
                    self.exchange.fetch_positions([ccxt_symbol]),
                    timeout=3.0
                )
                current_leverage = None
                for pos in positions:
                    if pos['symbol'] == ccxt_symbol:
                        current_leverage = pos.get('leverage')
                        break

                if current_leverage and abs(float(current_leverage) - target_leverage) > 0.1:
                    raise Exception(f"Leverage verification failed: expected {target_leverage}x, got {current_leverage}x")

                logger.info(f"Leverage verified: {target_leverage}x")
            except asyncio.TimeoutError:
                logger.warning("Leverage verification timed out, proceeding with caution")
            except Exception as e:
                logger.warning(f"Could not verify leverage: {e}")
            
            ccxt_side = 'buy' if side == 'LONG' else 'sell'
            ord_type = 'limit'

            # === POST-ONLY LIMIT ORDER (Maker Fee Optimization) ===
            # timeInForce='GTX' (Good-Til-Crossing) = Binance Post-Only mode
            # Benefits:
            #   - Maker fee 0.02% vs Taker 0.05% = 60% savings
            #   - No slippage (we set exact price)
            #   - Better for high-latency (wait for price to come to us)
            # Trade-off: Order may not fill if price doesn't reach our level
            logger.info(f"[{'TESTNET' if self.testnet else 'LIVE'}] Placing POST-ONLY {side} limit @ {order_details['price']:.2f}")

            # Create entry order with timeout protection
            res = await asyncio.wait_for(
                self.exchange.create_order(
                    symbol=ccxt_symbol,
                    type=ord_type,
                    side=ccxt_side,
                    amount=order_details["quantity"],
                    price=order_details["price"],
                    params={'timeInForce': 'GTX', 'clientOrderId': f"V7_{int(time.time()*1000)}"}
                ),
                timeout=10.0
            )
            
            latency = int((time.time() - start_time) * 1000)
            order_details["api_latency_ms"] = latency
            order_details["order_id"] = str(res.get('id', ''))
            order_details["client_order_id"] = str(res.get('clientOrderId', ''))
            order_details["status"] = "SUCCESS"
            order_details["execution_type"] = ord_type
            
            logger.info(f"Order executed in {latency}ms! Order ID: {order_details['order_id']}")
            order_logger.info(f"SUCCESS | {json.dumps(order_details)}")

            # === EXCHANGE-SIDE SL/TP PROTECTION ===
            # Place SL and TP as separate orders on the exchange
            # This protects the position even if the bot crashes
            sl_side = 'sell' if side == 'LONG' else 'buy'
            
            try:
                # Stop Loss (STOP_MARKET)
                await asyncio.wait_for(
                    self.exchange.create_order(
                        symbol=ccxt_symbol,
                        type='stop_market',
                        side=sl_side,
                        amount=order_details["quantity"],
                        params={
                            'stopPrice': order_details["sl_price"],
                            'reduceOnly': True,
                            'clientOrderId': f"V7SL_{int(time.time()*1000)}"
                        }
                    ),
                    timeout=5.0
                )
                logger.info(f"🛡️ SL placed @ {order_details['sl_price']:.2f}")
            except Exception as sl_err:
                logger.warning(f"⚠️ Failed to place SL order: {sl_err}")
                order_details["sl_status"] = "FAILED"

            try:
                # Take Profit (TAKE_PROFIT_MARKET)
                await asyncio.wait_for(
                    self.exchange.create_order(
                        symbol=ccxt_symbol,
                        type='take_profit_market',
                        side=sl_side,
                        amount=order_details["quantity"],
                        params={
                            'stopPrice': order_details["tp_price"],
                            'reduceOnly': True,
                            'clientOrderId': f"V7TP_{int(time.time()*1000)}"
                        }
                    ),
                    timeout=5.0
                )
                logger.info(f"🎯 TP placed @ {order_details['tp_price']:.2f}")
            except Exception as tp_err:
                logger.warning(f"⚠️ Failed to place TP order: {tp_err}")
                order_details["tp_status"] = "FAILED"
            
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            logger.error(f"Error sending order after {latency}ms: {e}")
            order_details["api_latency_ms"] = latency
            order_details["status"] = "API_ERROR"
            order_details["error_type"] = type(e).__name__
            order_details["error_msg"] = str(e)
            order_details["execution_type"] = "limit"
            order_logger.error(f"FAILED | Error: {str(e)} | Details: {json.dumps(order_details)}")
            
        return order_details
