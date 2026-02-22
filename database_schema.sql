-- ===================================================================
-- VORTEX-7 Trading Bot Database Schema for Supabase (PostgreSQL)
-- Purpose: Complete trade analytics and signal tracking for dashboard
-- ===================================================================

-- Table 1: TRADES (Executed Trades Only)
-- เก็บการเทรดที่เกิดขึ้นจริงทั้งหมด
CREATE TABLE IF NOT EXISTS trades (
    -- Primary Info
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Trade Identification
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- LONG, SHORT
    strategy VARCHAR(5) NOT NULL,  -- A, B, C

    -- Order Details
    order_id VARCHAR(50),
    client_order_id VARCHAR(50),
    execution_type VARCHAR(20),  -- limit, market
    api_latency_ms INTEGER,
    status VARCHAR(20),  -- SUCCESS, API_ERROR, CANCELLED
    error_type VARCHAR(50),
    error_msg TEXT,

    -- Entry Details
    entry_price DECIMAL(20, 8),
    size_usdt DECIMAL(20, 8),
    leverage INTEGER,
    sl_price DECIMAL(20, 8),
    tp1_price DECIMAL(20, 8),

    -- Decision Metrics
    confidence DECIMAL(5, 2),
    final_score DECIMAL(10, 6),

    -- Indexes for fast querying
    CONSTRAINT trades_symbol_idx_created_at INDEX (symbol, created_at DESC),
    CONSTRAINT trades_strategy_idx INDEX (strategy),
    CONSTRAINT trades_created_at_idx INDEX (created_at DESC)
);

-- Table 2: SIGNALS_SNAPSHOTS (All Decision Points)
-- เก็บ signals ทุกครั้งที่ระบบตัดสินใจ (ทั้งเข้าและไม่เข้า)
CREATE TABLE IF NOT EXISTS signals_snapshots (
    -- Primary Info
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,

    -- Decision Result
    action VARCHAR(20) NOT NULL,  -- LONG, SHORT, NO_TRADE
    reason TEXT,  -- เหตุผลที่ไม่เข้า (ถ้า NO_TRADE)
    final_score DECIMAL(10, 6),
    confidence DECIMAL(5, 2),
    strategy VARCHAR(5),

    -- Market Context
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
    e1_ofi_velocity DECIMAL(10, 6),  -- NEW: OFI velocity
    e1_vpin DECIMAL(10, 6),  -- NEW: VPIN
    e1_micro_price DECIMAL(20, 8),

    -- Engine 2: Tick Momentum
    e2_direction VARCHAR(20),
    e2_strength DECIMAL(10, 6),
    e2_aggressor_ratio DECIMAL(10, 6),
    e2_aggressor_1s DECIMAL(10, 6),  -- NEW: Multi-timeframe
    e2_aggressor_5s DECIMAL(10, 6),  -- NEW
    e2_aggressor_15s DECIMAL(10, 6),  -- NEW
    e2_alignment DECIMAL(10, 6),  -- NEW: Timeframe alignment
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

    -- Weights Used
    weight_e1 DECIMAL(5, 3),
    weight_e2 DECIMAL(5, 3),
    weight_e3 DECIMAL(5, 3),
    weight_e4 DECIMAL(5, 3),

    -- Indexes
    CONSTRAINT signals_symbol_idx_created_at INDEX (symbol, created_at DESC),
    CONSTRAINT signals_action_idx INDEX (action),
    CONSTRAINT signals_created_at_idx INDEX (created_at DESC)
);

-- Table 3: TRADE_OUTCOMES (Trade Results & PnL)
-- เก็บผลลัพธ์ของการเทรดแต่ละตัว
CREATE TABLE IF NOT EXISTS trade_outcomes (
    -- Primary Info
    id BIGSERIAL PRIMARY KEY,
    trade_id BIGINT REFERENCES trades(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,

    -- Trade Info
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    strategy VARCHAR(5) NOT NULL,

    -- Entry
    entry_price DECIMAL(20, 8),
    entry_time TIMESTAMPTZ,

    -- Exit
    exit_price DECIMAL(20, 8),
    exit_reason VARCHAR(50),  -- TP_HIT, SL_HIT, MANUAL_CLOSE, TIMEOUT
    exit_type VARCHAR(20),  -- limit, market

    -- Performance
    pnl_usdt DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 6),
    fees_paid DECIMAL(20, 8),
    net_pnl DECIMAL(20, 8),  -- PnL after fees

    -- Timing
    hold_time_seconds INTEGER,

    -- Result
    is_winner BOOLEAN,
    hit_tp BOOLEAN,
    hit_sl BOOLEAN,

    -- Max Adverse/Favorable Excursion
    mae DECIMAL(20, 8),  -- Maximum Adverse Excursion (ติดลบสุดเท่าไหร่)
    mfe DECIMAL(20, 8),  -- Maximum Favorable Excursion (กำไรสุดเท่าไหร่)

    -- Indexes
    CONSTRAINT outcomes_trade_id_idx INDEX (trade_id),
    CONSTRAINT outcomes_symbol_created_at_idx INDEX (symbol, created_at DESC),
    CONSTRAINT outcomes_is_winner_idx INDEX (is_winner),
    CONSTRAINT outcomes_strategy_idx INDEX (strategy)
);

-- Table 4: PERFORMANCE_METRICS (Aggregated Stats)
-- เก็บ metrics สรุปรายชั่วโมง/วัน
CREATE TABLE IF NOT EXISTS performance_metrics (
    -- Primary Info
    id BIGSERIAL PRIMARY KEY,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    period_type VARCHAR(20) NOT NULL,  -- HOURLY, DAILY, WEEKLY

    -- Symbol
    symbol VARCHAR(20),  -- NULL = all symbols
    strategy VARCHAR(5),  -- NULL = all strategies

    -- Trade Counts
    total_signals INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    total_winners INTEGER DEFAULT 0,
    total_losers INTEGER DEFAULT 0,

    -- Win Rate
    win_rate DECIMAL(5, 2),  -- Percentage

    -- PnL
    total_pnl DECIMAL(20, 8),
    total_fees DECIMAL(20, 8),
    net_pnl DECIMAL(20, 8),
    avg_winner DECIMAL(20, 8),
    avg_loser DECIMAL(20, 8),

    -- Risk Metrics
    sharpe_ratio DECIMAL(10, 6),
    max_drawdown DECIMAL(20, 8),
    profit_factor DECIMAL(10, 6),  -- Gross profit / Gross loss

    -- Timing
    avg_hold_time_seconds INTEGER,

    -- Predictive Signals Performance
    vpin_avg DECIMAL(10, 6),
    ofi_velocity_avg DECIMAL(10, 6),
    alignment_avg DECIMAL(10, 6),

    -- Indexes
    CONSTRAINT metrics_period_idx INDEX (period_start DESC, period_type),
    CONSTRAINT metrics_symbol_strategy_idx INDEX (symbol, strategy)
);

-- Table 5: ENGINE_PERFORMANCE (Per-Engine Analytics)
-- เก็บสถิติว่า engine ไหนทำงานดีที่สุด
CREATE TABLE IF NOT EXISTS engine_performance (
    -- Primary Info
    id BIGSERIAL PRIMARY KEY,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,

    -- Engine
    engine VARCHAR(5) NOT NULL,  -- E1, E2, E3, E4
    symbol VARCHAR(20),

    -- Agreement Analysis
    total_agreements INTEGER DEFAULT 0,  -- กี่ครั้งที่ engine นี้เห็นด้วยกับ decision
    correct_agreements INTEGER DEFAULT 0,  -- กี่ครั้งที่เห็นด้วยแล้วชนะ
    false_agreements INTEGER DEFAULT 0,  -- กี่ครั้งที่เห็นด้วยแล้วแพ้

    -- Opposition Analysis
    total_oppositions INTEGER DEFAULT 0,  -- กี่ครั้งที่ engine นี้คัดค้าน decision
    correct_oppositions INTEGER DEFAULT 0,  -- กี่ครั้งที่คัดค้านแล้วถูก (trade แพ้)

    -- Accuracy
    accuracy DECIMAL(5, 2),  -- (correct_agreements + correct_oppositions) / total

    -- Signal Quality
    avg_strength_when_correct DECIMAL(10, 6),
    avg_strength_when_wrong DECIMAL(10, 6),

    -- Indexes
    CONSTRAINT engine_perf_period_idx INDEX (period_start DESC),
    CONSTRAINT engine_perf_engine_idx INDEX (engine)
);

-- Table 6: REJECTED_SIGNALS (Why We Didn't Trade)
-- เก็บสาเหตุที่ไม่เข้าเทรด เพื่อ optimize filters
CREATE TABLE IF NOT EXISTS rejected_signals (
    -- Primary Info
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,

    -- Rejection Info
    rejection_reason VARCHAR(100) NOT NULL,
    rejection_stage VARCHAR(50),  -- E5_FILTER, PREDICTIVE_FILTER, AGREEMENT, etc.

    -- Would-be Trade Info
    would_be_action VARCHAR(10),
    would_be_score DECIMAL(10, 6),

    -- Key Metrics That Failed
    vpin DECIMAL(10, 6),
    ofi_velocity DECIMAL(10, 6),
    alignment DECIMAL(10, 6),
    agreements INTEGER,

    -- Market Context
    current_price DECIMAL(20, 8),
    regime VARCHAR(20),
    vol_phase VARCHAR(20),

    -- Missed Opportunity Analysis (filled later)
    price_move_5s DECIMAL(10, 6),  -- ราคาเคลื่อนไหวยังไงหลัง 5 วินาที
    price_move_30s DECIMAL(10, 6),
    was_correct_signal BOOLEAN,  -- ถ้าเข้าจริงจะชนะหรือไม่

    -- Index
    CONSTRAINT rejected_created_at_idx INDEX (created_at DESC),
    CONSTRAINT rejected_reason_idx INDEX (rejection_reason)
);

-- ===================================================================
-- VIEWS for Dashboard Queries
-- ===================================================================

-- View: Recent Trade Performance
CREATE OR REPLACE VIEW v_recent_performance AS
SELECT
    DATE_TRUNC('hour', t.created_at) as hour,
    t.symbol,
    t.strategy,
    COUNT(*) as trades,
    COUNT(CASE WHEN o.is_winner THEN 1 END) as winners,
    ROUND(100.0 * COUNT(CASE WHEN o.is_winner THEN 1 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(SUM(o.net_pnl), 2) as net_pnl,
    ROUND(AVG(t.confidence), 2) as avg_confidence,
    ROUND(AVG(CASE WHEN o.is_winner THEN t.final_score END), 4) as avg_score_winners,
    ROUND(AVG(CASE WHEN NOT o.is_winner THEN t.final_score END), 4) as avg_score_losers
FROM trades t
LEFT JOIN trade_outcomes o ON t.id = o.trade_id
WHERE t.created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour, t.symbol, t.strategy
ORDER BY hour DESC;

-- View: Signal Quality Analysis
CREATE OR REPLACE VIEW v_signal_quality AS
SELECT
    action,
    COUNT(*) as total_signals,
    AVG(e1_vpin) as avg_vpin,
    AVG(ABS(e1_ofi_velocity)) as avg_ofi_velocity,
    AVG(e2_alignment) as avg_alignment,
    AVG(confidence) as avg_confidence
FROM signals_snapshots
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY action;

-- View: Rejection Reasons Breakdown
CREATE OR REPLACE VIEW v_rejection_breakdown AS
SELECT
    rejection_reason,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage,
    AVG(would_be_score) as avg_score,
    COUNT(CASE WHEN was_correct_signal THEN 1 END) as would_have_won
FROM rejected_signals
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY rejection_reason
ORDER BY count DESC;

-- View: Engine Contribution Analysis
CREATE OR REPLACE VIEW v_engine_contribution AS
WITH trade_signals AS (
    SELECT
        t.id as trade_id,
        t.strategy,
        o.is_winner,
        s.e1_direction,
        s.e2_direction,
        s.e3_direction,
        s.e4_direction,
        t.side
    FROM trades t
    LEFT JOIN trade_outcomes o ON t.id = o.trade_id
    LEFT JOIN signals_snapshots s ON s.symbol = t.symbol
        AND s.created_at BETWEEN t.created_at - INTERVAL '1 second' AND t.created_at
    WHERE t.created_at > NOW() - INTERVAL '7 days'
)
SELECT
    'E1' as engine,
    COUNT(CASE WHEN e1_direction IN ('BUY_PRESSURE', 'SELL_PRESSURE') THEN 1 END) as active_signals,
    COUNT(CASE WHEN is_winner AND e1_direction != 'NEUTRAL' THEN 1 END) as contributed_to_wins,
    ROUND(100.0 * COUNT(CASE WHEN is_winner AND e1_direction != 'NEUTRAL' THEN 1 END) /
          NULLIF(COUNT(CASE WHEN e1_direction != 'NEUTRAL' THEN 1 END), 0), 2) as win_rate
FROM trade_signals
UNION ALL
SELECT
    'E2' as engine,
    COUNT(CASE WHEN e2_direction IN ('MOMENTUM_LONG', 'MOMENTUM_SHORT') THEN 1 END),
    COUNT(CASE WHEN is_winner AND e2_direction != 'NEUTRAL' THEN 1 END),
    ROUND(100.0 * COUNT(CASE WHEN is_winner AND e2_direction != 'NEUTRAL' THEN 1 END) /
          NULLIF(COUNT(CASE WHEN e2_direction != 'NEUTRAL' THEN 1 END), 0), 2)
FROM trade_signals
UNION ALL
SELECT
    'E3' as engine,
    COUNT(CASE WHEN e3_direction IN ('LONG', 'SHORT') THEN 1 END),
    COUNT(CASE WHEN is_winner AND e3_direction != 'NEUTRAL' THEN 1 END),
    ROUND(100.0 * COUNT(CASE WHEN is_winner AND e3_direction != 'NEUTRAL' THEN 1 END) /
          NULLIF(COUNT(CASE WHEN e3_direction != 'NEUTRAL' THEN 1 END), 0), 2)
FROM trade_signals;

-- ===================================================================
-- Indexes for Performance
-- ===================================================================

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_trades_symbol_created ON trades(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_action_created ON signals_snapshots(symbol, action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcomes_winner_created ON trade_outcomes(is_winner, created_at DESC);

-- ===================================================================
-- Comments for Documentation
-- ===================================================================

COMMENT ON TABLE trades IS 'All executed trades with full order details';
COMMENT ON TABLE signals_snapshots IS 'Complete signal snapshot at every decision point (including NO_TRADE)';
COMMENT ON TABLE trade_outcomes IS 'Trade results including PnL, exit reason, and timing';
COMMENT ON TABLE performance_metrics IS 'Aggregated performance statistics by time period';
COMMENT ON TABLE engine_performance IS 'Per-engine accuracy and contribution metrics';
COMMENT ON TABLE rejected_signals IS 'Signals that were filtered out with reasons why';

-- ===================================================================
-- Sample Queries for Dashboard
-- ===================================================================

-- Get win rate by strategy (last 7 days)
-- SELECT strategy, COUNT(*) as trades,
--        ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate
-- FROM trade_outcomes o JOIN trades t ON o.trade_id = t.id
-- WHERE o.created_at > NOW() - INTERVAL '7 days'
-- GROUP BY strategy;

-- Find common patterns in losing trades
-- SELECT e1_direction, e2_direction, e3_direction, COUNT(*) as count
-- FROM signals_snapshots s
-- JOIN trades t ON s.symbol = t.symbol AND s.created_at BETWEEN t.created_at - INTERVAL '1 sec' AND t.created_at
-- JOIN trade_outcomes o ON t.id = o.trade_id
-- WHERE NOT o.is_winner
-- GROUP BY e1_direction, e2_direction, e3_direction
-- ORDER BY count DESC LIMIT 10;

-- Analyze predictive signals performance
-- SELECT
--     CASE WHEN e1_vpin > 0.5 THEN 'High VPIN' ELSE 'Low VPIN' END as vpin_level,
--     CASE WHEN ABS(e1_ofi_velocity) > 2.0 THEN 'High Velocity' ELSE 'Low Velocity' END as velocity_level,
--     COUNT(*) as trades,
--     AVG(CASE WHEN o.is_winner THEN 100.0 ELSE 0 END) as win_rate
-- FROM signals_snapshots s
-- JOIN trades t ON s.symbol = t.symbol AND s.created_at BETWEEN t.created_at - INTERVAL '1 sec' AND t.created_at
-- JOIN trade_outcomes o ON t.id = o.trade_id
-- GROUP BY vpin_level, velocity_level;
