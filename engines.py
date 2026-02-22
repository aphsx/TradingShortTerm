from utils import calculate_imbalance, calculate_rsi, calculate_atr, calculate_bollinger_bands

class Engine1OrderFlow:
    def process(self, orderbook, ticks):
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if not bids or not asks:
            return {
                "direction": None,
                "strength": None,
                "conviction": None,
                "imbalance": None,
                "cvd_slope": None,
                "micro_price": None
            }
            
        imbalance = calculate_imbalance(bids, asks)
        
        direction = "NEUTRAL"
        if imbalance > 0.3: direction = "BUY_PRESSURE"
        elif imbalance < -0.3: direction = "SELL_PRESSURE"
        
        return {
            "direction": direction,
            "strength": abs(imbalance),
            "conviction": abs(imbalance),
            "imbalance": imbalance,
            "cvd_slope": 0,
            "micro_price": (float(bids[0][0])*float(asks[0][1]) + float(asks[0][0])*float(bids[0][1]))/(float(bids[0][1])+float(asks[0][1])) if bids and asks else 0
        }

class Engine2Tick:
    def process(self, ticks):
        if not ticks:
            return {
                "direction": None, 
                "strength": None, 
                "velocity_ratio": None, 
                "aggressor_ratio": None,
                "streak": None, 
                "volume_spike": None,
                "spike_ratio": None
            }
        buy_vol = sum(float(t.get('q', 0)) for t in ticks if not t.get('m', False))
        sell_vol = sum(float(t.get('q', 0)) for t in ticks if t.get('m', False))
        
        aggressor_ratio = buy_vol / (buy_vol + sell_vol) if (buy_vol + sell_vol) > 0 else 0.5
        
        direction = "NEUTRAL"
        if aggressor_ratio > 0.65: direction = "MOMENTUM_LONG"
        elif aggressor_ratio < 0.35: direction = "MOMENTUM_SHORT"
        
        return {
            "direction": direction,
            "strength": abs(aggressor_ratio - 0.5) * 2,
            "velocity_ratio": 1.5,
            "aggressor_ratio": aggressor_ratio,
            "streak": 5,
            "volume_spike": False,
            "spike_ratio": 1.0
        }

class Engine3Technical:
    def process(self, klines):
        if not klines or len(klines) < 20:
            return {
                "direction": None, 
                "strength": None, 
                "atr": None, 
                "bb_zone": None, 
                "rsi": None
            }
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        
        rsi = calculate_rsi(closes)
        atr = calculate_atr(highs, lows, closes)
        upper, middle, lower = calculate_bollinger_bands(closes)
        
        direction = "NEUTRAL"
        bb_zone = "MIDDLE"
        if closes[-1] > upper: bb_zone = "UPPER"
        elif closes[-1] < lower: bb_zone = "LOWER"
        
        if rsi < 30: direction = "LONG"
        elif rsi > 70: direction = "SHORT"
        
        return {
            "direction": direction,
            "strength": abs(rsi - 50) / 50,
            "rsi": rsi,
            "bb_zone": bb_zone,
            "atr": atr
        }

class Engine4Sentiment:
    def process(self, market_data):
        if not market_data:
            return {
                "direction": None,
                "strength": None,
                "liq_proximity_score": None
            }
        return {
            "direction": "BALANCED",
            "strength": 0,
            "liq_proximity_score": 0.0
        }

class Engine5Regime:
    def process(self, klines):
        if not klines or len(klines) < 20:
            return {
                "tradeable": False,
                "regime": None,
                "spread_ok": False,
                "weight_overrides": {"e1": 0.35, "e2": 0.25, "e3": 0.20, "e4": 0.12},
                "param_overrides": {"tp_multiplier": 1.0, "sl_multiplier": 1.0, "leverage_max": 12}
            }
        return {
            "tradeable": True,
            "regime": "NORMAL_VOL",
            "spread_ok": True,
            "weight_overrides": {"e1": 0.35, "e2": 0.25, "e3": 0.20, "e4": 0.12},
            "param_overrides": {"tp_multiplier": 1.0, "sl_multiplier": 1.0, "leverage_max": 12}
        }
