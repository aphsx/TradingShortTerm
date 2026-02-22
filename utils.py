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
    if len(closes) < period * 2:
        return np.nan
        
    tr = []
    plus_dm = []
    minus_dm = []
    
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        ph = highs[i-1]
        pl = lows[i-1]
        c = closes[i-1]
        
        tr.append(max(h - l, abs(h - c), abs(l - c)))
        
        up_move = h - ph
        down_move = pl - l
        
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)
            
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)
            
    atr = calculate_ema(tr, period)
    if atr == 0 or np.isnan(atr): return 0
    
    plus_di = 100 * (calculate_ema(plus_dm, period) / atr)
    minus_di = 100 * (calculate_ema(minus_dm, period) / atr)
    
    if (plus_di + minus_di) == 0: return 0
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    # Simple ADX (could use EMA of DX, but average works for approximation)
    adx = np.mean([dx] * period) # Simplified
    return adx

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
