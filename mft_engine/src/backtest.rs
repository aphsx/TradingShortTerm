/// backtest.rs — Event-Driven Backtesting Engine
///
/// Processes kline bars in chronological order, passing each bar through the
/// full strategy pipeline.  Records equity curve and closed trades for
/// metrics computation.
///
/// ARCHITECTURE
/// ┌─────────────────────────────────────────────────────┐
/// │  Bar Feed (Vec<Kline>)                              │
/// │        │                                            │
/// │        ▼                                            │
/// │  [on_bar(price, log_return, tick)]                  │
/// │        │                                            │
/// │   ┌────┴──────────────────────────────────┐        │
/// │   │  StrategyEngine                       │        │
/// │   │  ├─ GARCH.update(log_return)          │        │
/// │   │  ├─ OU.push(price) → Z-score          │        │
/// │   │  ├─ FlowAnalyser.process(tick) → OFI  │        │
/// │   │  ├─ check_exit(existing pos)           │        │
/// │   │  └─ evaluate_entry → TradeSignal?      │        │
/// │   └────────────────────────────────────────┘        │
/// │        │                                            │
/// │   open_position() / close_position()               │
/// │        │                                            │
/// │   equity_curve[t] = engine.equity                  │
/// └─────────────────────────────────────────────────────┘

use tracing::info;

use crate::config::AppConfig;
use crate::data::Kline;
use crate::metrics::{compute_metrics, PerfReport};
use crate::strategy::StrategyEngine;

/// Backtest configuration / run parameters (separate from strategy config).
#[derive(Debug, Clone)]
pub struct BacktestConfig {
    /// Log every signal (true) or only summary (false)
    pub verbose: bool,
    /// Bars per year (for annualisation in metrics)
    pub bars_per_year: f64,
}

impl Default for BacktestConfig {
    fn default() -> Self {
        Self { verbose: false, bars_per_year: 525_600.0 }
    }
}

/// Run a complete backtest over a kline series.
///
/// Returns the final PerfReport with all metrics.
pub fn run_backtest(
    klines: &[Kline],
    cfg:    AppConfig,
    bt_cfg: BacktestConfig,
) -> PerfReport {
    if klines.len() < 2 {
        panic!("Backtest requires at least 2 bars");
    }

    let initial_equity = cfg.initial_capital;
    let mut engine = StrategyEngine::new(cfg);
    let mut equity_curve: Vec<f64> = Vec::with_capacity(klines.len());

    info!(
        "═══════════════════════════════════════════════"
    );
    info!("  MFT ENGINE BACKTEST  — {} bars", klines.len());
    info!(
        "═══════════════════════════════════════════════"
    );

    // ── Main event loop ───────────────────────────────────────────────────
    for (i, bar) in klines.iter().enumerate() {
        // Need previous bar for log-return
        if i == 0 {
            equity_curve.push(engine.equity);
            continue;
        }

        let prev_close = klines[i - 1].close;
        let log_return = if prev_close > 0.0 {
            (bar.close / prev_close).ln()
        } else {
            0.0
        };

        // Convert bar to synthetic tick (uses taker buy/sell split)
        let tick = bar.to_tick();

        // ── Strategy decision ─────────────────────────────────────────────
        if let Some(signal) = engine.on_bar(bar.close, log_return, &tick) {
            if bt_cfg.verbose {
                info!(
                    "  [Bar {:>5}] OPEN {:>5} @ {:.2}  Z={:.3}  EV={:.5}  VPIN={:.3}",
                    i,
                    if signal.direction == 1 { "LONG" } else { "SHORT" },
                    signal.entry_price,
                    signal.z_score,
                    signal.ev,
                    signal.vpin.unwrap_or(0.0)
                );
            }
            engine.open_position(signal);
        }

        // Record equity AFTER processing bar
        equity_curve.push(engine.equity);
    }

    // ── Force-close any remaining open position at last price ─────────────
    if engine.position.is_some() {
        let last_price = klines.last().map(|k| k.close).unwrap_or(0.0);
        engine.close_position(last_price, crate::strategy::ExitReason::ManualClose);
    }

    // ── Compute metrics ───────────────────────────────────────────────────
    let final_equity = engine.equity;
    let closed = engine.closed_trades.clone();
    let report = compute_metrics(
        &closed,
        &equity_curve,
        initial_equity,
        final_equity,
        bt_cfg.bars_per_year,
    );

    info!("{}", report);
    report
}

/// Log a summary table of all closed trades (top N by absolute PnL).
pub fn print_trade_log(
    trades: &[crate::strategy::ActivePosition],
    top_n:  usize,
) {
    println!(
        "\n{:<6} {:<7} {:<12} {:<8} {:<10} {:<8}",
        "N", "DIR", "ENTRY", "Z-SCR", "PNL%", "EXIT"
    );
    println!("{}", "─".repeat(55));

    for (i, t) in trades.iter().enumerate().take(top_n) {
        let pnl = t.pnl_frac.unwrap_or(0.0) * 100.0;
        let exit = t.exit_reason.as_ref()
            .map(|r| format!("{:?}", r))
            .unwrap_or_else(|| "?".into());
        println!(
            "{:<6} {:<7} {:<12.2} {:<8.3} {:<+10.4} {:<8}",
            i + 1,
            if t.signal.direction == 1 { "LONG" } else { "SHORT" },
            t.signal.entry_price,
            t.signal.z_score,
            pnl,
            exit,
        );
    }
}
