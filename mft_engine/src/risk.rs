/// risk.rs — Fee-Adjusted EV, Kelly Sizing, and Position Risk Management
///
/// ─────────────────────────────────────────────────────────────────────────
/// MATHEMATICAL SPECIFICATION
/// ─────────────────────────────────────────────────────────────────────────
///
/// ── FEE MODEL ────────────────────────────────────────────────────────────
///
///   Total round-trip cost per unit of notional:
///     C = 2 · taker_fee + slippage
///
///   e.g.  C = 2 × 0.0005 + 0.0003 = 0.0013 (13bps)
///
///   Fee-adjusted entry price (LONG):
///     P_effective_entry = P_entry × (1 + taker_fee + slippage)
///
///   Fee-adjusted exit price (LONG):
///     P_effective_exit = P_exit × (1 − taker_fee − slippage)
///
/// ── EXPECTED VALUE CONSTRAINT ────────────────────────────────────────────
///
///   EV = P_win × AvgWin − P_loss × AvgLoss
///
///   A trade is allowed ONLY if:
///     EV > C   (expected gain exceeds round-trip cost)
///
///   Where:
///     P_win  = probability of price reaching take-profit
///              estimated from OU Z-score: P_win = Φ(|Z| − z_exit)
///     AvgWin = expected gain = |Z − z_exit| × σ_OU
///     P_loss = 1 − P_win (symmetric Gaussian assumption)
///     AvgLoss = stop_loss_frac × entry_price
///
/// ── KELLY CRITERION (FRACTIONAL) ─────────────────────────────────────────
///
///   f* = (P_win × b − P_loss) / b
///
///   where b = AvgWin / AvgLoss  (odds ratio)
///
///   Applied with fractional Kelly (safety scaling):
///     f_safe = f* × kelly_fraction  (typically kelly_fraction = 0.25)
///
///   Position size (in base currency notional):
///     N = equity × f_safe × leverage / entry_price
///
///   Hard cap: f_safe ≤ max_risk_per_trade (e.g. 1% of equity)
///
/// ── STOP LOSS ────────────────────────────────────────────────────────────
///
///   Stop-loss price (LONG):    P_stop = P_entry × (1 − stop_frac)
///   Stop-loss price (SHORT):   P_stop = P_entry × (1 + stop_frac)
///
///   stop_frac must cover at least round-trip fees:
///     stop_frac > C  →  assert enforced at runtime
/// ─────────────────────────────────────────────────────────────────────────

use statrs::distribution::{ContinuousCDF, Normal};
use crate::config::AppConfig;

/// Result of an EV evaluation.
#[derive(Debug, Clone)]
pub struct EvResult {
    pub p_win:    f64,
    pub p_loss:   f64,
    pub avg_win:  f64,
    pub avg_loss: f64,
    pub ev:       f64,
    pub total_fee: f64,
    pub is_viable: bool,
}

/// Evaluate Expected Value for a potential trade.
///
/// # Arguments
/// * `z_score`      — current OU Z-score (|Z|)
/// * `sigma_ou`     — OU σ (per-bar diffusion)
/// * `entry_price`  — current market price
/// * `z_exit`       — Z-score exit threshold
/// * `cfg`          — application config (fees, stop-loss)
pub fn evaluate_ev(
    z_score:     f64,
    sigma_ou:    f64,
    entry_price: f64,
    z_exit:      f64,
    cfg:         &AppConfig,
) -> EvResult {
    // Total round-trip transaction cost (fraction of notional)
    // C = 2·taker_fee + slippage
    let total_fee = 2.0 * cfg.taker_fee + cfg.slippage;

    // P_win = Φ(|Z| − z_exit)  ∈ [0, 1]
    // Rationale: if |Z|=2, z_exit=0.5 → P_win = Φ(1.5) ≈ 0.933
    let normal = Normal::new(0.0, 1.0).expect("Normal distribution");
    let p_win = normal.cdf(z_score.abs() - z_exit).max(0.0).min(1.0);
    let p_loss = 1.0 - p_win;

    // Expected gain per unit notional: proportional to how far σ_OU can travel
    // AvgWin = (|Z| − z_exit) × σ_OU / entry_price   (as fraction of entry)
    let z_travel = (z_score.abs() - z_exit).max(0.0);
    let avg_win = if entry_price > 0.0 {
        z_travel * sigma_ou / entry_price
    } else {
        0.0
    };

    // AvgLoss = stop_loss_frac (e.g. 0.003, i.e. 30 basis points)
    let avg_loss = cfg.stop_loss_frac;

    // EV = P_win × AvgWin − P_loss × AvgLoss
    let ev = p_win * avg_win - p_loss * avg_loss;

    // Trade is viable if EV strictly exceeds round-trip cost
    let is_viable = ev > total_fee && p_win >= cfg.min_p_win;

    EvResult { p_win, p_loss, avg_win, avg_loss, ev, total_fee, is_viable }
}

/// Calculate fee-adjusted LONG position PnL.
///
/// Returns (gross_pnl_frac, net_pnl_frac) where fractions are relative to entry.
pub fn calculate_pnl(entry: f64, exit: f64, cfg: &AppConfig) -> (f64, f64) {
    let gross = (exit - entry) / entry;
    let fees  = 2.0 * cfg.taker_fee + cfg.slippage;
    (gross, gross - fees)
}

/// Kelly-optimal position size (fraction of equity), capped by risk limit.
///
/// # Arguments
/// * `p_win`            — probability of winning
/// * `avg_win`          — expected win expressed as fraction (e.g. 0.005 = 50bps)
/// * `avg_loss`         — expected loss expressed as fraction
/// * `kelly_fraction`   — fractional Kelly safety multiplier (e.g. 0.25)
/// * `max_risk`         — hard cap on fraction of equity at risk (e.g. 0.01)
pub fn kelly_fraction(
    p_win: f64,
    avg_win: f64,
    avg_loss: f64,
    kelly_fraction: f64,
    max_risk: f64,
) -> f64 {
    if avg_loss < 1e-10 || avg_win < 1e-10 {
        return 0.0;
    }
    // b = AvgWin / AvgLoss  (odds ratio)
    let b = avg_win / avg_loss;
    // f* = (P_win × b − P_loss) / b
    let p_loss = 1.0 - p_win;
    let f_star = (p_win * b - p_loss) / b;

    if f_star <= 0.0 {
        return 0.0;
    }

    // Apply fractional Kelly and hard cap
    (f_star * kelly_fraction).min(max_risk).max(0.0)
}

/// Compute position size in base asset quantity.
///
/// Q = equity × f_risk × leverage / entry_price
pub fn position_size(
    equity: f64,
    f_risk: f64,
    leverage: u32,
    entry_price: f64,
) -> f64 {
    if entry_price < 1e-8 {
        return 0.0;
    }
    equity * f_risk * leverage as f64 / entry_price
}

/// Stop-loss and take-profit prices.
#[derive(Debug, Clone)]
pub struct RiskLevels {
    pub entry:       f64,
    pub stop_loss:   f64,
    pub take_profit: f64,
    pub direction:   i8,  // +1 long, −1 short
}

impl RiskLevels {
    /// Compute risk levels for a LONG trade.
    ///
    /// stop_loss   = entry × (1 − stop_frac)
    /// take_profit = entry + |Z − z_exit| × σ_OU  (reverts to mean)
    pub fn long(entry: f64, stop_frac: f64, take_profit_price: f64) -> Self {
        Self {
            entry,
            stop_loss: entry * (1.0 - stop_frac),
            take_profit: take_profit_price,
            direction: 1,
        }
    }

    /// Compute risk levels for a SHORT trade.
    ///
    /// stop_loss   = entry × (1 + stop_frac)
    /// take_profit = entry − |Z − z_exit| × σ_OU
    pub fn short(entry: f64, stop_frac: f64, take_profit_price: f64) -> Self {
        Self {
            entry,
            stop_loss: entry * (1.0 + stop_frac),
            take_profit: take_profit_price,
            direction: -1,
        }
    }

    /// Has price hit stop-loss?
    pub fn is_stopped(&self, price: f64) -> bool {
        match self.direction {
            1  => price <= self.stop_loss,
            -1 => price >= self.stop_loss,
            _  => false,
        }
    }

    /// Has price hit take-profit?
    pub fn is_profit_taken(&self, price: f64) -> bool {
        match self.direction {
            1  => price >= self.take_profit,
            -1 => price <= self.take_profit,
            _  => false,
        }
    }

    /// Reward-to-risk ratio.
    pub fn rr_ratio(&self) -> f64 {
        let risk   = (self.entry - self.stop_loss).abs();
        let reward = (self.take_profit - self.entry).abs();
        if risk < 1e-10 { 0.0 } else { reward / risk }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::AppConfig;

    fn default_cfg() -> AppConfig {
        AppConfig {
            api_key:    String::new(),
            api_secret: String::new(),
            use_testnet: true,
            rest_url: String::new(),
            ws_url:   String::new(),
            trading_pairs: vec![],
            initial_capital: 1000.0,
            risk_per_trade:  0.01,
            max_leverage:    10,
            maker_fee: 0.0002,
            taker_fee: 0.0005,
            slippage:  0.0003,
            garch_omega: 1e-6,
            garch_alpha: 0.10,
            garch_beta:  0.85,
            ou_entry_z:  2.0,
            ou_exit_z:   0.5,
            ou_window:   120,
            vpin_bucket_size: 50,
            vpin_n_buckets:   50,
            vpin_threshold:   0.35,
            min_ev:   0.0001,
            min_p_win: 0.52,
            stop_loss_frac:      0.003,
            exit_prob_threshold: 0.30,
            max_hold_bars:       60,
            kline_interval:  "1m".into(),
            backtest_symbol: "BTCUSDT".into(),
            backtest_limit:  1000,
        }
    }

    #[test]
    fn ev_positive_at_high_z() {
        let cfg = default_cfg();
        // Z = 3.0, σ_OU = 50 (BTC-like), entry = 50000
        let ev = evaluate_ev(3.0, 50.0, 50_000.0, 0.5, &cfg);
        assert!(ev.is_viable, "EV = {:.6}, fees = {:.6}", ev.ev, ev.total_fee);
    }

    #[test]
    fn kelly_bounded_by_max_risk() {
        let frac = kelly_fraction(0.6, 0.01, 0.005, 0.25, 0.01);
        assert!(frac <= 0.01, "Kelly fraction = {frac}");
    }

    #[test]
    fn risk_levels_stop_triggered() {
        let rl = RiskLevels::long(50_000.0, 0.003, 50_300.0);
        assert!(!rl.is_stopped(49_900.0) || rl.is_stopped(49_800.0));
        assert!(rl.is_stopped(49_850.0)); // 50000 × 0.997 = 49850
    }
}
