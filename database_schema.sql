-- ===================================================================
-- 1. TABLES DEFINITION
-- ===================================================================

-- Table 1: TRADES (Executed Trades Only)
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- LONG, SHORT
    strategy VARCHAR(5) NOT NULL,  -- A, B, C
    order_id VARCHAR(50),
    client_order_id VARCHAR(50),
    execution_type VARCHAR(20),  -- limit, market
    api_latency_ms INTEGER,
    status VARCHAR(20),  -- SUCCESS, API_ERROR, CANCELLED
    error_type VARCHAR(50),
    error_msg TEXT,
    entry_price DECIMAL(20, 8),
    size_usdt DECIMAL(20, 8),
    leverage INTEGER,
    sl_price DECIMAL(20, 8),
    tp1_price DECIMAL(20, 8),
    confidence DECIMAL(5, 2),
    final_score DECIMAL(10, 6)
);

-- Table 2: SIGNALS_SNAPSHOTS (All Decision Points)
CREATE TABLE IF NOT EXISTS signals_snapshots (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(20) NOT NULL,  -- LONG, SHORT, NO_TRADE
    reason TEXT,
    final_score DECIMAL(10, 6),
    confidence DECIMAL(5, 2),
    strategy VARCHAR(5),
    current_price DECIMAL(20, 8),
    atr DECIMAL(20, 8),

    -- Engine 1: Order Flow
    e1_direction VARCHAR(20),
    e1_strength DECIMAL(10, 6),
    e1_conviction DECIMAL(10, 6),
    e1_imbalance DECIMAL(10, 6),
    e1_imbalance_l5 DECIMAL(10, 6),
    e1_imbalance_l10 DECIMAL(10, 6),
    e1_imbalance_l20 DECIMAL(10, 6),
    e1_ofi_velocity DECIMAL(10, 6),
    e1_vpin DECIMAL(10, 6),
    e1_micro_price DECIMAL(20, 8),

    -- Engine 2: Tick Momentum
    e2_direction VARCHAR(20),
    e2_strength DECIMAL(10, 6),
    e2_aggressor_ratio DECIMAL(10, 6),
    e2_aggressor_1s DECIMAL(10, 6),
    e2_aggressor_5s DECIMAL(10, 6),
    e2_aggressor_15s DECIMAL(10, 6),
    e2_alignment DECIMAL(10, 6),
    e2_velocity_ratio DECIMAL(10, 6),

    -- Engine 3: Technical
    e3_direction VARCHAR(20),
    e3_strength DECIMAL(10, 6),
    e3_rsi DECIMAL(10, 6),
    e3_bb_zone VARCHAR(20),

    -- Engine 4: Sentiment
    e4_direction VARCHAR(20),
    e4_strength DECIMAL(10, 6),
    e4_ls_ratio DECIMAL(10, 6),
    e4_funding_rate DECIMAL(10, 8),
    e4_long_pct DECIMAL(10, 6),
    e4_short_pct DECIMAL(10, 6),

    -- Engine 5: Regime
    e5_regime VARCHAR(20),
    e5_vol_phase VARCHAR(20),
    e5_tradeable BOOLEAN,

    -- Weights
    weight_e1 DECIMAL(5, 3),
    weight_e2 DECIMAL(5, 3),
    weight_e3 DECIMAL(5, 3),
    weight_e4 DECIMAL(5, 3)
);

-- Table 3: TRADE_OUTCOMES (Trade Results & PnL)
CREATE TABLE IF NOT EXISTS trade_outcomes (
    id BIGSERIAL PRIMARY KEY,
    trade_id BIGINT REFERENCES trades(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    strategy VARCHAR(5) NOT NULL,
    entry_price DECIMAL(20, 8),
    entry_time TIMESTAMPTZ,
    exit_price DECIMAL(20, 8),
    exit_reason VARCHAR(50),
    exit_type VARCHAR(20),
    pnl_usdt DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 6),
    fees_paid DECIMAL(20, 8),
    net_pnl DECIMAL(20, 8),
    hold_time_seconds INTEGER,
    is_winner BOOLEAN,
    hit_tp BOOLEAN,
    hit_sl BOOLEAN,
    mae DECIMAL(20, 8),
    mfe DECIMAL(20, 8)
);

-- Table 4: PERFORMANCE_METRICS (Aggregated Stats)
CREATE TABLE IF NOT EXISTS performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    period_type VARCHAR(20) NOT NULL,  -- HOURLY, DAILY
    symbol VARCHAR(20),
    strategy VARCHAR(5),
    total_signals INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    total_winners INTEGER DEFAULT 0,
    total_losers INTEGER DEFAULT 0,
    win_rate DECIMAL(5, 2),
    total_pnl DECIMAL(20, 8),
    total_fees DECIMAL(20, 8),
    net_pnl DECIMAL(20, 8),
    avg_winner DECIMAL(20, 8),
    avg_loser DECIMAL(20, 8),
    sharpe_ratio DECIMAL(10, 6),
    max_drawdown DECIMAL(20, 8),
    profit_factor DECIMAL(10, 6),
    avg_hold_time_seconds INTEGER
);

-- Table 5: ENGINE_PERFORMANCE
CREATE TABLE IF NOT EXISTS engine_performance (
    id BIGSERIAL PRIMARY KEY,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    engine VARCHAR(5) NOT NULL,
    symbol VARCHAR(20),
    total_agreements INTEGER DEFAULT 0,
    correct_agreements INTEGER DEFAULT 0,
    false_agreements INTEGER DEFAULT 0,
    total_oppositions INTEGER DEFAULT 0,
    correct_oppositions INTEGER DEFAULT 0,
    accuracy DECIMAL(5, 2),
    avg_strength_when_correct DECIMAL(10, 6),
    avg_strength_when_wrong DECIMAL(10, 6)
);

-- Table 6: REJECTED_SIGNALS
CREATE TABLE IF NOT EXISTS rejected_signals (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    rejection_reason VARCHAR(100) NOT NULL,
    rejection_stage VARCHAR(50),
    would_be_action VARCHAR(10),
    would_be_score DECIMAL(10, 6),
    vpin DECIMAL(10, 6),
    ofi_velocity DECIMAL(10, 6),
    alignment DECIMAL(10, 6),
    agreements INTEGER,
    current_price DECIMAL(20, 8),
    regime VARCHAR(20),
    vol_phase VARCHAR(20),
    price_move_5s DECIMAL(10, 6),
    price_move_30s DECIMAL(10, 6),
    was_correct_signal BOOLEAN
);

-- ===================================================================
-- 2. INDEXES (Separate from CREATE TABLE)
-- ===================================================================
CREATE INDEX IF NOT EXISTS idx_trades_symbol_created ON trades(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_created ON signals_snapshots(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_action ON signals_snapshots(action);
CREATE INDEX IF NOT EXISTS idx_outcomes_trade_id ON trade_outcomes(trade_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_is_winner ON trade_outcomes(is_winner);
CREATE INDEX IF NOT EXISTS idx_metrics_period ON performance_metrics(period_start DESC, period_type);
CREATE INDEX IF NOT EXISTS idx_rejected_reason ON rejected_signals(rejection_reason);

-- ===================================================================
-- 3. VIEWS FOR DASHBOARD
-- ===================================================================

-- Recent Performance (24h)
CREATE OR REPLACE VIEW v_recent_performance AS
SELECT
    DATE_TRUNC('hour', t.created_at) as hour,
    t.symbol,
    t.strategy,
    COUNT(*) as trades,
    COUNT(CASE WHEN o.is_winner THEN 1 END) as winners,
    ROUND(100.0 * COUNT(CASE WHEN o.is_winner THEN 1 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(SUM(o.net_pnl), 2) as net_pnl,
    ROUND(AVG(t.confidence), 2) as avg_confidence
FROM trades t
LEFT JOIN trade_outcomes o ON t.id = o.trade_id
WHERE t.created_at > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2, 3
ORDER BY hour DESC;

-- Rejection Analysis
CREATE OR REPLACE VIEW v_rejection_breakdown AS
SELECT
    rejection_reason,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage,
    AVG(would_be_score) as avg_score
FROM rejected_signals
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY rejection_reason
ORDER BY count DESC;

-- Engine Contribution (Optimized)
CREATE OR REPLACE VIEW v_engine_contribution AS
WITH base AS (
    SELECT 
        o.is_winner,
        s.e1_direction, s.e2_direction, s.e3_direction
    FROM trades t
    JOIN trade_outcomes o ON t.id = o.trade_id
    JOIN signals_snapshots s ON s.symbol = t.symbol 
        AND s.created_at BETWEEN t.created_at - INTERVAL '1 second' AND t.created_at
)
SELECT 
    'E1' as engine,
    COUNT(*) FILTER (WHERE e1_direction != 'NEUTRAL') as active_signals,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_winner AND e1_direction != 'NEUTRAL') / 
          NULLIF(COUNT(*) FILTER (WHERE e1_direction != 'NEUTRAL'), 0), 2) as win_rate
FROM base
UNION ALL
SELECT 
    'E2',
    COUNT(*) FILTER (WHERE e2_direction != 'NEUTRAL'),
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_winner AND e2_direction != 'NEUTRAL') / 
          NULLIF(COUNT(*) FILTER (WHERE e2_direction != 'NEUTRAL'), 0), 2)
FROM base
UNION ALL
SELECT 
    'E3',
    COUNT(*) FILTER (WHERE e3_direction != 'NEUTRAL'),
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_winner AND e3_direction != 'NEUTRAL') / 
          NULLIF(COUNT(*) FILTER (WHERE e3_direction != 'NEUTRAL'), 0), 2)
FROM base;

-- ===================================================================
-- 4. DOCUMENTATION
-- ===================================================================
COMMENT ON TABLE trades IS 'บันทึกการเปิด Order จริง';
COMMENT ON TABLE signals_snapshots IS 'Snapshot ข้อมูลดิบจากทุก Engine ณ เวลาที่ตัดสินใจ';
COMMENT ON TABLE trade_outcomes IS 'สรุปผลกำไร/ขาดทุน และ MAE/MFE ของแต่ละ Trade';