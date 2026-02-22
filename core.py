import logging
import json
import ccxt.async_support as ccxt
from config import BASE_BALANCE, RISK_PER_TRADE, MIN_LEVERAGE, MAX_LEVERAGE, API_KEY, SECRET_KEY, EXCHANGE_TAKER_FEE, SLIPPAGE_BUFFER, MIN_RR_RATIO, STRAT_MIN_SCORE, STRAT_AGREEMENT_REQ
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

        # === PREDICTIVE SIGNAL FILTERS (High-Latency Optimization) ===
        # For 30-80ms latency environments, we need leading indicators
        # that predict price movement 0.5-2 seconds ahead

        vpin = e1.get('vpin', 0.0)
        ofi_velocity = e1.get('ofi_velocity', 0.0)
        alignment = e2.get('alignment', 0.0)

        # VPIN Filter: Require informed trading activity
        # Research shows VPIN > 0.4 indicates informed traders active
        if vpin < 0.35:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Low VPIN ({vpin:.2f}) - no informed trading detected"}

        # OFI Velocity Filter: Require momentum building
        # |velocity| > 1.5 indicates orderbook imbalance accelerating
        if abs(ofi_velocity) < 1.5:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Low OFI velocity ({ofi_velocity:.2f}) - momentum not building"}

        # Multi-timeframe Alignment Filter: Require consensus
        # Alignment > 0.4 means 1s, 5s, 15s windows agree on direction
        if alignment < 0.35:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Low momentum alignment ({alignment:.2f}) - timeframes disagree"}

        # === END PREDICTIVE FILTERS ===

        # Reduced strictness for short-term active scalping (Dynamic)
        if abs(final_score) < STRAT_MIN_SCORE:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Final score {abs(final_score):.2f} < {STRAT_MIN_SCORE} min"}

        action = "LONG" if final_score > 0 else "SHORT"
        action_val = 1 if action == "LONG" else -1

        # Agreement Check: Reduced for aggressive short-term trading (Dynamic)
        agreements = sum(1 for d in [d1, d2, d3, d4] if d == action_val)
        if agreements < STRAT_AGREEMENT_REQ:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": f"Only {agreements} engines agree (need {STRAT_AGREEMENT_REQ} for scalping)"}

        # E1 Check
        if d1 == -action_val:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": "E1 (Primary) opposes the direction"}
        
        score_a = StrategyA().evaluate(signals, e5_filter)
        score_b = StrategyB().evaluate(signals, e5_filter)
        score_c = StrategyC().evaluate(signals, e5_filter)
        
        strategies = [("A", score_a), ("B", score_b), ("C", score_c)]
        best_strategy = max(strategies, key=lambda x: x[1])
        
        if best_strategy[1] < 0.4:
            return {"action": "NO_TRADE", "final_score": final_score, "reason": "No clear strategy match (score < 0.4)"}
            
        agreement_bonus = 1.0 + (agreements - 3) * 0.1
        strategy_clarity = best_strategy[1] / 1.0
        confidence = abs(final_score) * agreement_bonus * strategy_clarity * 100
        
        return {
            "action": action,
            "strategy": best_strategy[0],
            "confidence": min(confidence, 100),
            "final_score": final_score,
            "reason": f"Agreements: {agreements}, Strategy: {best_strategy[0]}"
        }

class RiskManager:
    def calculate(self, decision, current_price, atr, e5_param):
        confidence = decision.get("confidence", 0)
        strategy = decision.get("strategy", "A")
        
        risk_pct = RISK_PER_TRADE
        if confidence >= 80: risk_pct = 0.020 # Aggressive short term sizing
        elif confidence >= 60: risk_pct = 0.012
        else: risk_pct = 0.005
        
        risk_amount = BASE_BALANCE * risk_pct
        atr_multiplier_sl = e5_param.get('sl_multiplier', 1.0)
        atr_multiplier_tp = e5_param.get('tp_multiplier', 1.0)
        
        safe_atr = atr if atr else (current_price * 0.002)
        
        sl_distance = 0
        tp1_distance = 0
        
        if strategy == "A":
            sl_distance = safe_atr * 0.4 * atr_multiplier_sl # Extremely tight SL for momentum failures
            tp1_distance = safe_atr * 0.6 * atr_multiplier_tp # Quick TP for breakout scalps
        elif strategy == "B":
            sl_distance = safe_atr * 0.5 * atr_multiplier_sl
            tp1_distance = safe_atr * 0.8 * atr_multiplier_tp # Mean reversion TP
        elif strategy == "C":
            sl_distance = safe_atr * 0.3 * atr_multiplier_sl # Lightning tight SL for liquidation clusters
            tp1_distance = safe_atr * 0.5 * atr_multiplier_tp
            
        # Min TP check (Dynamic calculation based on Exchange Taker Fees and Slippage Buffer defined in .env)
        # For a scalping strategy, if the actual price movement required to hit TP is less than the round-trip fee + slip, it's just paying fees.
        min_tp_pct = (EXCHANGE_TAKER_FEE * 2) + SLIPPAGE_BUFFER 
        min_tp = current_price * min_tp_pct
        if tp1_distance < min_tp:
            return {"action": "NO_TRADE", "reason": f"Target Profit ({tp1_distance:.4f}) too small. Fails {min_tp_pct*100:.3f}% dynamic fee+slippage test."}
            
        # R:R Check - Dynamic floor for high win-rate scalping
        # CRITICAL: Check sl_distance first to prevent division by zero
        if sl_distance <= 0:
            return {"action": "NO_TRADE", "reason": f"Invalid SL distance: {sl_distance:.4f}"}

        rr_ratio = tp1_distance / sl_distance
        if rr_ratio < MIN_RR_RATIO:
            return {"action": "NO_TRADE", "reason": f"R:R ({rr_ratio:.2f}) < {MIN_RR_RATIO} min"}
        
        pos_size_usdt = risk_amount / (sl_distance / current_price) if sl_distance > 0 else 0
        
        # --- Leverage Clamping ---
        # User requested exact bounds: 10x minimum, 30x maximum
        leverage = min(pos_size_usdt / (BASE_BALANCE * 0.1), e5_param.get('leverage_max', MAX_LEVERAGE), MAX_LEVERAGE)
        leverage = max(leverage, MIN_LEVERAGE)
        
        # --- Liquidation Prevention Squeeze ---
        # At 30x leverage, Binance margin is ~3.33%. 
        # If sl_distance > 3%, the position will liquidate *before* it hits SL.
        max_safe_sl_pct = (1.0 / leverage) * 0.8 # Clamp SL to max 80% of margin allowed before liquidation
        max_safe_sl_dist = current_price * max_safe_sl_pct
        
        if sl_distance > max_safe_sl_dist:
            # Squeeze SL down to the safe liquidation-proof limit
            sl_scale_factor = max_safe_sl_dist / sl_distance
            sl_distance = max_safe_sl_dist
            # Squeeze TP in tandem to maintain original Profit/Loss ratio
            tp1_distance = tp1_distance * sl_scale_factor 
            
            # Re-check TP against exchange fees after the squeeze
            if tp1_distance < min_tp:
                return {"action": "NO_TRADE", "reason": f"Squeezed 30x SL forced TP too small for fees."}
        
        return {
            "position_size_usdt": pos_size_usdt,
            "leverage": leverage,
            "sl_distance": sl_distance,
            "tp1_distance": tp1_distance,
            "risk_amount": risk_amount
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
            "quantity": round(pos_size, qty_precision),
            "price": round(entry_price, price_precision),
            "sl_price": round(sl_price, price_precision),
            "tp_price": round(tp_price, price_precision),
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

            # Create order with timeout protection (prevent hanging)
            res = await asyncio.wait_for(
                self.exchange.create_order(
                    symbol=ccxt_symbol,
                    type=ord_type,
                    side=ccxt_side,
                    amount=order_details["quantity"],
                    price=order_details["price"],
                    params={'timeInForce': 'GTX', 'clientOrderId': f"V7_{int(time.time()*1000)}"}
                ),
                timeout=10.0  # 10 second timeout for order placement
            )
            
            latency = int((time.time() - start_time) * 1000)
            order_details["api_latency_ms"] = latency
            order_details["order_id"] = str(res.get('id', ''))
            order_details["client_order_id"] = str(res.get('clientOrderId', ''))
            order_details["status"] = "SUCCESS"
            order_details["execution_type"] = ord_type
            
            logger.info(f"Order executed in {latency}ms! Order ID: {order_details['order_id']}")
            order_logger.info(f"SUCCESS | {json.dumps(order_details)}")
            
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
