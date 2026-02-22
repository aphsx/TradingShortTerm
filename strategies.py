class StrategyA:
    def evaluate(self, signals, e5_filter):
        e2 = signals.get('e2', {})
        e1 = signals.get('e1', {})
        
        # TRIGGER
        if not (e2.get('velocity_ratio', 0) > 2.0 and e2.get('streak', 0) >= 8 and e2.get('volume_spike', False) or e2.get('spike_ratio', 0) > 2.5):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if e2.get('velocity_ratio', 0) > 2.0: score += 0.4
        if e2.get('streak', 0) >= 8: score += 0.3
        if e1.get('strength', 0) > 0.60: score += 0.2
        
        regime = e5_filter.get('regime', '')
        if regime == "TRENDING": score += 0.1
        elif regime == "RANGING": score -= 0.3
        
        return max(0, score)

class StrategyB:
    def evaluate(self, signals, e5_filter):
        e3 = signals.get('e3', {})
        e1 = signals.get('e1', {})
        
        # TRIGGER
        rsi = e3.get('rsi', 50)
        bb_zone = e3.get('bb_zone', 'MIDDLE')
        
        if not ((rsi < 25 or rsi > 75) and bb_zone in ["UPPER", "LOWER"]):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if rsi < 25 or rsi > 75: score += 0.4
        if bb_zone in ["UPPER", "LOWER"]: score += 0.3
        if e1.get('strength', 0) > 0.40: score += 0.2
        
        phase = e5_filter.get('regime', '') # using regime as phase
        if phase == "RANGING": score += 0.1
        elif phase == "TRENDING": score -= 0.3
        
        return max(0, score)

class StrategyC:
    def evaluate(self, signals, e5_filter):
        e4 = signals.get('e4', {})
        e2 = signals.get('e2', {})
        
        # TRIGGER
        if not (e4.get('liq_proximity_score', 0) > 0.70 and (e2.get('volume_spike', False) or e2.get('spike_ratio', 0) > 2.0)):
            return 0
            
        score = 0.0
        score += 0.4 # Base qualifying
        
        if e4.get('liq_proximity_score', 0) > 0.70: score += 0.5
        if e2.get('spike_ratio', 0) > 2.0: score += 0.3
        
        # Simple proximity check as placeholder for oi interpretation
        if e4.get('liq_proximity_score', 0) > 0.90: score += 0.2 
        
        return max(0, score)
