/// metrics.rs — Performance Metrics
///
/// ─────────────────────────────────────────────────────────────────────────
/// MATHEMATICAL SPECIFICATION
/// ─────────────────────────────────────────────────────────────────────────
///
/// SHARPE RATIO (annualised)
///   Used for: overall risk-adjusted return
///
///   r̄  = mean(period returns)
///   σ_r = std(period returns)
///   SR  = (r̄ − r_f) / σ_r × √N_annual
///
///   where r_f = risk-free rate (0 for crypto), N_annual = periods per year.
///   Higher is better; SR > 1.0 is acceptable, > 2.0 is excellent.
///
/// SORTINO RATIO (annualised)
///   Used for: penalises only DOWNSIDE volatility
///
///   r̄_downside = mean(negative returns only)
///   σ_d = √(mean(min(r_t, 0)²))   (downside deviation)
///   SoR = (r̄ − r_f) / σ_d × √N_annual
///
/// MAXIMUM DRAWDOWN
///   Used for: worst-case scenario; key constraint for investors
///
///   Equity curve: E_t
///   Running peak: peak_t = max_{s ≤ t}(E_s)
///   Drawdown at t: DD_t = (E_t − peak_t) / peak_t
///   MaxDD = min_{t}(DD_t)   (most negative)
///
/// CALMAR RATIO
///   Calmar = CAGR / |MaxDD|
///   Useful when comparing strategies with different drawdown profiles.
///
/// WIN RATE & AVERAGE TRADE
///   P_win  = count(winners) / N_trades
///   AvgWin = mean(return | positive)
///   AvgLoss= mean(|return| | negative)
///   Profit Factor = (P_win × AvgWin) / (P_loss × |AvgLoss|)
/// ─────────────────────────────────────────────────────────────────────────

use crate::strategy::ActivePosition;

/// Complete backtest performance report.
#[derive(Debug, Clone)]
pub struct PerfReport {
    pub n_trades:       usize,
    pub win_rate:       f64,
    pub avg_win:        f64,  // fraction
    pub avg_loss:       f64,  // fraction
    pub profit_factor:  f64,
    pub total_return:   f64,  // fraction of initial capital
    pub sharpe:         f64,
    pub sortino:        f64,
    pub max_drawdown:   f64,  // fraction (negative)
    pub calmar:         f64,
    pub initial_equity: f64,
    pub final_equity:   f64,
}

impl std::fmt::Display for PerfReport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(f, "════════════════════════════════════════════")?;
        writeln!(f, "  MFT ENGINE — BACKTEST PERFORMANCE REPORT")?;
        writeln!(f, "════════════════════════════════════════════")?;
        writeln!(f, "  Trades         : {}", self.n_trades)?;
        writeln!(f, "  Win Rate       : {:.2}%", self.win_rate * 100.0)?;
        writeln!(f, "  Avg Win        : {:.4}%", self.avg_win * 100.0)?;
        writeln!(f, "  Avg Loss       : {:.4}%", self.avg_loss * 100.0)?;
        writeln!(f, "  Profit Factor  : {:.3}", self.profit_factor)?;
        writeln!(f, "  Total Return   : {:.2}%", self.total_return * 100.0)?;
        writeln!(f, "  Sharpe Ratio   : {:.3}", self.sharpe)?;
        writeln!(f, "  Sortino Ratio  : {:.3}", self.sortino)?;
        writeln!(f, "  Max Drawdown   : {:.2}%", self.max_drawdown * 100.0)?;
        writeln!(f, "  Calmar Ratio   : {:.3}", self.calmar)?;
        writeln!(f, "  Initial Equity : ${:.2}", self.initial_equity)?;
        writeln!(f, "  Final Equity   : ${:.2}", self.final_equity)?;
        writeln!(f, "════════════════════════════════════════════")
    }
}

/// Compute all performance metrics from a list of closed trades and equity curve.
///
/// # Arguments
/// * `trades`        — completed position records with pnl_frac set
/// * `equity_curve`  — equity at each bar (for drawdown calculation)
/// * `initial_equity`— starting equity
/// * `final_equity`  — ending equity
/// * `bars_per_year` — annualisation factor
pub fn compute_metrics(
    trades:         &[ActivePosition],
    equity_curve:   &[f64],
    initial_equity: f64,
    final_equity:   f64,
    bars_per_year:  f64,
) -> PerfReport {
    let n = trades.len();
    if n == 0 {
        return PerfReport {
            n_trades: 0, win_rate: 0.0, avg_win: 0.0, avg_loss: 0.0,
            profit_factor: 0.0, total_return: 0.0, sharpe: 0.0,
            sortino: 0.0, max_drawdown: 0.0, calmar: 0.0,
            initial_equity, final_equity,
        };
    }

    // ── Per-trade statistics ──────────────────────────────────────────────
    let returns: Vec<f64> = trades.iter()
        .filter_map(|t| t.pnl_frac)
        .collect();

    let winners: Vec<f64> = returns.iter().filter(|&&r| r > 0.0).cloned().collect();
    let losers:  Vec<f64> = returns.iter().filter(|&&r| r <= 0.0).cloned().collect();

    let win_rate  = winners.len() as f64 / n as f64;
    let avg_win   = mean(&winners).unwrap_or(0.0);
    let avg_loss  = mean(&losers.iter().map(|x| x.abs()).collect::<Vec<_>>()).unwrap_or(0.0);
    let p_loss    = 1.0 - win_rate;

    let profit_factor = if p_loss * avg_loss < 1e-10 {
        f64::INFINITY
    } else {
        win_rate * avg_win / (p_loss * avg_loss)
    };

    let total_return = (final_equity - initial_equity) / initial_equity;

    // ── Sharpe Ratio ──────────────────────────────────────────────────────
    //   SR = mean(r) / std(r) × √N_annual
    let r_mean = mean(&returns).unwrap_or(0.0);
    let r_std  = std_dev(&returns);
    let sharpe = if r_std < 1e-12 {
        0.0
    } else {
        // Scale by √N_annual where N = bars_per_year / avg_hold_bars
        // Approximation: treat each trade as independent return
        (r_mean / r_std) * (bars_per_year / n as f64).sqrt()
    };

    // ── Sortino Ratio ─────────────────────────────────────────────────────
    //   σ_d = √(mean(min(r, 0)²))
    let downside_sq: Vec<f64> = returns.iter()
        .map(|&r| if r < 0.0 { r * r } else { 0.0 })
        .collect();
    let sigma_d = (mean(&downside_sq).unwrap_or(0.0)).sqrt();
    let sortino = if sigma_d < 1e-12 {
        f64::INFINITY
    } else {
        (r_mean / sigma_d) * (bars_per_year / n as f64).sqrt()
    };

    // ── Maximum Drawdown ──────────────────────────────────────────────────
    //   MaxDD = min_t { (E_t − peak_t) / peak_t }
    let max_drawdown = max_drawdown(equity_curve);

    // ── Calmar Ratio ──────────────────────────────────────────────────────
    //   Assuming simulation period ≈ n_trades periods of avg_hold_bars
    let calmar = if max_drawdown.abs() < 1e-10 {
        f64::INFINITY
    } else {
        total_return / max_drawdown.abs()
    };

    PerfReport {
        n_trades: n,
        win_rate,
        avg_win,
        avg_loss,
        profit_factor,
        total_return,
        sharpe,
        sortino,
        max_drawdown,
        calmar,
        initial_equity,
        final_equity,
    }
}

/// Maximum drawdown from an equity curve.
/// Returns a negative value (e.g. −0.15 = −15% drawdown).
pub fn max_drawdown(equity_curve: &[f64]) -> f64 {
    if equity_curve.is_empty() {
        return 0.0;
    }
    let mut peak = equity_curve[0];
    let mut max_dd = 0.0f64;

    for &e in equity_curve {
        if e > peak {
            peak = e;
        }
        let dd = (e - peak) / peak;
        if dd < max_dd {
            max_dd = dd;
        }
    }
    max_dd
}

// ── Statistical helpers ───────────────────────────────────────────────────

fn mean(data: &[f64]) -> Option<f64> {
    if data.is_empty() {
        return None;
    }
    Some(data.iter().sum::<f64>() / data.len() as f64)
}

fn std_dev(data: &[f64]) -> f64 {
    if data.len() < 2 {
        return 0.0;
    }
    let m = data.iter().sum::<f64>() / data.len() as f64;
    let var = data.iter().map(|x| (x - m).powi(2)).sum::<f64>() / (data.len() - 1) as f64;
    var.sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn max_drawdown_flat() {
        let curve = vec![100.0, 100.0, 100.0];
        assert_eq!(max_drawdown(&curve), 0.0);
    }

    #[test]
    fn max_drawdown_50_pct() {
        let curve = vec![100.0, 120.0, 60.0, 80.0];
        // peak=120, low=60 → DD = (60−120)/120 = −0.5
        let dd = max_drawdown(&curve);
        assert!((dd + 0.5).abs() < 1e-9, "dd = {dd}");
    }
}
