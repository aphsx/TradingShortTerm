from config import BASE_BALANCE, RISK_PER_TRADE, MAX_LEVERAGE
from strategies import StrategyA, StrategyB, StrategyC

class DecisionEngine:
    def evaluate(self, signals, e5_filter):
        w1 = e5_filter.get('weight_overrides', {}).get('e1', 0.35)
        w2 = e5_filter.get('weight_overrides', {}).get('e2', 0.25)
        w3 = e5_filter.get('weight_overrides', {}).get('e3', 0.20)
        w4 = e5_filter.get('weight_overrides', {}).get('e4', 0.12)
        
        e1, e2, e3, e4 = signals.get('e1', {}), signals.get('e2', {}), signals.get('e3', {}), signals.get('e4', {})
        
        def get_dir_val(d):
            if d in ["BUY_PRESSURE", "MOMENTUM_LONG", "LONG", "CROWD_SHORT"]: return 1
            if d in ["SELL_PRESSURE", "MOMENTUM_SHORT", "SHORT", "CROWD_LONG"]: return -1
            return 0
            
        s1 = get_dir_val(e1.get('direction')) * e1.get('strength', 0)
        s2 = get_dir_val(e2.get('direction')) * e2.get('strength', 0)
        s3 = get_dir_val(e3.get('direction')) * e3.get('strength', 0)
        s4 = get_dir_val(e4.get('direction')) * e4.get('strength', 0)
        
        final_score = s1*w1 + s2*w2 + s3*w3 + s4*w4
        
        if abs(final_score) < 0.55 or not e5_filter.get('tradeable', True):
            return {"action": "NO_TRADE", "final_score": final_score}
            
        action = "LONG" if final_score > 0 else "SHORT"
        
        score_a = StrategyA().evaluate(signals)
        score_b = StrategyB().evaluate(signals)
        score_c = StrategyC().evaluate(signals)
        
        strategies = [("A", score_a), ("B", score_b), ("C", score_c)]
        best_strategy = max(strategies, key=lambda x: x[1])
        
        if best_strategy[1] < 0.4:
            return {"action": "NO_TRADE", "final_score": final_score}
            
        return {
            "action": action,
            "strategy": best_strategy[0],
            "confidence": min(abs(final_score) * 100 * (1 + best_strategy[1]), 100),
            "final_score": final_score
        }

class RiskManager:
    def calculate(self, decision, current_price, atr, e5_param):
        confidence = decision.get("confidence", 0)
        risk_pct = RISK_PER_TRADE
        if confidence >= 80: risk_pct = 0.015
        elif confidence >= 60: risk_pct = 0.010
        else: risk_pct = 0.005
        
        risk_amount = BASE_BALANCE * risk_pct
        atr_multiplier_sl = e5_param.get('sl_multiplier', 1.0)
        atr_multiplier_tp = e5_param.get('tp_multiplier', 1.0)
        
        sl_distance = atr * 0.8 * atr_multiplier_sl if atr else (current_price * 0.002)
        tp1_distance = atr * 1.3 * atr_multiplier_tp if atr else (current_price * 0.004)
        
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
    def __init__(self, binance_client=None, testnet=True):
        self.client = binance_client
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
            "strategy": decision['strategy']
        }
        
        if self.client:
            try:
                print(f"[{'TESTNET' if self.testnet else 'LIVE MARKET'}] Adjusting leverage to {int(risk_params['leverage'])}x for {symbol}...")
                await self.client.futures_change_leverage(symbol=symbol, leverage=int(risk_params['leverage']))
                
                print(f"[{'TESTNET' if self.testnet else 'LIVE MARKET'}] Sending {side} order ({order_details['quantity']} @ {order_details['price']})...")
                res = await self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='LIMIT',
                    timeInForce='GTX',
                    quantity=order_details["quantity"],
                    price=order_details["price"]
                )
                print(f"✅ Order Executed Successfully! Order ID: {res.get('orderId')}")
                # You could also send SL and TP orders here automatically!
            except Exception as e:
                print(f"❌ API Error sending order: {e}")
                return None
        else:
            print(f"🔥 [SIMULATED] order to Binance: {order_details}")
            
        return order_details
