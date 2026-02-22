from utils import calculate_imbalance, calculate_rsi, calculate_atr, calculate_atr_array, calculate_bollinger_bands, calculate_adx, calculate_percentiles, calculate_vpin
from config import E1_IMBALANCE_THRESHOLD, E2_MOMENTUM_THRESHOLD, E4_FUNDING_RATE_THRESHOLD

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
                "micro_price": None,
                "vpin": 0.0
            }

        imbalance = calculate_imbalance(bids, asks)

        # Calculate VPIN for predictive signal (0.5-2s ahead)
        vpin = calculate_vpin(ticks, volume_bucket_size=50, num_buckets=5)

        direction = "NEUTRAL"
        if imbalance > E1_IMBALANCE_THRESHOLD: direction = "BUY_PRESSURE" # Aggressively catch micro liquidity imbalances
        elif imbalance < -E1_IMBALANCE_THRESHOLD: direction = "SELL_PRESSURE"

        # Boost conviction if VPIN is high (informed trading detected)
        conviction = abs(imbalance)
        if vpin > 0.5:  # High informed trading activity
            conviction = min(1.0, conviction * 1.3)  # 30% boost

        return {
            "direction": direction,
            "strength": abs(imbalance),
            "conviction": conviction,
            "imbalance": imbalance,
            "cvd_slope": 0,
            "micro_price": (float(bids[0][0])*float(asks[0][1]) + float(asks[0][0])*float(bids[0][1]))/(float(bids[0][1])+float(asks[0][1])) if bids and asks else 0,
            "vpin": vpin
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
        if aggressor_ratio > E2_MOMENTUM_THRESHOLD: direction = "MOMENTUM_LONG" # Hair-trigger momentum
        elif aggressor_ratio < (1.0 - E2_MOMENTUM_THRESHOLD): direction = "MOMENTUM_SHORT"
        
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
                "liq_proximity_score": None,
                "oi_interpretation": None,
                "funding_signal": None
            }
            
        ls_ratio = market_data.get('ls_ratio', 1.0)
        funding_rate = market_data.get('funding_rate', 0.0)
        long_pct = market_data.get('long_account_pct', 0.5)
        top_long = market_data.get('top_trader_long_pct', 0.5)
        
        direction = "BALANCED"
        strength = 0.0
        
        # Long/Short Ratio Contrarion Logic
        if long_pct > 0.70:
            direction = "CROWD_LONG" # Bias Short
            strength += 0.4
        elif long_pct < 0.35: # Equivalent to Short > 65%
            direction = "CROWD_SHORT" # Bias Long
            strength += 0.4
            
        # Funding Rate
        funding_signal = "NEUTRAL"
        if funding_rate > E4_FUNDING_RATE_THRESHOLD: # React to mild expensive funding
            funding_signal = "LONGS_EXPENSIVE"
            if direction == "CROWD_LONG": strength += 0.3
        elif funding_rate < -E4_FUNDING_RATE_THRESHOLD: # React to mild shorts compression
            funding_signal = "SHORTS_EXPENSIVE"
            if direction == "CROWD_SHORT": strength += 0.3
            
        # Top Trader Logic (Smart Money vs Retail)
        if top_long > 0.60 and direction == "CROWD_SHORT":
            strength += 0.3 # Smart money long, crowd short
        elif top_long < 0.40 and direction == "CROWD_LONG":
            strength += 0.3 # Smart money short, crowd long
            
        # Placeholder for complex Liquidation Map, use OI proxy for activity
        oi = market_data.get("open_interest", 0)
        liq_prox = 0.0
        # Would require keeping historical OI to map 'change_pct', returning static proxy for testing
        if oi > 0: liq_prox = min(0.5, (abs(funding_rate) * 1000)) 
            
        return {
            "direction": direction,
            "strength": min(1.0, strength),
            "liq_proximity_score": liq_prox,
            "oi_interpretation": "UNKNOWN",
            "funding_signal": funding_signal
        }

class Engine5Regime:
    def process(self, klines):
        if not klines or len(klines) < 30:
            return {
                "tradeable": False,
                "regime": None,
                "vol_phase": None,
                "spread_ok": False,
                "weight_overrides": {"e1": 0.35, "e2": 0.25, "e3": 0.20, "e4": 0.12},
                "param_overrides": {"tp_multiplier": 1.0, "sl_multiplier": 1.0, "leverage_max": 12}
            }
            
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        
        current_price = closes[-1]
        
        # 1. Volatility Phase (ATR as % of price)
        atr_array = calculate_atr_array(highs, lows, closes, 14)
        
        if not atr_array or len(atr_array) < 50:
            # Fallback to static if not enough history
            atr_14 = calculate_atr(highs, lows, closes, 14)
            atr_pct = (atr_14 / current_price) if current_price else 0
            vol_phase = "NORMAL_VOL"
            if atr_pct < 0.0015: vol_phase = "LOW_VOL" # Less than 0.15% move per 15m candle
            elif atr_pct > 0.008: vol_phase = "EXTREME_VOL" # > 0.8% move per 15m candle
            elif atr_pct > 0.005: vol_phase = "HIGH_VOL" # > 0.5% move per 15m candle
        else:
            # Calculate historical ATR%
            atr_pct_history = []
            offset = len(closes) - len(atr_array)
            for i in range(len(atr_array)):
                c = closes[offset + i]
                if c > 0:
                    atr_pct_history.append(atr_array[i] / c)
            
            percentiles = calculate_percentiles(atr_pct_history, [25, 75, 90])
            p25, p75, p90 = percentiles.get(25, 0), percentiles.get(75, 0), percentiles.get(90, 0)
            
            atr_pct = atr_pct_history[-1] if atr_pct_history else 0
            
            vol_phase = "NORMAL_VOL"
            # Prevent zero-division/empty flatlines
            if p90 > 0:
                if atr_pct < p25: vol_phase = "LOW_VOL"
                elif atr_pct > p90: vol_phase = "EXTREME_VOL"
                elif atr_pct > p75: vol_phase = "HIGH_VOL"
        
        # 2. Trend Regime (ADX)
        adx_14 = calculate_adx(highs, lows, closes, 14)
        
        regime = "RANGING"
        if adx_14 < 20: regime = "CHOPPY"
        elif adx_14 > 25: regime = "TRENDING"
        
        # 3. Tradeability & Spread Proxy
        # If High/Low diff of current candle is 0 (stale data), spread might be bad
        spread_proxy_pct = (highs[-1] - lows[-1]) / current_price if current_price else 0
        spread_ok = spread_proxy_pct < 0.002 # Assume spread is ok if 3m range isn't inexplicably vast
        
        # Removed CHOPPY from the hardware trade-block for short term scalping
        tradeable = True
        if vol_phase == "EXTREME_VOL":
            tradeable = False
            
        # 4. Dynamic Weight Setup
        weights = {"e1": 0.35, "e2": 0.25, "e3": 0.20, "e4": 0.12}
        params = {"tp_multiplier": 0.8, "sl_multiplier": 1.0, "leverage_max": 20} # Aggressive short-term scalping params
        
        if regime == "TRENDING":
            weights = {"e1": 0.40, "e2": 0.30, "e3": 0.10, "e4": 0.10} # Favor momentum
            params["tp_multiplier"] = 1.0 # Let winners run a bit more
            
        elif regime == "RANGING" or regime == "CHOPPY":
            weights = {"e1": 0.15, "e2": 0.25, "e3": 0.45, "e4": 0.15} # Favor oscillators heavily for mean reversion
            params["tp_multiplier"] = 0.5 # Take very quick profits
            
        if vol_phase == "HIGH_VOL":
            params["sl_multiplier"] = 1.5 # Widen SL to avoid wicks
            params["leverage_max"] = 5 # Reduce risk
            
        return {
            "tradeable": tradeable,
            "regime": regime,
            "vol_phase": vol_phase,
            "spread_ok": spread_ok,
            "weight_overrides": weights,
            "param_overrides": params
        }
