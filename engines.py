from utils import calculate_imbalance, calculate_rsi, calculate_atr, calculate_atr_array, calculate_bollinger_bands, calculate_adx, calculate_percentiles, calculate_vpin, calculate_depth_imbalance_multi, calculate_macd, calculate_keltner_channels
from config import E1_IMBALANCE_THRESHOLD, E2_MOMENTUM_THRESHOLD, E4_FUNDING_RATE_THRESHOLD
from logger_config import get_logger

logger = get_logger(__name__)

class Engine1OrderFlow:
    def __init__(self):
        # Track imbalance history for velocity calculation
        self.imbalance_history = {}  # {symbol: [(timestamp, imbalance), ...]}
        self.max_history_size = 50  # Keep last 50 snapshots (~10 seconds at 200ms intervals)
        self.last_access_time = {}  # Track last access per symbol for cleanup
        self.cleanup_threshold_seconds = 300  # Remove symbols not accessed for 5 minutes

    def _cleanup_stale_symbols(self):
        """Remove symbols that haven't been accessed recently to prevent memory leak"""
        import time
        current_time = time.time()
        stale_symbols = [
            sym for sym, last_time in self.last_access_time.items()
            if current_time - last_time > self.cleanup_threshold_seconds
        ]

        for sym in stale_symbols:
            if sym in self.imbalance_history:
                del self.imbalance_history[sym]
            if sym in self.last_access_time:
                del self.last_access_time[sym]

        if stale_symbols:
            logger.debug(f"Engine1 cleaned up {len(stale_symbols)} stale symbols: {stale_symbols}")

    def _update_imbalance_history(self, symbol, imbalance):
        """Track imbalance over time to calculate velocity"""
        import time
        timestamp = time.time()

        if symbol not in self.imbalance_history:
            self.imbalance_history[symbol] = []

        self.imbalance_history[symbol].append((timestamp, imbalance))
        self.last_access_time[symbol] = timestamp  # Track access for cleanup

        # Keep only recent history
        if len(self.imbalance_history[symbol]) > self.max_history_size:
            self.imbalance_history[symbol].pop(0)

        # Periodic cleanup (every ~100 calls to avoid overhead)
        if len(self.imbalance_history) > 20 and timestamp % 100 < 1:
            self._cleanup_stale_symbols()

    def _calculate_ofi_velocity(self, symbol, window_seconds=0.3):
        """
        Calculate Order Flow Imbalance velocity (rate of change)

        Research shows velocity is more predictive than static imbalance.
        High velocity indicates momentum building → price likely to follow.

        Args:
            symbol: Trading pair symbol
            window_seconds: Time window to calculate velocity (default 300ms)

        Returns:
            float: Velocity score (can be positive or negative)
        """
        if symbol not in self.imbalance_history or len(self.imbalance_history[symbol]) < 2:
            return 0.0

        import time
        current_time = time.time()
        history = self.imbalance_history[symbol]

        # Find data points within the window
        cutoff_time = current_time - window_seconds
        recent_points = [p for p in history if p[0] >= cutoff_time]

        if len(recent_points) < 2:
            return 0.0

        # Calculate velocity: change in imbalance / time elapsed
        oldest = recent_points[0]
        newest = recent_points[-1]

        time_delta = newest[0] - oldest[0]
        if time_delta == 0:
            return 0.0

        imbalance_delta = newest[1] - oldest[1]
        velocity = imbalance_delta / time_delta

        return velocity

    def process(self, orderbook, ticks, symbol="UNKNOWN"):
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if not bids or not asks:
            return {
                "direction": None,
                "strength": None,
                "conviction": None,
                "imbalance": None,
                "depth_imbalance": None,
                "ofi_velocity": 0.0,
                "cvd_slope": None,
                "micro_price": None,
                "vpin": 0.0
            }

        # Multi-level depth imbalance for better liquidity structure detection
        depth_data = calculate_depth_imbalance_multi(bids, asks)
        imbalance = depth_data['imbalance_weighted']  # Use weighted average as primary

        # Update history and calculate OFI velocity (predictive!)
        self._update_imbalance_history(symbol, imbalance)
        ofi_velocity = self._calculate_ofi_velocity(symbol, window_seconds=0.3)

        # Calculate VPIN for predictive signal (0.5-2s ahead)
        vpin = calculate_vpin(ticks, volume_bucket_size=50, num_buckets=5)

        direction = "NEUTRAL"
        if imbalance > E1_IMBALANCE_THRESHOLD: direction = "BUY_PRESSURE" # Aggressively catch micro liquidity imbalances
        elif imbalance < -E1_IMBALANCE_THRESHOLD: direction = "SELL_PRESSURE"

        # Boost conviction if VPIN is high (informed trading detected)
        conviction = abs(imbalance)
        if vpin > 0.5:  # High informed trading activity
            conviction = min(1.0, conviction * 1.3)  # 30% boost

        # Boost conviction if OFI velocity is high (momentum building)
        # Velocity > 2.0 means imbalance changing rapidly → price likely to follow
        if abs(ofi_velocity) > 2.0:
            conviction = min(1.0, conviction * 1.25)  # 25% boost

        # Additional conviction boost if all depth levels align
        if abs(depth_data['imbalance_L5']) > E1_IMBALANCE_THRESHOLD and \
           abs(depth_data['imbalance_L10']) > E1_IMBALANCE_THRESHOLD and \
           abs(depth_data['imbalance_L20']) > E1_IMBALANCE_THRESHOLD:
            # All depths showing same direction = strong liquidity structure
            conviction = min(1.0, conviction * 1.2)  # 20% boost

        return {
            "direction": direction,
            "strength": abs(imbalance),
            "conviction": conviction,
            "imbalance": imbalance,
            "depth_imbalance": depth_data,  # Full depth structure for analysis
            "ofi_velocity": ofi_velocity,  # Rate of change of imbalance
            "cvd_slope": 0,
            "micro_price": (float(bids[0][0])*float(asks[0][1]) + float(asks[0][0])*float(bids[0][1]))/(float(bids[0][1])+float(asks[0][1])) if bids and asks else 0,
            "vpin": vpin
        }

class Engine2Tick:
    def __init__(self):
        # Track tick history for multi-timeframe analysis
        self.tick_history = {}  # {symbol: [(timestamp, tick_data), ...]}
        self.max_history_seconds = 20  # Keep 20 seconds of history
        self.last_access_time = {}  # Track last access per symbol for cleanup
        self.cleanup_threshold_seconds = 300  # Remove symbols not accessed for 5 minutes

    def _cleanup_stale_symbols(self):
        """Remove symbols that haven't been accessed recently to prevent memory leak"""
        import time
        current_time = time.time()
        stale_symbols = [
            sym for sym, last_time in self.last_access_time.items()
            if current_time - last_time > self.cleanup_threshold_seconds
        ]

        for sym in stale_symbols:
            if sym in self.tick_history:
                del self.tick_history[sym]
            if sym in self.last_access_time:
                del self.last_access_time[sym]

        if stale_symbols:
            logger.debug(f"Engine2 cleaned up {len(stale_symbols)} stale symbols: {stale_symbols}")

    def _update_tick_history(self, symbol, ticks):
        """Store ticks with timestamps for multi-timeframe analysis"""
        import time
        current_time = time.time()

        if symbol not in self.tick_history:
            self.tick_history[symbol] = []

        # Add new ticks with timestamps
        for tick in ticks:
            self.tick_history[symbol].append((current_time, tick))

        self.last_access_time[symbol] = current_time  # Track access for cleanup

        # Clean old data
        cutoff = current_time - self.max_history_seconds
        self.tick_history[symbol] = [
            (ts, t) for ts, t in self.tick_history[symbol] if ts >= cutoff
        ]

        # Periodic cleanup (every ~100 calls to avoid overhead)
        if len(self.tick_history) > 20 and current_time % 100 < 1:
            self._cleanup_stale_symbols()

    def _calculate_aggressor_ratio(self, ticks):
        """Calculate buy/sell aggressor ratio from tick data"""
        if not ticks:
            return 0.5

        buy_vol = sum(float(t.get('q', 0)) for t in ticks if not t.get('m', False))
        sell_vol = sum(float(t.get('q', 0)) for t in ticks if t.get('m', False))

        return buy_vol / (buy_vol + sell_vol) if (buy_vol + sell_vol) > 0 else 0.5

    def _get_ticks_in_window(self, symbol, window_seconds):
        """Get ticks within specified time window"""
        if symbol not in self.tick_history:
            return []

        import time
        cutoff = time.time() - window_seconds
        return [t for ts, t in self.tick_history[symbol] if ts >= cutoff]

    def _calculate_alignment_score(self, ratios):
        """
        Calculate how aligned multiple timeframes are.

        When all timeframes show the same direction (all > 0.55 or all < 0.45),
        it indicates strong, building momentum.

        Args:
            ratios: List of aggressor ratios from different timeframes

        Returns:
            float: Alignment score (0-1), 1 = perfect alignment
        """
        if not ratios or len(ratios) < 2:
            return 0.0

        # Check if all bullish (> 0.55) or all bearish (< 0.45)
        all_bullish = all(r > 0.55 for r in ratios)
        all_bearish = all(r < 0.45 for r in ratios)

        if all_bullish or all_bearish:
            # Calculate how far from neutral (0.5) on average
            avg_deviation = sum(abs(r - 0.5) for r in ratios) / len(ratios)
            return min(1.0, avg_deviation * 2)  # Scale to 0-1

        return 0.0

    def process(self, ticks, symbol="UNKNOWN"):
        if not ticks:
            return {
                "direction": None,
                "strength": None,
                "velocity_ratio": None,
                "aggressor_ratio": None,
                "aggressor_1s": None,
                "aggressor_5s": None,
                "aggressor_15s": None,
                "alignment": 0.0,
                "streak": None,
                "volume_spike": None,
                "spike_ratio": None
            }

        # Update history for multi-timeframe analysis
        self._update_tick_history(symbol, ticks)

        # Calculate aggressor ratios at multiple timeframes
        ticks_1s = self._get_ticks_in_window(symbol, window_seconds=1)
        ticks_5s = self._get_ticks_in_window(symbol, window_seconds=5)
        ticks_15s = self._get_ticks_in_window(symbol, window_seconds=15)

        aggressor_1s = self._calculate_aggressor_ratio(ticks_1s)
        aggressor_5s = self._calculate_aggressor_ratio(ticks_5s)
        aggressor_15s = self._calculate_aggressor_ratio(ticks_15s)

        # Use 5s window as primary (balanced between noise and lag)
        aggressor_ratio = aggressor_5s

        # Calculate alignment across timeframes
        alignment = self._calculate_alignment_score([aggressor_1s, aggressor_5s, aggressor_15s])

        direction = "NEUTRAL"
        if aggressor_ratio > E2_MOMENTUM_THRESHOLD: direction = "MOMENTUM_LONG"
        elif aggressor_ratio < (1.0 - E2_MOMENTUM_THRESHOLD): direction = "MOMENTUM_SHORT"

        # Strength boosted by alignment
        base_strength = abs(aggressor_ratio - 0.5) * 2
        strength = min(1.0, base_strength * (1 + alignment * 0.5))  # Up to 50% boost

        # === ACTUAL velocity_ratio calculation ===
        # Compare 1s aggressor ratio change rate vs 5s baseline
        # velocity_ratio > 1 means short-term momentum accelerating
        if aggressor_5s != 0.5 and abs(aggressor_5s - 0.5) > 0.01:
            velocity_ratio = abs(aggressor_1s - 0.5) / abs(aggressor_5s - 0.5)
        else:
            velocity_ratio = 1.0

        # === ACTUAL streak calculation ===
        # Count consecutive ticks in the same direction (buy or sell)
        streak = 0
        if ticks_1s:
            last_side = ticks_1s[0].get('m', False)
            current_streak = 1
            for tick in ticks_1s[1:]:
                if tick.get('m', False) == last_side:
                    current_streak += 1
                else:
                    break
            streak = current_streak

        # === ACTUAL volume_spike detection ===
        # Compare current 1s volume vs rolling 15s average per second
        import numpy as np
        vol_1s = sum(float(t.get('q', 0)) for t in ticks_1s)
        vol_15s = sum(float(t.get('q', 0)) for t in ticks_15s)
        avg_vol_per_sec = vol_15s / 15.0 if ticks_15s else 0

        # spike_ratio = current 1s volume / average 1s volume
        spike_ratio = vol_1s / avg_vol_per_sec if avg_vol_per_sec > 0 else 1.0

        # Volume spike = current volume > 2 standard deviations above mean
        # Simplified: spike when ratio > 2.0x average
        volume_spike = spike_ratio > 2.0

        return {
            "direction": direction,
            "strength": strength,
            "velocity_ratio": velocity_ratio,
            "aggressor_ratio": aggressor_ratio,
            "aggressor_1s": aggressor_1s,
            "aggressor_5s": aggressor_5s,
            "aggressor_15s": aggressor_15s,
            "alignment": alignment,
            "streak": streak,
            "volume_spike": volume_spike,
            "spike_ratio": spike_ratio
        }

class Engine3Technical:
    def process(self, klines):
        if not klines or len(klines) < 20:
            return {
                "direction": None, 
                "strength": None, 
                "atr": None, 
                "bb_zone": None, 
                "rsi": None,
                "macd_histogram": None,
                "squeeze": False,
                "trend_strength": 0.0
            }
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        
        rsi = calculate_rsi(closes)
        atr = calculate_atr(highs, lows, closes)
        upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(closes)
        
        # MACD for trend momentum confirmation
        macd_line, signal_line, histogram = calculate_macd(closes, fast=12, slow=26, signal=9)
        
        # Keltner Channels for squeeze detection
        upper_kc, middle_kc, lower_kc = calculate_keltner_channels(highs, lows, closes)
        
        # === Squeeze Detection ===
        # When BB contracts inside KC, volatility is compressed
        # Breakout from squeeze = high-probability directional move
        import numpy as np
        squeeze = False
        if not any(np.isnan(x) for x in [upper_bb, lower_bb, upper_kc, lower_kc] if x is not None):
            squeeze = (upper_bb < upper_kc) and (lower_bb > lower_kc)
        
        # === Multi-indicator Direction ===
        direction = "NEUTRAL"
        bb_zone = "MIDDLE"
        trend_score = 0.0  # -1 (bearish) to +1 (bullish)
        
        # Bollinger Band zone
        if not np.isnan(upper_bb) and not np.isnan(lower_bb):
            if closes[-1] > upper_bb: bb_zone = "UPPER"
            elif closes[-1] < lower_bb: bb_zone = "LOWER"
        
        # RSI contribution
        if rsi < 30:
            trend_score += 0.4   # Oversold = bullish reversal signal
        elif rsi < 40:
            trend_score += 0.2
        elif rsi > 70:
            trend_score -= 0.4   # Overbought = bearish reversal signal
        elif rsi > 60:
            trend_score -= 0.2
        
        # MACD contribution (momentum confirmation)
        if not np.isnan(histogram):
            if histogram > 0:
                trend_score += min(0.3, histogram / (atr if atr and atr > 0 else 1) * 10)
            else:
                trend_score -= min(0.3, abs(histogram) / (atr if atr and atr > 0 else 1) * 10)
        
        # Squeeze contribution (amplifies signal)
        if squeeze:
            # In squeeze, MACD direction predicts breakout direction
            if not np.isnan(histogram):
                if histogram > 0:
                    trend_score += 0.2  # Bullish squeeze breakout
                else:
                    trend_score -= 0.2  # Bearish squeeze breakout
        
        # Final direction decision
        if trend_score > 0.15:
            direction = "LONG"
        elif trend_score < -0.15:
            direction = "SHORT"
        
        # Strength is absolute trend_score normalized
        strength = min(1.0, abs(trend_score))
        
        return {
            "direction": direction,
            "strength": strength,
            "rsi": rsi,
            "bb_zone": bb_zone,
            "atr": atr,
            "macd_histogram": histogram if not np.isnan(histogram) else 0.0,
            "squeeze": squeeze,
            "trend_strength": trend_score
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
                "adx": 0,
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
            atr_14 = calculate_atr(highs, lows, closes, 14)
            atr_pct = (atr_14 / current_price) if current_price else 0
            vol_phase = "NORMAL_VOL"
            if atr_pct < 0.0015: vol_phase = "LOW_VOL"
            elif atr_pct > 0.008: vol_phase = "EXTREME_VOL"
            elif atr_pct > 0.005: vol_phase = "HIGH_VOL"
        else:
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
            if p90 > 0:
                if atr_pct < p25: vol_phase = "LOW_VOL"
                elif atr_pct > p90: vol_phase = "EXTREME_VOL"
                elif atr_pct > p75: vol_phase = "HIGH_VOL"
        
        # 2. Trend Regime (ADX — now properly calculated with Wilder's smoothing)
        adx_14 = calculate_adx(highs, lows, closes, 14)
        import numpy as np
        if np.isnan(adx_14):
            adx_14 = 0
        
        # Granular regime detection
        regime = "RANGING"
        if adx_14 < 15: regime = "CHOPPY"
        elif adx_14 < 25: regime = "RANGING"
        elif adx_14 < 40: regime = "TRENDING"
        else: regime = "STRONG_TREND"
        
        # 3. Tradeability & Spread Proxy
        spread_proxy_pct = (highs[-1] - lows[-1]) / current_price if current_price else 0
        spread_ok = spread_proxy_pct < 0.002
        
        tradeable = True
        if vol_phase == "EXTREME_VOL":
            tradeable = False
            
        # 4. Dynamic Weight & Parameter Matrix
        # Each regime gets optimized weights and params
        weights = {"e1": 0.35, "e2": 0.25, "e3": 0.20, "e4": 0.12}
        params = {"tp_multiplier": 0.8, "sl_multiplier": 1.0, "leverage_max": 20}
        
        if regime == "STRONG_TREND":
            weights = {"e1": 0.45, "e2": 0.30, "e3": 0.05, "e4": 0.10}
            params["tp_multiplier"] = 1.5   # Let winners run
            params["sl_multiplier"] = 0.8   # Tighter SL (trend protects)
            params["leverage_max"] = 25
            
        elif regime == "TRENDING":
            weights = {"e1": 0.40, "e2": 0.30, "e3": 0.10, "e4": 0.10}
            params["tp_multiplier"] = 1.0
            params["leverage_max"] = 20
            
        elif regime == "RANGING":
            weights = {"e1": 0.15, "e2": 0.20, "e3": 0.45, "e4": 0.15}
            params["tp_multiplier"] = 0.6
            params["leverage_max"] = 15
            
        elif regime == "CHOPPY":
            weights = {"e1": 0.10, "e2": 0.20, "e3": 0.50, "e4": 0.15}
            params["tp_multiplier"] = 0.4   # Very quick profits
            params["sl_multiplier"] = 0.7   # Tight SL in chop
            params["leverage_max"] = 12
        
        # Volatility-specific overrides
        if vol_phase == "HIGH_VOL":
            params["sl_multiplier"] = max(params["sl_multiplier"], 1.5)
            params["leverage_max"] = min(params["leverage_max"], 10)
            
        elif vol_phase == "LOW_VOL":
            # Low volatility = safe to size up
            params["leverage_max"] = min(30, params["leverage_max"] + 5)
            params["sl_multiplier"] = max(0.6, params["sl_multiplier"] - 0.2)
            
        return {
            "tradeable": tradeable,
            "regime": regime,
            "vol_phase": vol_phase,
            "spread_ok": spread_ok,
            "adx": adx_14,
            "weight_overrides": weights,
            "param_overrides": params
        }
