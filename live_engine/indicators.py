"""
indicators.py — Numba-accelerated indicator calculations.
Drop-in replacements for the NumPy versions in ams_scalper.py,
running 50-100x faster via JIT compilation.
"""

import numpy as np

try:
    from numba import njit
except ImportError:
    # Fallback when numba is not installed (e.g. backtest environment).
    # Same algorithms, no JIT — correct results, slower speed.
    def njit(*args, **kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator if args and callable(args[0]) is False else decorator(args[0]) if args else decorator


@njit(cache=True)
def calc_ema(prices: np.ndarray, period: int) -> float:
    """EMA — Exponential Moving Average (Numba JIT)."""
    n = len(prices)
    if n == 0:
        return 0.0
    if n < period:
        return prices[-1]
    k = 2.0 / (period + 1)
    result = prices[0]
    for i in range(1, n):
        result = prices[i] * k + result * (1.0 - k)
    return result


@njit(cache=True)
def calc_rsi(prices: np.ndarray, period: int) -> float:
    """RSI — Wilder's smoothing (Numba JIT)."""
    n = len(prices)
    if n < period + 1:
        return 50.0
    start = n - period - 1
    avg_gain = 0.0
    avg_loss = 0.0
    # First value
    delta = prices[start + 1] - prices[start]
    if delta > 0:
        avg_gain = delta
    else:
        avg_loss = -delta
    # Wilder smoothing
    for i in range(start + 2, n):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            avg_gain = (avg_gain * (period - 1) + delta) / period
            avg_loss = (avg_loss * (period - 1)) / period
        else:
            avg_gain = (avg_gain * (period - 1)) / period
            avg_loss = (avg_loss * (period - 1) + (-delta)) / period
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


@njit(cache=True)
def calc_atr(highs: np.ndarray, lows: np.ndarray,
             closes: np.ndarray, period: int) -> float:
    """ATR — Average True Range with Wilder's smoothing (Numba JIT)."""
    n = len(highs)
    if n < 2:
        return highs[0] - lows[0] if n > 0 else 0.0
    if n < period + 1:
        # Not enough data: return simple average TR
        total = 0.0
        for i in range(1, n):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
            total += tr
        return total / max(n - 1, 1)

    # Initial ATR: simple mean of first `period` TRs
    atr_val = 0.0
    for i in range(1, period + 1):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        atr_val += tr
    atr_val /= period

    # Wilder smoothing for remaining
    for i in range(period + 1, n):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


@njit(cache=True)
def calc_bollinger(closes: np.ndarray, period: int,
                   num_std: float) -> tuple[float, float, float]:
    """Bollinger Bands → (upper, middle, lower). Numba JIT."""
    n = len(closes)
    if n < period:
        v = closes[-1] if n > 0 else 0.0
        return (v, v, v)
    window = closes[-period:]
    total = 0.0
    for i in range(period):
        total += window[i]
    middle = total / period
    sq_sum = 0.0
    for i in range(period):
        diff = window[i] - middle
        sq_sum += diff * diff
    std = (sq_sum / (period - 1)) ** 0.5
    return (middle + num_std * std, middle, middle - num_std * std)


@njit(cache=True)
def detect_squeeze(closes: np.ndarray, bb_period: int,
                   bb_std: float, lookback: int) -> bool:
    """BB Squeeze — bandwidth at percentile < 15% of lookback. Numba JIT."""
    n = len(closes)
    if n < bb_period + lookback:
        return False

    min_bw = 1e18
    max_bw = -1e18
    current_bw = 0.0

    for offset in range(lookback):
        end = n - offset
        start = end - bb_period
        if start < 0:
            break
        total = 0.0
        for j in range(start, end):
            total += closes[j]
        mid = total / bb_period
        if mid <= 0:
            continue
        sq_sum = 0.0
        for j in range(start, end):
            diff = closes[j] - mid
            sq_sum += diff * diff
        std = (sq_sum / (bb_period - 1)) ** 0.5
        bw = (2.0 * bb_std * std) / mid
        if offset == 0:
            current_bw = bw
        if bw < min_bw:
            min_bw = bw
        if bw > max_bw:
            max_bw = bw

    bw_range = max_bw - min_bw
    if bw_range <= 0:
        return False
    percentile = (current_bw - min_bw) / bw_range
    return percentile < 0.15


@njit(cache=True)
def calc_vwap(closes: np.ndarray, volumes: np.ndarray,
              period: int) -> float:
    """VWAP — Volume Weighted Average Price. Numba JIT."""
    n = len(closes)
    if n < period:
        return closes[-1] if n > 0 else 0.0
    total_pv = 0.0
    total_v = 0.0
    for i in range(n - period, n):
        total_pv += closes[i] * volumes[i]
        total_v += volumes[i]
    if total_v <= 0:
        return closes[-1]
    return total_pv / total_v


@njit(cache=True)
def calc_rvol(volumes: np.ndarray, period: int) -> float:
    """Relative Volume. Numba JIT."""
    n = len(volumes)
    if n < period + 1:
        return 0.0
    current = volumes[-1]
    total = 0.0
    for i in range(n - period - 1, n - 1):
        total += volumes[i]
    avg = total / period
    if avg <= 0:
        return 0.0
    return current / avg


@njit(cache=True)
def order_book_imbalance(bid_qty: float, ask_qty: float) -> float:
    """OBI: -1.0 (sell pressure) to +1.0 (buy pressure)."""
    total = bid_qty + ask_qty
    if total == 0:
        return 0.0
    return (bid_qty - ask_qty) / total


@njit(cache=True)
def trailing_stop_calc(
    side_is_long: bool,
    highest: float,
    lowest: float,
    current_atr: float,
    entry_price: float,
    activate_atr_mult: float,
    trail_atr_mult: float,
    prev_trailing_stop: float,
) -> tuple[bool, float]:
    """Volatility-based trailing stop using real-time ATR."""
    if side_is_long:
        unrealized = highest - entry_price
        if unrealized >= current_atr * activate_atr_mult:
            new_stop = highest - (current_atr * trail_atr_mult)
            return True, max(new_stop, prev_trailing_stop)
    else:
        unrealized = entry_price - lowest
        if unrealized >= current_atr * activate_atr_mult:
            new_stop = lowest + (current_atr * trail_atr_mult)
            if prev_trailing_stop <= 0:
                return True, new_stop
            return True, min(new_stop, prev_trailing_stop)
    return False, prev_trailing_stop
