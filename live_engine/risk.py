"""
risk.py — Risk Management & Circuit Breakers (The Shield).
Dynamic position sizing + hard circuit breakers.
"""

import time
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Dynamic Position Sizing
# ─────────────────────────────────────────────────────────────────────

def dynamic_position_size(
    balance: float,
    atr: float,
    price: float,
    risk_pct: float = 0.01,
    sl_atr_mult: float = 2.0,
    max_position_pct: float = 0.25,
    leverage: int = 10,
) -> float:
    """
    Risk-based position sizing.
    Size = (Balance × Risk%) / (ATR × SL_multiplier)
    Capped at max_position_pct of leveraged balance.
    """
    if atr <= 0 or price <= 0:
        return 0.0
    risk_amount = balance * risk_pct
    stop_distance = atr * sl_atr_mult
    if stop_distance <= 0:
        return 0.0
    raw_qty = risk_amount / stop_distance
    max_qty = (balance * max_position_pct * leverage) / price
    qty = min(raw_qty, max_qty)
    # Round to 3 decimals (Binance BTC precision)
    return round(qty, 3)


def kelly_position_size(
    balance: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
    max_risk_pct: float = 0.02,
) -> float:
    """
    Fractional Kelly Criterion position sizing.
    f* = (p * b - q) / b  where p=win_rate, q=1-p, b=avg_win/avg_loss
    Uses `fraction` of Kelly (default 25%) for safety.
    """
    if avg_loss <= 0 or win_rate <= 0:
        return 0.0
    b = avg_win / avg_loss
    q = 1.0 - win_rate
    kelly_f = (win_rate * b - q) / b
    kelly_f = max(0.0, min(1.0, kelly_f)) * fraction
    risk_amount = balance * min(kelly_f, max_risk_pct)
    return risk_amount


# ─────────────────────────────────────────────────────────────────────
# Circuit Breaker System
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CircuitBreakerState:
    daily_pnl: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0
    peak_balance: float = 0.0
    current_balance: float = 0.0
    session_start_ts: float = 0.0
    latency_samples: list = None  # rolling latency window

    def __post_init__(self):
        if self.latency_samples is None:
            self.latency_samples = []

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return sum(self.latency_samples[-50:]) / len(self.latency_samples[-50:])


class CircuitBreaker:
    """
    Hard circuit breakers that halt all trading when triggered.
    Must be checked BEFORE every new order submission.
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 0.03,
        max_drawdown_pct: float = 0.10,
        max_consecutive_losses: int = 5,
        max_daily_trades: int = 50,
        max_latency_ms: float = 500.0,
    ):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_trades = max_daily_trades
        self.max_latency_ms = max_latency_ms
        self.state = CircuitBreakerState()
        self._halted = False
        self._halt_reason = ""

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def check(self) -> tuple[bool, str]:
        """Returns (can_trade, reason). Call before every entry."""
        s = self.state

        # 1. Daily loss limit
        if s.peak_balance > 0:
            daily_loss = -s.daily_pnl / s.peak_balance
            if daily_loss >= self.max_daily_loss_pct:
                return self._halt(f"DAILY_LOSS:{daily_loss:.1%}")

        # 2. Max drawdown from peak
        if s.peak_balance > 0 and s.current_balance > 0:
            dd = (s.peak_balance - s.current_balance) / s.peak_balance
            if dd >= self.max_drawdown_pct:
                return self._halt(f"MAX_DD:{dd:.1%}")

        # 3. Consecutive losses
        if s.consecutive_losses >= self.max_consecutive_losses:
            return self._halt(f"STREAK:{s.consecutive_losses}")

        # 4. Daily trade count
        if s.daily_trades >= self.max_daily_trades:
            return self._halt(f"TRADE_LIMIT:{s.daily_trades}")

        # 5. Latency degradation
        if s.avg_latency_ms > self.max_latency_ms:
            return self._halt(f"LATENCY:{s.avg_latency_ms:.0f}ms")

        self._halted = False
        self._halt_reason = ""
        return True, "OK"

    def _halt(self, reason: str) -> tuple[bool, str]:
        self._halted = True
        self._halt_reason = reason
        logger.critical(f"[CIRCUIT BREAKER] HALTED: {reason}")
        return False, reason

    def record_trade(self, pnl: float):
        """Call after every trade close."""
        self.state.daily_pnl += pnl
        self.state.daily_trades += 1
        if pnl > 0:
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1

    def update_balance(self, balance: float):
        self.state.current_balance = balance
        if balance > self.state.peak_balance:
            self.state.peak_balance = balance

    def record_latency(self, latency_ms: float):
        self.state.latency_samples.append(latency_ms)
        if len(self.state.latency_samples) > 200:
            self.state.latency_samples = self.state.latency_samples[-100:]

    def reset_daily(self):
        """Call at session start (00:00 UTC)."""
        self.state.daily_pnl = 0.0
        self.state.daily_trades = 0
        self.state.consecutive_losses = 0
        self._halted = False
        self._halt_reason = ""
        self.state.session_start_ts = time.time()
        logger.info("[CIRCUIT BREAKER] Daily reset")
