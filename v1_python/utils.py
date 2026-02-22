import numpy as np

def calculate_ema(data, period):
    if len(data) < period:
        return np.nan
    alpha = 2 / (period + 1)
    ema = [np.mean(data[:period])]
    for price in data[period:]:
        ema.append(price * alpha + ema[-1] * (1 - alpha))
    return ema[-1]

def calculate_ema_array(data, period):
    if len(data) < period:
        return []
    alpha = 2 / (period + 1)
    ema = [np.mean(data[:period])]
    for price in data[period:]:
        ema.append(price * alpha + ema[-1] * (1 - alpha))
    return ema

def calculate_rsi(data, period=14):
    if len(data) <= period:
        return 50.0
    diffs = np.diff(data)
    gains = np.where(diffs > 0, diffs, 0)
    losses = np.where(diffs < 0, -diffs, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = [100 - (100 / (1 + rs))]
    for i in range(period, len(diffs)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
    return rsi[-1]

def calculate_atr(highs, lows, closes, period=14):
    if len(highs) <= period:
        return np.mean(np.array(highs) - np.array(lows))
    tr = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr.append(max(hl, hc, lc))
    return calculate_ema(tr, period)

def calculate_atr_array(highs, lows, closes, period=14):
    if len(highs) <= period:
        return []
    tr = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr.append(max(hl, hc, lc))
    return calculate_ema_array(tr, period)

def calculate_bollinger_bands(data, period=20, std_dev=2):
    if len(data) < period:
        return np.nan, np.nan, np.nan
    sma = np.mean(data[-period:])
    std = np.std(data[-period:])
    return sma + std_dev * std, sma, sma - std_dev * std

def calculate_imbalance(bids, asks, levels=10):
    """
    Calculate order book imbalance at specified depth levels.

    Args:
        bids: List of [price, quantity] for bids
        asks: List of [price, quantity] for asks
        levels: Number of depth levels to consider (default 10)

    Returns:
        float: Imbalance ratio (-1 to 1), positive = buy pressure
    """
    bid_vol = sum(float(b[1]) for b in bids[:levels])
    ask_vol = sum(float(a[1]) for a in asks[:levels])
    if bid_vol + ask_vol == 0:
        return 0
    return (bid_vol - ask_vol) / (bid_vol + ask_vol)

def calculate_depth_imbalance_multi(bids, asks):
    """
    Calculate imbalance at multiple depth levels for better liquidity detection.

    Research shows multi-level analysis captures deeper market structure
    better than single-level snapshots.

    Args:
        bids: List of [price, quantity] for bids
        asks: List of [price, quantity] for asks

    Returns:
        dict: Imbalance at L5, L10, L20 and weighted average
    """
    if not bids or not asks:
        return {
            'imbalance_L5': 0.0,
            'imbalance_L10': 0.0,
            'imbalance_L20': 0.0,
            'imbalance_weighted': 0.0
        }

    imb_L5 = calculate_imbalance(bids, asks, levels=5)
    imb_L10 = calculate_imbalance(bids, asks, levels=10)
    imb_L20 = calculate_imbalance(bids, asks, levels=20)

    # Weighted average: L5 most important (closest to price), L20 least
    # Weights: L5=50%, L10=30%, L20=20%
    weighted = (imb_L5 * 0.5) + (imb_L10 * 0.3) + (imb_L20 * 0.2)

    return {
        'imbalance_L5': imb_L5,
        'imbalance_L10': imb_L10,
        'imbalance_L20': imb_L20,
        'imbalance_weighted': weighted
    }

def calculate_adx(highs, lows, closes, period=14):
    """
    Calculate ADX (Average Directional Index) using Wilder's smoothing.
    
    Properly smooths +DI, -DI, and DX series using Wilder's method
    (alpha = 1/period) instead of the broken single-DX approach.
    
    Returns:
        float: ADX value (0-100). >25 = trending, <20 = ranging/choppy
    """
    n = len(closes)
    if n < period * 2 + 1:
        return np.nan

    # Step 1: Calculate True Range, +DM, -DM series
    tr = np.empty(n - 1)
    plus_dm = np.empty(n - 1)
    minus_dm = np.empty(n - 1)

    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr[i - 1] = max(h - l, abs(h - pc), abs(l - pc))

        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm[i - 1] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i - 1] = down_move if (down_move > up_move and down_move > 0) else 0.0

    # Step 2: Wilder's smoothing (alpha = 1/period)
    # Initial seed = SMA of first `period` bars
    atr_s = np.mean(tr[:period])
    pdm_s = np.mean(plus_dm[:period])
    mdm_s = np.mean(minus_dm[:period])

    dx_values = []

    for i in range(period, len(tr)):
        atr_s = atr_s - (atr_s / period) + tr[i]
        pdm_s = pdm_s - (pdm_s / period) + plus_dm[i]
        mdm_s = mdm_s - (mdm_s / period) + minus_dm[i]

        if atr_s == 0:
            continue

        plus_di = 100.0 * pdm_s / atr_s
        minus_di = 100.0 * mdm_s / atr_s
        di_sum = plus_di + minus_di

        if di_sum == 0:
            dx_values.append(0.0)
        else:
            dx_values.append(100.0 * abs(plus_di - minus_di) / di_sum)

    if len(dx_values) < period:
        return np.mean(dx_values) if dx_values else 0.0

    # Step 3: Smooth DX with Wilder's method → ADX
    adx = np.mean(dx_values[:period])
    for dx_val in dx_values[period:]:
        adx = adx - (adx / period) + dx_val

    return adx


def calculate_macd(data, fast=12, slow=26, signal=9):
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Returns:
        tuple: (macd_line, signal_line, histogram) or (nan, nan, nan) if insufficient data
    """
    if len(data) < slow + signal:
        return np.nan, np.nan, np.nan

    fast_ema = calculate_ema_array(data, fast)
    slow_ema = calculate_ema_array(data, slow)

    # Align arrays (slow_ema is shorter)
    offset = len(fast_ema) - len(slow_ema)
    macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema)]

    if len(macd_line) < signal:
        return np.nan, np.nan, np.nan

    signal_line = calculate_ema_array(macd_line, signal)
    offset2 = len(macd_line) - len(signal_line)

    histogram = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], histogram


def calculate_keltner_channels(highs, lows, closes, ema_period=20, atr_period=14, multiplier=1.5):
    """
    Calculate Keltner Channels for volatility-adjusted support/resistance.
    
    Returns:
        tuple: (upper, middle, lower) channel values
    """
    if len(closes) < max(ema_period, atr_period + 1):
        return np.nan, np.nan, np.nan

    middle = calculate_ema(closes, ema_period)
    atr_val = calculate_atr(highs, lows, closes, atr_period)

    if np.isnan(middle) or np.isnan(atr_val):
        return np.nan, np.nan, np.nan

    upper = middle + multiplier * atr_val
    lower = middle - multiplier * atr_val
    return upper, middle, lower

def calculate_percentiles(data_list, percentiles=[20, 80, 95]):
    if not data_list or len(data_list) < 5:
        return {p: 0 for p in percentiles}
    return {p: np.percentile(data_list, p) for p in percentiles}

def calculate_vpin(ticks, volume_bucket_size=50, num_buckets=5):
    """
    Calculate VPIN (Volume-Synchronized Probability of Informed Trading)

    Research shows VPIN can predict price jumps 0.5-2 seconds in advance.
    Instead of time-based windows, uses volume-based buckets.

    Args:
        ticks: List of tick data [{'q': quantity, 'm': is_buyer_maker}, ...]
        volume_bucket_size: Volume threshold for each bucket (default 50 for crypto)
        num_buckets: Number of buckets to average (default 5)

    Returns:
        float: VPIN score (0-1), higher = more informed trading = potential price jump
    """
    if not ticks or len(ticks) < 10:
        return 0.0

    buckets = []
    current_bucket = {'buy': 0.0, 'sell': 0.0, 'total': 0.0}

    # Process ticks from newest to oldest
    for tick in ticks:
        qty = float(tick.get('q', 0))
        is_sell = tick.get('m', False)  # m=True means buyer is maker (i.e., sell aggressor)

        if is_sell:
            current_bucket['sell'] += qty
        else:
            current_bucket['buy'] += qty

        current_bucket['total'] += qty

        # When bucket reaches target volume, calculate VPIN for this bucket
        if current_bucket['total'] >= volume_bucket_size:
            if current_bucket['total'] > 0:
                bucket_vpin = abs(current_bucket['buy'] - current_bucket['sell']) / current_bucket['total']
                buckets.append(bucket_vpin)

            # Reset for next bucket
            current_bucket = {'buy': 0.0, 'sell': 0.0, 'total': 0.0}

            # Stop when we have enough buckets
            if len(buckets) >= num_buckets:
                break

    # Return average VPIN across buckets
    if not buckets:
        return 0.0

    return np.mean(buckets)
