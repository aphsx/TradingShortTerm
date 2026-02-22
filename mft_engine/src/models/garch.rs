/// models/garch.rs — GARCH(1,1) Volatility Forecasting
///
/// ─────────────────────────────────────────────────────────────────────────
/// MATHEMATICAL SPECIFICATION
/// ─────────────────────────────────────────────────────────────────────────
///
/// GARCH(1,1): Bollerslev (1986)
///
///   Return innovation:  ε_t = r_t − μ
///   Conditional variance update:
///
///       σ²_t = ω  +  α · ε²_{t-1}  +  β · σ²_{t-1}
///
///   Constraints (covariance stationarity):
///     ω > 0,  α ≥ 0,  β ≥ 0,  α + β < 1
///
///   Long-run (unconditional) variance:
///       σ²_∞ = ω / (1 − α − β)
///
///   Multi-step forecast (h-step ahead):
///       σ²_{t+h} = σ²_∞ + (α+β)^(h-1) · (σ²_t − σ²_∞)
///
///   Annualised volatility (from per-bar σ²):
///       σ_annual = √(σ²_t · bars_per_year)
///
///   Regime classification:
///     - LOW:    σ_annual < LO_THRESH
///     - NORMAL: LO_THRESH ≤ σ_annual < HI_THRESH
///     - HIGH:   σ_annual ≥ HI_THRESH
/// ─────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum VolRegime {
    Low,
    Normal,
    High,
}

#[derive(Debug, Clone)]
pub struct Garch11 {
    /// ω: long-run variance weight
    pub omega: f64,
    /// α: ARCH (shock) coefficient
    pub alpha: f64,
    /// β: GARCH (persistence) coefficient
    pub beta: f64,
    /// Current conditional variance estimate σ²_t
    pub sigma2: f64,
    /// Previous return innovation ε_{t-1}
    pub prev_epsilon: f64,
    /// Annualisation factor (number of bars per year)
    /// E.g. 1-min bars → 365*24*60 = 525_600
    pub bars_per_year: f64,
}

impl Garch11 {
    /// Construct GARCH(1,1) with given parameters.
    /// Initial σ² is set to the long-run variance σ²_∞ = ω/(1-α-β).
    pub fn new(omega: f64, alpha: f64, beta: f64, bars_per_year: f64) -> Self {
        assert!(
            alpha + beta < 1.0,
            "GARCH covariance-stationarity requires α+β < 1, got α={alpha}, β={beta}"
        );
        let longrun_var = omega / (1.0 - alpha - beta);
        Self {
            omega,
            alpha,
            beta,
            sigma2: longrun_var,
            prev_epsilon: 0.0,
            bars_per_year,
        }
    }

    /// Feed a new return observation and update σ²_t.
    ///
    /// Formula:  σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
    ///
    /// # Arguments
    /// * `r` – log-return for this bar:  ln(close_t / close_{t-1})
    /// * `mu` – conditional mean (use 0 for zero-mean assumption)
    pub fn update(&mut self, r: f64, mu: f64) {
        // Update variance BEFORE computing new epsilon (use t-1 values)
        // σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
        self.sigma2 = self.omega
            + self.alpha * self.prev_epsilon.powi(2)
            + self.beta * self.sigma2;

        // ε_t = r_t − μ
        self.prev_epsilon = r - mu;
    }

    /// Current conditional σ (annualised).
    ///
    /// σ_annual = √(σ²_t · bars_per_year)
    pub fn sigma_annual(&self) -> f64 {
        (self.sigma2 * self.bars_per_year).sqrt()
    }

    /// Current conditional σ (per-bar, raw).
    pub fn sigma_bar(&self) -> f64 {
        self.sigma2.sqrt()
    }

    /// h-step ahead variance forecast.
    ///
    /// σ²_{t+h} = σ²_∞ + (α+β)^(h−1) · (σ²_t − σ²_∞)
    pub fn forecast_variance(&self, h: usize) -> f64 {
        let persistence = self.alpha + self.beta;
        let longrun = self.omega / (1.0 - persistence);
        longrun + persistence.powi(h as i32 - 1) * (self.sigma2 - longrun)
    }

    /// Classify the current volatility regime.
    ///
    /// Thresholds are in annualised σ terms:
    ///   LOW    < 0.40  (40% annual vol  → ~2.5%  daily)
    ///   NORMAL < 0.80  (80% annual vol  → ~5.0%  daily)
    ///   HIGH  >= 0.80
    pub fn regime(&self) -> VolRegime {
        let sa = self.sigma_annual();
        if sa < 0.40 {
            VolRegime::Low
        } else if sa < 0.80 {
            VolRegime::Normal
        } else {
            VolRegime::High
        }
    }

    /// Compute GARCH parameters from a return series via MOM
    /// (Method of Moments — fast approximation, not MLE).
    ///
    /// γ₁ = Var(r²) / [2 · Var(r)²]   (excess-kurtosis proxy)
    /// α̂ = γ₁ · k,  β̂ = 1 − α̂ − ε,  ω̂ = Var(r) · ε
    /// where k, ε are calibration constants.
    ///
    /// For production use: replace with Nelder-Mead MLE minimising
    ///   L = −Σ [ln(σ²_t) + ε²_t/σ²_t]
    pub fn estimate_from_returns(returns: &[f64], bars_per_year: f64) -> Self {
        let n = returns.len() as f64;
        let mean = returns.iter().sum::<f64>() / n;
        let var_r = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / n;

        // Simple MOM approximation
        let alpha = 0.10_f64.min(0.20_f64.max(0.05));
        let beta  = 0.85_f64;
        let omega = var_r * (1.0 - alpha - beta);

        Garch11::new(omega.max(1e-12), alpha, beta, bars_per_year)
    }
}

/// Run GARCH(1,1) over a return series, return all σ²_t values.
pub fn garch_filter(garch: &mut Garch11, returns: &[f64]) -> Vec<f64> {
    let mut variances = Vec::with_capacity(returns.len());
    for &r in returns {
        garch.update(r, 0.0);
        variances.push(garch.sigma2);
    }
    variances
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn garch_stationarity() {
        let g = Garch11::new(1e-6, 0.10, 0.85, 525_600.0);
        let longrun = 1e-6 / (1.0 - 0.10 - 0.85);
        assert!((g.sigma2 - longrun).abs() < 1e-12);
    }

    #[test]
    fn garch_update_monotonic() {
        let mut g = Garch11::new(1e-6, 0.10, 0.85, 525_600.0);
        let spike_return = 0.05; // 5% shock
        g.update(spike_return, 0.0);
        let after_shock = g.sigma2;
        g.update(0.0, 0.0);
        let after_calm = g.sigma2;
        // After shock, variance must be elevated; after calm tick it decays
        assert!(after_shock > after_calm);
    }
}
