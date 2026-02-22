from config import STRATA_V_RAT_TRIGGER, STRATA_STREAK_TRIGGER, STRATA_S_RAT_TRIGGER, STRATB_RSI_LOWER, STRATB_RSI_UPPER, STRATC_LIQ_PROXIMITY, STRATC_S_RAT_TRIGGER

class StrategyA:
    """
    Momentum Breakout Strategy.
    
    Triggers on:
    - Velocity ratio acceleration (1s momentum > 5s baseline)
    - Consecutive same-direction ticks (streak)
    - Volume spikes (unusual volume = institutional flow)
    
    Best in: TRENDING / STRONG_TREND regimes
    """
    def evaluate(self, signals, e5_filter):
        e2 = signals.get('e2', {})
        e1 = signals.get('e1', {})
        e3 = signals.get('e3', {})
        
        v_rat = e2.get('velocity_ratio') or 0
        streak = e2.get('streak') or 0
        v_spike = e2.get('volume_spike') or False
        s_rat = e2.get('spike_ratio') or 0
        str1 = e1.get('strength') or 0
        alignment = e2.get('alignment') or 0
        
        # TRIGGER: Need either momentum acceleration + streak + spike,
        # OR massive volume spike alone
        if not ((v_rat > STRATA_V_RAT_TRIGGER and streak >= STRATA_STREAK_TRIGGER and v_spike) or s_rat > STRATA_S_RAT_TRIGGER):
            return 0
            
        score = 0.0
        score += 0.35  # Base qualifying
        
        # Momentum acceleration scoring
        if v_rat > STRATA_V_RAT_TRIGGER: score += 0.25
        if v_rat > STRATA_V_RAT_TRIGGER * 1.5: score += 0.15  # Very strong acceleration
        
        # Streak scoring (consecutive same-direction trades)
        if streak >= STRATA_STREAK_TRIGGER: score += 0.15
        if streak >= (STRATA_STREAK_TRIGGER + 3): score += 0.15  # Extended streak
        
        # Volume spike scoring
        if v_spike: score += 0.1
        if s_rat > STRATA_S_RAT_TRIGGER: score += 0.15
        
        # Order flow confirmation
        if str1 > 0.30: score += 0.15
        
        # Multi-timeframe alignment bonus
        if alignment > 0.5: score += 0.2
        
        # Squeeze breakout bonus (MACD + BB inside KC)
        if e3.get('squeeze', False): score += 0.25
        
        # Regime adjustment
        regime = e5_filter.get('regime', '')
        if regime == "STRONG_TREND": score += 0.15
        elif regime == "TRENDING": score += 0.1
        elif regime == "RANGING": score -= 0.2
        elif regime == "CHOPPY": score -= 0.3
        
        return max(0, min(1.5, score))


class StrategyB:
    """
    Mean Reversion Strategy.
    
    Triggers on:
    - RSI extremes (oversold/overbought)
    - Bollinger Band violations (price outside bands)
    - MACD histogram divergence
    
    Best in: RANGING / CHOPPY regimes
    """
    def evaluate(self, signals, e5_filter):
        e3 = signals.get('e3', {})
        e1 = signals.get('e1', {})
        
        rsi = e3.get('rsi')
        bb_zone = e3.get('bb_zone')
        str1 = e1.get('strength') or 0
        macd_hist = e3.get('macd_histogram') or 0
        trend_strength = e3.get('trend_strength') or 0
        
        if rsi is None or bb_zone is None:
            return 0
            
        # TRIGGER: RSI extreme + BB violation
        if not ((rsi < STRATB_RSI_LOWER or rsi > STRATB_RSI_UPPER) and bb_zone in ["UPPER", "LOWER"]):
            return 0
            
        score = 0.0
        score += 0.35  # Base qualifying
        
        # RSI extremity scoring
        if rsi < (STRATB_RSI_LOWER - 5) or rsi > (STRATB_RSI_UPPER + 5): score += 0.3
        if rsi < (STRATB_RSI_LOWER - 10) or rsi > (STRATB_RSI_UPPER + 10): score += 0.2
        
        # BB zone confirmation
        if bb_zone in ["UPPER", "LOWER"]: score += 0.2
        
        # MACD divergence (histogram opposing BB zone = reversal signal)
        if bb_zone == "UPPER" and macd_hist < 0: score += 0.2  # Price high but momentum fading
        elif bb_zone == "LOWER" and macd_hist > 0: score += 0.2  # Price low but momentum building
        
        # Order flow support
        if str1 > 0.25: score += 0.15
        
        # Regime adjustment
        phase = e5_filter.get('regime', '')
        if phase == "RANGING": score += 0.15
        elif phase == "CHOPPY": score += 0.1
        elif phase == "TRENDING": score -= 0.2
        elif phase == "STRONG_TREND": score -= 0.4  # Don't fade strong trends
        
        return max(0, min(1.5, score))


class StrategyC:
    """
    Liquidation Scalp Strategy.
    
    Triggers on:
    - High liquidation proximity (OI + funding rate proxy)
    - Volume spikes (cascading liquidations)
    
    Best in: Any regime with high funding rate
    """
    def evaluate(self, signals, e5_filter):
        e4 = signals.get('e4', {})
        e2 = signals.get('e2', {})
        e1 = signals.get('e1', {})
        
        liq = e4.get('liq_proximity_score') or 0
        v_spike = e2.get('volume_spike') or False
        s_rat = e2.get('spike_ratio') or 0
        funding_signal = e4.get('funding_signal', 'NEUTRAL')
        str1 = e1.get('strength') or 0
        
        # TRIGGER: High liquidation proximity + volume confirmation
        if not (liq > STRATC_LIQ_PROXIMITY and (v_spike or s_rat > STRATC_S_RAT_TRIGGER)):
            return 0
            
        score = 0.0
        score += 0.35  # Base qualifying
        
        # Liquidation proximity scoring
        if liq > STRATC_LIQ_PROXIMITY: score += 0.3
        if liq > (STRATC_LIQ_PROXIMITY + 0.15): score += 0.2
        if liq > (STRATC_LIQ_PROXIMITY + 0.30): score += 0.15
        
        # Volume confirmation
        if s_rat > STRATC_S_RAT_TRIGGER: score += 0.2
        if v_spike: score += 0.1
        
        # Funding rate confluence (expensive longs/shorts = liquidation fuel)
        if funding_signal in ["LONGS_EXPENSIVE", "SHORTS_EXPENSIVE"]: score += 0.2
        
        # Order flow support
        if str1 > 0.30: score += 0.1
        
        return max(0, min(1.5, score))
