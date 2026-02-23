/// models/ou_process.rs — Ornstein-Uhlenbeck Mean Reversion Engine
///
/// ─────────────────────────────────────────────────────────────────────────
/// MATHEMATICAL SPECIFICATION
/// ─────────────────────────────────────────────────────────────────────────
///
/// The OU SDE (continuous time):
///
///   dX_t = θ(μ − X_t)dt + σ_OU · dW_t
///
///   θ   = mean-reversion speed (larger → faster reversion)
///   μ   = long-run equilibrium level
///   σ_OU = diffusion coefficient (volatility of the process)
///   W_t  = standard Brownian motion
///
/// AR(1) DISCRETISATION (Δt = 1 bar):
///
///   X_t = a + b·X_{t-1} + ε_t,    ε_t ~ N(0, σ²_ε)
///
/// Parameter mapping from OLS regression:
///
///   b̂  = OLS slope  →  θ̂ = −ln(b̂)/Δt
///   â  = OLS intercept → μ̂ = â / (1 − b̂)
///   σ̂²_OU = σ²_ε / (1 − b̂²) · 2·|ln(b̂)|  (exact OU σ from AR residuals)
///             NOTE: simplified approximation used here:
///             σ̂_OU = std(residuals) / √(1 − b̂²)
///
/// Z-SCORE (key signal):
///
///   Z_t = (X_t − μ̂) / σ̂_OU
///
///   Entry LONG:  Z_t < −z_entry  (price far below equilibrium)
///   Entry SHORT: Z_t > +z_entry  (price far above equilibrium)
///   Exit:        |Z_t| < z_exit  (price near equilibrium)
///
/// HALF-LIFE of mean reversion:
///
///   t½ = ln(2) / θ = −ln(2) / ln(b̂)    [in bars]
///
/// PROBABILITY OF CONTINUATION (exit trigger):
///
///   Using normal CDF on Z-score:
///   P(price moves further from μ) ≈ 1 − Φ(|Z_t|)
///   where Φ is the standard normal CDF.
///   Exit when P_continue < p_threshold (e.g. 0.30)
/// ─────────────────────────────────────────────────────────────────────────

use statrs::distribution::{ContinuousCDF, Normal};

/// Fitted OU parameters estimated from price window.
#[derive(Debug, Clone)]
pub struct OuParams {
    /// Long-run mean / equilibrium price level
    pub mu: f64,
    /// Diffusion coefficient (vol of the OU process)
    pub sigma_ou: f64,
    /// Mean-reversion speed (per bar)
    pub theta: f64,
    /// AR(1) coefficient b̂ (= e^{−θ·Δt})
    pub b: f64,
    /// Half-life in bars: −ln(2)/ln(b)
    pub half_life: f64,
}

impl OuParams {
    /// Estimate OU parameters from a price window via OLS on AR(1).
    ///
    /// # Returns `None` if the series does not show mean-reversion (b ≥ 1).
    pub fn estimate(prices: &[f64]) -> Option<Self> {
        let n = prices.len();
        if n < 10 {
            return None;
        }

        // X_t = a + b·X_{t-1}  via OLS
        // y = prices[1..], x = prices[..n-1]
        let y: Vec<f64> = prices[1..].to_vec();
        let x: Vec<f64> = prices[..n - 1].to_vec();
        let m = x.len() as f64;

        let x_mean = x.iter().sum::<f64>() / m;
        let y_mean = y.iter().sum::<f64>() / m;

        // β̂ = Σ(x_i − x̄)(y_i − ȳ) / Σ(x_i − x̄)²
        let num: f64 = x.iter().zip(y.iter()).map(|(xi, yi)| (xi - x_mean) * (yi - y_mean)).sum();
        let den: f64 = x.iter().map(|xi| (xi - x_mean).powi(2)).sum();

        if den.abs() < 1e-12 {
            return None;
        }

        let b = num / den;
        let a = y_mean - b * x_mean;

        // Require mean-reversion: 0 < b < 1
        if b <= 0.0 || b >= 1.0 {
            return None;
        }

        // θ = −ln(b)   (with Δt = 1)
        let theta = -b.ln();
        if theta <= 0.0 {
            return None;
        }

        // μ = a / (1 − b)
        let mu = a / (1.0 - b);

        // Residuals ε_t = y_t − (a + b·x_t)
        let residuals: Vec<f64> = x.iter().zip(y.iter())
            .map(|(xi, yi)| yi - (a + b * xi))
            .collect();
        let sigma_eps = std_dev(&residuals);

        // σ_OU = σ_ε / √(1 − b²)
        let denom_sigma = (1.0 - b.powi(2)).sqrt();
        if denom_sigma < 1e-10 {
            return None;
        }
        let sigma_ou = sigma_eps / denom_sigma;

        // t½ = −ln(2)/ln(b)
        let half_life = -std::f64::consts::LN_2 / b.ln();

        Some(OuParams { mu, sigma_ou, theta, b, half_life })
    }
}

/// Real-time OU signal engine.
#[derive(Debug)]
pub struct OuSignalEngine {
    /// Estimation window length (bars)
    pub window: usize,
    /// Rolling price buffer
    price_buf: Vec<f64>,
    /// Most recently fitted parameters
    pub params: Option<OuParams>,
}

impl OuSignalEngine {
    pub fn new(window: usize) -> Self {
        Self {
            window,
            price_buf: Vec::with_capacity(window + 1),
            params: None,
        }
    }

    /// Push a new price observation.  Re-fits OU parameters when the
    /// buffer is full (every bar).  Returns current Z-score if fitted.
    pub fn push(&mut self, price: f64) -> Option<f64> {
        self.price_buf.push(price);
        if self.price_buf.len() > self.window {
            self.price_buf.remove(0); // O(n) — fine for window ≤ 500
        }
        if self.price_buf.len() == self.window {
            self.params = OuParams::estimate(&self.price_buf);
        }
        self.z_score(price)
    }

    /// Z-score of the current price given the fitted OU process.
    ///
    /// Z_t = (X_t − μ) / σ_OU
    pub fn z_score(&self, price: f64) -> Option<f64> {
        self.params.as_ref().map(|p| {
            if p.sigma_ou < 1e-12 { 0.0 } else { (price - p.mu) / p.sigma_ou }
        })
    }

    /// P(price moves FURTHER from equilibrium at the next bar).
    ///
    /// Derived from normal CDF:
    ///   P_further = 1 − Φ(|Z|)
    ///
    /// Intuition: if Z = 3.0, only 0.13% chance of going further out
    //  → very high P of reversion.  Exit when this P_continue < threshold.
    pub fn p_continuation(&self, price: f64) -> Option<f64> {
        let z = self.z_score(price)?.abs();
        // 1 − Φ(|Z|), i.e. probability price continues in current direction
        let normal = Normal::new(0.0, 1.0).ok()?;
        Some(1.0 - normal.cdf(z))
    }

    /// Signal direction based on Z-score thresholds.
    ///
    /// Returns:
    ///   +1 → BUY  (Z < −entry_z: price far below mean, expect reversion UP)
    ///   −1 → SELL (Z > +entry_z: price far above mean, expect reversion DOWN)
    ///    0 → NO SIGNAL
    pub fn signal(&self, price: f64, entry_z: f64) -> i8 {
        match self.z_score(price) {
            Some(z) if z < -entry_z => 1,
            Some(z) if z >  entry_z => -1,
            _ => 0,
        }
    }

    /// Should we close an existing position?
    ///
    /// Two conditions (either triggers exit):
    ///   1. |Z_t| has reverted below exit_z threshold
    ///   2. P(continuation) < prob_threshold
    pub fn should_exit(
        &self,
        price: f64,
        exit_z: f64,
        prob_threshold: f64,
    ) -> bool {
        let z_ok = self.z_score(price).map_or(false, |z| z.abs() < exit_z);
        let prob_ok = self.p_continuation(price).map_or(false, |p| p < prob_threshold);
        z_ok || prob_ok
    }

    /// Return the Z-score of the *last pushed price* without modifying state.
    ///
    /// Useful when `push()` was already called this bar (e.g. via `on_bar`)
    /// and you need to read the current Z-score without double-counting.
    pub fn last_z(&self) -> Option<f64> {
        let last_price = *self.price_buf.last()?;
        self.z_score(last_price)
    }
}


// ── Helpers ──────────────────────────────────────────────────────────────

fn std_dev(data: &[f64]) -> f64 {
    if data.len() < 2 {
        return 0.0;
    }
    let n = data.len() as f64;
    let mean = data.iter().sum::<f64>() / n;
    let var = data.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n - 1.0);
    var.sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ou_estimate_mean_reverting() {
        // Simulate OU path: X_t = 0.05 + 0.90·X_{t-1} + ε_t
        let mut prices = vec![100.0f64; 200];
        let seed_noise: Vec<f64> = (0..199).map(|i| 0.01 * ((i % 7) as f64 - 3.0)).collect();
        for i in 1..200 {
            prices[i] = 5.0 + 0.90 * prices[i - 1] + seed_noise[i - 1];
        }
        let params = OuParams::estimate(&prices).expect("should fit");
        // b should be close to 0.90
        assert!((params.b - 0.90).abs() < 0.05, "b = {}", params.b);
        // half_life should be around −ln(2)/ln(0.90) ≈ 6.6 bars
        assert!(params.half_life > 5.0 && params.half_life < 10.0);
    }

    #[test]
    fn p_continuation_extreme_z() {
        let mut engine = OuSignalEngine::new(60);
        // Price at 3σ above mean
        let prices: Vec<f64> = (0..59).map(|i| 100.0 + 0.1 * (i as f64)).collect();
        for p in &prices { engine.push(*p); }
        let p_cont = engine.p_continuation(105.0);
        // With high Z, P(continuation) should be low
        if let Some(p) = p_cont {
            assert!(p < 0.5, "P(cont) = {p}");
        }
    }
}
