import logging
import json
import ccxt.async_support as ccxt
import ccxt.async_support as ccxt
from config import BASE_BALANCE, RISK_PER_TRADE, MAX_LEVERAGE, API_KEY, SECRET_KEY, EXCHANGE_TAKER_FEE, SLIPPAGE_BUFFER, MIN_RR_RATIO, STRAT_MIN_SCORE, STRAT_AGREEMENT_REQ
from strategies import StrategyA, StrategyB, StrategyC

# Configure Order Logger (Save orders to file)
order_logger = logging.getLogger("OrderLogger")
order_logger.setLevel(logging.INFO)
if not order_logger.handlers:
    fh = logging.FileHandler("orders.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    order_logger.addHandler(fh)

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
        if sl_distance == 0 or (tp1_distance / sl_distance) < MIN_RR_RATIO:
            return {"action": "NO_TRADE", "reason": f"R:R ({tp1_distance/sl_distance if sl_distance else 0:.2f}) < {MIN_RR_RATIO} min"}
        
        pos_size_usdt = risk_amount / (sl_distance / current_price) if sl_distance > 0 else 0
        leverage = min(pos_size_usdt / (BASE_BALANCE * 0.1), e5_param.get('leverage_max', MAX_LEVERAGE), 12)
        leverage = max(leverage, 5)
        
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
        
        entry_price = current_price * 1.0001 if side == "SHORT" else current_price * 0.9999
        sl_price = entry_price + risk_params['sl_distance'] if side == "SHORT" else entry_price - risk_params['sl_distance']
        tp_price = entry_price - risk_params['tp1_distance'] if side == "SHORT" else entry_price + risk_params['tp1_distance']
        
        # Determine precision based on symbol (approximate mapping for simplicity)
        qty_precision = 3 if symbol == "BTCUSDT" else 2 if "ETH" in symbol else 0
        price_precision = 1 if symbol == "BTCUSDT" else 2 if "ETH" in symbol else 4
        
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
        start_time = time.time()
        try:
            print(f"[{'TESTNET' if self.testnet else 'LIVE MARKET'}] Adjusting leverage to {int(risk_params['leverage'])}x for {symbol}...")
            # For binanceusdm module, it often requires the format BTC/USDT:USDT.
            if ":" not in symbol:
                 ccxt_symbol = f"{symbol.replace('USDT', '')}/USDT:USDT"
            else:
                 ccxt_symbol = symbol
                 
            await self.exchange.set_leverage(int(risk_params['leverage']), ccxt_symbol)
            
            ccxt_side = 'buy' if side == 'LONG' else 'sell'
            ord_type = 'limit'
            print(f"[{'TESTNET' if self.testnet else 'LIVE MARKET'}] CCXT Sending {side} ({ccxt_side}) {ord_type} order ({order_details['quantity']} @ {order_details['price']})...")
            
            res = await self.exchange.create_order(
                symbol=ccxt_symbol,
                type=ord_type,
                side=ccxt_side,
                amount=order_details["quantity"],
                price=order_details["price"],
                params={'timeInForce': 'GTX', 'clientOrderId': f"V7_{int(time.time()*1000)}"}
            )
            
            latency = int((time.time() - start_time) * 1000)
            order_details["api_latency_ms"] = latency
            order_details["order_id"] = str(res.get('id', ''))
            order_details["client_order_id"] = str(res.get('clientOrderId', ''))
            order_details["status"] = "SUCCESS"
            order_details["execution_type"] = ord_type
            
            print(f"CCXT Order Executed in {latency}ms! Order ID: {order_details['order_id']}")
            order_logger.info(f"SUCCESS | {json.dumps(order_details)}")
            
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            print(f"CCXT Error sending order after {latency}ms: {e}")
            order_details["api_latency_ms"] = latency
            order_details["status"] = "API_ERROR"
            order_details["error_type"] = type(e).__name__
            order_details["error_msg"] = str(e)
            order_details["execution_type"] = "limit"
            order_logger.error(f"FAILED | Error: {str(e)} | Details: {json.dumps(order_details)}")
            
        return order_details
