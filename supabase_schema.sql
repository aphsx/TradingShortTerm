-- Supabase / PostgreSQL Schema for VORTEX-7

-- 1. Create trades table
CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(5) NOT NULL,          -- 'LONG' or 'SHORT'
    strategy CHAR(1) NOT NULL,         -- 'A', 'B', or 'C'
    
    -- API & Execution Analytics (Detailed Logs)
    order_id VARCHAR(50),              -- BNB/Exchange assigned Order ID
    client_order_id VARCHAR(50),       -- Our custom ID
    execution_type VARCHAR(20),        -- 'LIMIT', 'MARKET', etc.
    api_latency_ms INTEGER,            -- How long did CCXT request take?
    status VARCHAR(20) DEFAULT 'NEW',  -- 'SUCCESS', 'REJECTED', 'CANCELED', 'API_ERROR'
    error_type VARCHAR(50),            -- CCXT Exception type (e.g., NetworkError, InsufficientFunds)
    error_msg TEXT,                    -- Full error dump
    
    -- Price & Position Details
    entry_price DECIMAL(18,8) NOT NULL,
    exit_price DECIMAL(18,8),
    size_usdt DECIMAL(18,2) NOT NULL,
    leverage INTEGER NOT NULL,
    sl_price DECIMAL(18,8) NOT NULL,
    tp1_price DECIMAL(18,8) NOT NULL,
    tp2_price DECIMAL(18,8),
    
    -- Trade Lifecycle & Returns
    pnl_gross DECIMAL(18,4),
    fee_total DECIMAL(18,4),
    pnl_net DECIMAL(18,4),
    confidence DECIMAL(5,2),           -- 0 to 100
    engine_signals JSONB,              -- snapshot of signals upon entry 
    final_score DECIMAL(5,4),
    hold_duration_sec INTEGER,
    exit_reason VARCHAR(30),           -- 'TP1', 'TP2', 'SL', 'TIMEOUT'
    maker_fills INTEGER,
    taker_fills INTEGER,
    entry_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_time TIMESTAMPTZ,
    regime_at_entry VARCHAR(20),
    vol_phase_at_entry VARCHAR(20)
);

-- Index for analytics and faster query
CREATE INDEX idx_trades_symbol_time ON trades(symbol, entry_time);
CREATE INDEX idx_trades_strategy_time ON trades(strategy, entry_time);
CREATE INDEX idx_trades_exit_reason ON trades(exit_reason);

-- 2. Create engine_accuracy table (Used by Learning Module later)
CREATE TABLE engine_accuracy (
    id BIGSERIAL PRIMARY KEY,
    trade_id BIGINT REFERENCES trades(id) ON DELETE CASCADE,
    engine VARCHAR(5),                 -- 'E1', 'E2', 'E3', 'E4'
    signal_dir VARCHAR(10),            -- direction the engine indicated
    signal_strength DECIMAL(4,3),
    trade_result VARCHAR(4),           -- 'WIN' or 'LOSS'
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Create daily_summary table 
CREATE TABLE daily_summary (
    date DATE PRIMARY KEY,
    symbol VARCHAR(20),
    total_trades INTEGER,
    wins INTEGER,
    losses INTEGER,
    no_fills INTEGER,
    gross_pnl DECIMAL(18,4),
    total_fees DECIMAL(18,4),
    net_pnl DECIMAL(18,4),
    fee_ratio DECIMAL(5,4),            -- fee/gross
    maker_rate DECIMAL(5,4),           -- maker fills / total fills
    max_drawdown DECIMAL(5,4),
    best_trade_pnl DECIMAL(18,4),
    worst_trade_pnl DECIMAL(18,4),
    avg_hold_sec DECIMAL(10,2),
    avg_confidence DECIMAL(5,2),
    strategy_a_count INTEGER,
    strategy_b_count INTEGER,
    strategy_c_count INTEGER,
    circuit_breaks INTEGER             -- how many times circuit breaks hit
);

-- 4. Create weight_history table
CREATE TABLE weight_history (
    id BIGSERIAL PRIMARY KEY,
    trade_count INTEGER,               -- optimized after N trades
    e1_weight DECIMAL(4,3),
    e2_weight DECIMAL(4,3),
    e3_weight DECIMAL(4,3),
    e4_weight DECIMAL(4,3),
    win_rate DECIMAL(5,4),
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
