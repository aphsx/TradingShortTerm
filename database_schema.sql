-- ===================================================================
-- VORTEX-7  ·  Trading Database Schema  v2.0
-- 2 tables only: trade_logs + rejected_signals
-- All DB writes are fire-and-forget (asyncio.create_task) in Python
-- so they never block the trading loop.
-- ===================================================================

-- ─── 1. TRADE LOGS ──────────────────────────────────────────────────────────
-- One row per trade attempt.
--   OPEN  row is inserted the moment an order is filled.
--   CLOSED row is updated with exit data when the position is closed.
--   FAILED row stays with only the error_msg filled in.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trade_logs (

    -- Identity
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    symbol          VARCHAR(20)      NOT NULL,
    side            VARCHAR(10)      NOT NULL,   -- LONG | SHORT
    status          VARCHAR(20)      NOT NULL,   -- OPEN | CLOSED | FAILED

    -- Order metadata
    order_id        VARCHAR(64),
    strategy        VARCHAR(40),
    execution_type  VARCHAR(20),                -- MARKET | LIMIT
    api_latency_ms  INTEGER,

    -- ── Entry side ──────────────────────────────────────────────
    entry_price     NUMERIC(20, 8),
    quantity        NUMERIC(20, 8),             -- Base asset qty (e.g. BTC)
    leverage        SMALLINT,
    margin_used     NUMERIC(20, 8),             -- Notional / leverage (USDT)
    sl_price        NUMERIC(20, 8),
    tp_price        NUMERIC(20, 8),
    opened_at       TIMESTAMPTZ      DEFAULT NOW(),
    open_fee_usdt   NUMERIC(20, 8),             -- ค่าธรรมเนียมเปิดไม้ (USDT)

    -- Signal context snapshot (filled at open, never changes)
    confidence      NUMERIC(6, 2),              -- 0–100
    final_score     NUMERIC(6, 4),              -- DecisionEngine score
    e1_direction    VARCHAR(10),                -- LONG | SHORT | NEUTRAL
    e5_regime       VARCHAR(30),                -- TRENDING_UP | RANGING | etc.

    -- ── Exit side (NULL until closed) ───────────────────────────
    exit_price      NUMERIC(20, 8),
    closed_at       TIMESTAMPTZ,
    hold_time_s     INTEGER,                    -- seconds the position was open
    close_reason    VARCHAR(30),                -- TP_HIT | SL_HIT | TIME_EXIT | MANUAL
    close_fee_usdt  NUMERIC(20, 8),             -- ค่าธรรมเนียมปิดไม้ (USDT)

    -- ── PnL (filled when status = CLOSED) ───────────────────────
    pnl_gross_usdt  NUMERIC(20, 8),             -- (exit − entry) × qty × leverage
    pnl_net_usdt    NUMERIC(20, 8),             -- gross − open_fee − close_fee  ← ตัวเลขจริง
    pnl_pct         NUMERIC(10, 6),             -- pnl_net / margin_used × 100

    -- Error (filled when status = FAILED)
    error_msg       TEXT
);

-- Indexes optimised for the most common dashboard queries
CREATE INDEX IF NOT EXISTS idx_tl_created   ON trade_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tl_symbol    ON trade_logs (symbol, status);
CREATE INDEX IF NOT EXISTS idx_tl_status    ON trade_logs (status);


-- ─── 2. REJECTED SIGNALS ────────────────────────────────────────────────────
-- Logged when RiskManager decides not to fire the order.
-- Useful for strategy tuning: "how many good signals got killed by fees/rr?"
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rejected_signals (

    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol           VARCHAR(20) NOT NULL,
    action           VARCHAR(10),                -- LONG | SHORT (intended direction)
    strategy         VARCHAR(40),
    confidence       NUMERIC(6, 2),
    rejection_reason TEXT,                       -- FEE_TOO_HIGH | RR_LOW | DRAWDOWN | COOLDOWN
    current_price    NUMERIC(20, 8),
    daily_pnl        NUMERIC(20, 8)

);

CREATE INDEX IF NOT EXISTS idx_rs_created ON rejected_signals (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rs_symbol  ON rejected_signals (symbol);


-- ─── DASHBOARD VIEWS ────────────────────────────────────────────────────────

-- Overall summary (all-time)
CREATE OR REPLACE VIEW v_trading_summary AS
SELECT
    COUNT(*)                                                    AS total_attempts,
    COUNT(*) FILTER (WHERE status = 'CLOSED')                   AS total_closed,
    COUNT(*) FILTER (WHERE status = 'FAILED')                   AS total_failed,
    ROUND(SUM(pnl_net_usdt)               FILTER (WHERE status = 'CLOSED'), 4) AS net_profit_usdt,
    ROUND(SUM(open_fee_usdt + close_fee_usdt) FILTER (WHERE status = 'CLOSED'), 4) AS total_fees_usdt,
    ROUND(AVG(pnl_pct)                    FILTER (WHERE status = 'CLOSED'), 4) AS avg_pnl_pct,
    ROUND(AVG(hold_time_s)                FILTER (WHERE status = 'CLOSED'), 0) AS avg_hold_s,
    COUNT(*) FILTER (WHERE status = 'CLOSED' AND pnl_net_usdt > 0) AS win_count,
    COUNT(*) FILTER (WHERE status = 'CLOSED' AND pnl_net_usdt < 0) AS loss_count
FROM trade_logs;


-- Per-symbol breakdown
CREATE OR REPLACE VIEW v_symbol_summary AS
SELECT
    symbol,
    side,
    COUNT(*)                                             AS trades,
    ROUND(SUM(pnl_net_usdt), 4)                          AS net_pnl,
    ROUND(AVG(pnl_pct), 4)                               AS avg_pnl_pct,
    ROUND(AVG(hold_time_s), 0)                           AS avg_hold_s,
    ROUND(SUM(open_fee_usdt + close_fee_usdt), 4)        AS total_fees
FROM  trade_logs
WHERE status = 'CLOSED'
GROUP BY symbol, side
ORDER BY net_pnl DESC;


-- Recent 50 trades (for frontend trade log table)
CREATE OR REPLACE VIEW v_recent_trades AS
SELECT
    id,
    created_at,
    symbol,
    side,
    status,
    strategy,
    leverage,
    entry_price,
    exit_price,
    sl_price,
    tp_price,
    open_fee_usdt,
    close_fee_usdt,
    pnl_gross_usdt,
    pnl_net_usdt,
    pnl_pct,
    hold_time_s,
    close_reason,
    confidence,
    e5_regime,
    error_msg
FROM  trade_logs
ORDER BY created_at DESC
LIMIT 50;