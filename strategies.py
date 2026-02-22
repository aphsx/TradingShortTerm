from config import STRATA_V_RAT_TRIGGER, STRATA_STREAK_TRIGGER, STRATA_S_RAT_TRIGGER, STRATB_RSI_LOWER, STRATB_RSI_UPPER, STRATC_LIQ_PROXIMITY, STRATC_S_RAT_TRIGGER

class StrategyA:
    def evaluate(self, signals, e5_filter):
        e2 = signals.get('e2', {})
        e1 = signals.get('e1', {})
        
        v_rat = e2.get('velocity_ratio') or 0
        streak = e2.get('streak') or 0
        v_spike = e2.get('volume_spike') or False
        s_rat = e2.get('spike_ratio') or 0
        str1 = e1.get('strength') or 0
        
        # TRIGGER - Dynamic strictness for short-term scalping
        if not ((v_rat > STRATA_V_RAT_TRIGGER and streak >= STRATA_STREAK_TRIGGER and v_spike) or s_rat > STRATA_S_RAT_TRIGGER):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if v_rat > STRATA_V_RAT_TRIGGER: score += 0.4
        if streak >= (STRATA_STREAK_TRIGGER + 1): score += 0.3
        if str1 > 0.40: score += 0.2
        
        regime = e5_filter.get('regime', '')
        if regime == "TRENDING": score += 0.1
        elif regime == "RANGING": score -= 0.3
        
        return max(0, score)

class StrategyB:
    def evaluate(self, signals, e5_filter):
        e3 = signals.get('e3', {})
        e1 = signals.get('e1', {})
        
        rsi = e3.get('rsi')
        bb_zone = e3.get('bb_zone')
        str1 = e1.get('strength') or 0
        
        if rsi is None or bb_zone is None:
            return 0
            
        # TRIGGER - Dynamic RSI zones for rapid mean reversion 
        if not ((rsi < STRATB_RSI_LOWER or rsi > STRATB_RSI_UPPER) and bb_zone in ["UPPER", "LOWER"]):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if rsi < (STRATB_RSI_LOWER - 5) or rsi > (STRATB_RSI_UPPER + 5): score += 0.4
        if bb_zone in ["UPPER", "LOWER"]: score += 0.3
        if str1 > 0.30: score += 0.2
        
        phase = e5_filter.get('regime', '')
        if phase == "RANGING": score += 0.1
        elif phase == "TRENDING": score -= 0.3
        
        return max(0, score)

class StrategyC:
    def evaluate(self, signals, e5_filter):
        e4 = signals.get('e4', {})
        e2 = signals.get('e2', {})
        
        liq = e4.get('liq_proximity_score') or 0
        v_spike = e2.get('volume_spike') or False
        s_rat = e2.get('spike_ratio') or 0
        
        # TRIGGER - Dynamic liquidation proxy requirement
        if not (liq > STRATC_LIQ_PROXIMITY and (v_spike or s_rat > STRATC_S_RAT_TRIGGER)):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if liq > STRATC_LIQ_PROXIMITY: score += 0.5
        if s_rat > STRATC_S_RAT_TRIGGER: score += 0.3
        
        if liq > (STRATC_LIQ_PROXIMITY + 0.20): score += 0.2 
        
        return max(0, score)
