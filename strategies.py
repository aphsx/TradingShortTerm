class StrategyA:
    def evaluate(self, signals):
        e2 = signals.get('e2', {})
        e1 = signals.get('e1', {})
        score = 0
        if e2.get('velocity_ratio', 0) > 2.0: score += 0.4
        if e2.get('streak', 0) >= 8: score += 0.3
        if e1.get('strength', 0) > 0.60: score += 0.2
        return score

class StrategyB:
    def evaluate(self, signals):
        e3 = signals.get('e3', {})
        e1 = signals.get('e1', {})
        score = 0
        if e3.get('rsi', 50) < 25 or e3.get('rsi', 50) > 75: score += 0.4
        if e3.get('bb_zone') in ["UPPER", "LOWER"]: score += 0.3
        if e1.get('imbalance', 0) > 0.40: score += 0.2
        return score

class StrategyC:
    def evaluate(self, signals):
        e4 = signals.get('e4', {})
        e2 = signals.get('e2', {})
        score = 0
        if e4.get('liq_proximity_score', 0) > 0.70: score += 0.5
        if e2.get('spike_ratio', 0) > 2.0: score += 0.3
        return score
