class StrategyA:
    def evaluate(self, signals, e5_filter):
        e2 = signals.get('e2', {})
        e1 = signals.get('e1', {})
        
        v_rat = e2.get('velocity_ratio') or 0
        streak = e2.get('streak') or 0
        v_spike = e2.get('volume_spike') or False
        s_rat = e2.get('spike_ratio') or 0
        str1 = e1.get('strength') or 0
        
        # TRIGGER
        if not ((v_rat > 2.0 and streak >= 8 and v_spike) or s_rat > 2.5):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if v_rat > 2.0: score += 0.4
        if streak >= 8: score += 0.3
        if str1 > 0.60: score += 0.2
        
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
            
        # TRIGGER
        if not ((rsi < 25 or rsi > 75) and bb_zone in ["UPPER", "LOWER"]):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if rsi < 25 or rsi > 75: score += 0.4
        if bb_zone in ["UPPER", "LOWER"]: score += 0.3
        if str1 > 0.40: score += 0.2
        
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
        
        # TRIGGER
        if not (liq > 0.70 and (v_spike or s_rat > 2.0)):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if liq > 0.70: score += 0.5
        if s_rat > 2.0: score += 0.3
        
        if liq > 0.90: score += 0.2 
        
        return max(0, score)
