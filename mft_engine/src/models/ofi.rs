/// models/ofi.rs — Order Flow Imbalance (OFI) and VPIN
///
/// ─────────────────────────────────────────────────────────────────────────
/// MATHEMATICAL SPECIFICATION
/// ─────────────────────────────────────────────────────────────────────────
///
/// ORDER FLOW IMBALANCE (OFI)
/// Based on: Cont, Kukanov, Stoikov (2014) — "The Price Impact of Order Book Events"
///
///   For each trade tick:
///     Signed volume:  v_t^+ = volume  if buyer-initiated
///                     v_t^− = volume  if seller-initiated
///
///   OFI over rolling window W:
///     OFI_W = Σ_{t∈W} (v_t^+ − v_t^−) / Σ_{t∈W} (v_t^+ + v_t^−)
///
///   Interpretation:
///     OFI ∈ [−1, +1]
///     OFI → +1: overwhelming buy pressure (momentum long signal)
///     OFI → −1: overwhelming sell pressure (momentum short signal)
///     |OFI| < threshold: balanced, no signal
///
///   OFI velocity (rate-of-change over two windows):
///     ΔOFI = OFI_{W_fast} − OFI_{W_slow}
///     High |ΔOFI| = accelerating order flow imbalance = stronger signal.
///
/// VOLUME-SYNCHRONISED PROBABILITY OF INFORMED TRADING (VPIN)
/// Based on: Easley, López de Prado, O'Hara (2012)
///
///   1. Partition total volume into N equal-size "volume buckets" of size V_B.
///   2. Within each bucket k, classify trades as buy (V_b^k) or sell (V_s^k).
///      Approximation: use tick rule (price up → buy; price down → sell).
///   3. VPIN over last τ buckets:
///
///       VPIN = (1/τ) · Σ_{k=t-τ+1}^{t} |V_b^k − V_s^k| / V_B
///
///   Interpretation:
///     VPIN → 1: high informed trading activity → large imminent price move
///     VPIN → 0: pure noise / uninformed flow → low short-term signal
///
///   Entry filter: require VPIN > threshold before acting on OU signal.
/// ─────────────────────────────────────────────────────────────────────────

use std::collections::VecDeque;

/// A single trade tick from the exchange.
#[derive(Debug, Clone)]
pub struct TradeTick {
    /// Trade price
    pub price:  f64,
    /// Trade volume (base asset)
    pub volume: f64,
    /// True = buyer initiated (aggressor = buyer)
    pub is_buy: bool,
    /// Unix timestamp in milliseconds
    pub ts_ms:  i64,
}

// ── ORDER FLOW IMBALANCE ─────────────────────────────────────────────────

/// Rolling Order Flow Imbalance calculator.
#[derive(Debug)]
pub struct OfiEngine {
    /// Rolling window length (number of ticks)
    window: usize,
    /// Signed-volume buffer: positive = buy, negative = sell
    signed_vol_buf: VecDeque<f64>,
    /// Absolute-volume buffer
    abs_vol_buf:    VecDeque<f64>,
    /// Accumulated signed volume
    sum_signed: f64,
    /// Accumulated absolute volume
    sum_abs:    f64,
}

impl OfiEngine {
    pub fn new(window: usize) -> Self {
        Self {
            window,
            signed_vol_buf: VecDeque::with_capacity(window),
            abs_vol_buf:    VecDeque::with_capacity(window),
            sum_signed: 0.0,
            sum_abs:    0.0,
        }
    }

    /// Push a new tick and return current OFI.
    ///
    /// OFI = Σ signed_vol / Σ |vol|   ∈ [−1, +1]
    pub fn push(&mut self, tick: &TradeTick) -> f64 {
        let signed = if tick.is_buy { tick.volume } else { -tick.volume };
        let abs    = tick.volume;

        self.signed_vol_buf.push_back(signed);
        self.abs_vol_buf.push_back(abs);
        self.sum_signed += signed;
        self.sum_abs    += abs;

        // Evict oldest element if window exceeded
        if self.signed_vol_buf.len() > self.window {
            let old_signed = self.signed_vol_buf.pop_front().unwrap_or(0.0);
            let old_abs    = self.abs_vol_buf.pop_front().unwrap_or(0.0);
            self.sum_signed -= old_signed;
            self.sum_abs    -= old_abs;
        }

        self.ofi()
    }

    /// Current OFI value.  Returns 0 when no data.
    pub fn ofi(&self) -> f64 {
        if self.sum_abs < 1e-12 {
            return 0.0;
        }
        self.sum_signed / self.sum_abs
    }

    /// Number of ticks stored.
    pub fn len(&self) -> usize {
        self.signed_vol_buf.len()
    }

    pub fn is_full(&self) -> bool {
        self.len() >= self.window
    }
}

// ── VPIN ─────────────────────────────────────────────────────────────────

/// Volume bucket for VPIN calculation.
#[derive(Debug, Clone, Default)]
struct VpinBucket {
    buy_vol:  f64,
    sell_vol: f64,
    total:    f64,
}

impl VpinBucket {
    fn imbalance_frac(&self) -> f64 {
        if self.total < 1e-12 {
            return 0.0;
        }
        (self.buy_vol - self.sell_vol).abs() / self.total
    }
}

/// VPIN estimator.
///
/// Maintains volume buckets of fixed size; each tick fills the current
/// bucket.  When a bucket is full it rolls into the VPIN window.
#[derive(Debug)]
pub struct VpinEngine {
    /// Volume per bucket V_B
    bucket_size: f64,
    /// Number of buckets in rolling window τ
    n_buckets: usize,
    /// Current (open) bucket being filled
    current_bucket: VpinBucket,
    /// Volume accumulated into current bucket so far
    current_vol: f64,
    /// Completed buckets (rolling, length = n_buckets)
    finished_buckets: VecDeque<VpinBucket>,
    /// Last known price for tick-rule classification fallback
    last_price: f64,
}

impl VpinEngine {
    pub fn new(bucket_size: f64, n_buckets: usize) -> Self {
        Self {
            bucket_size,
            n_buckets,
            current_bucket: VpinBucket::default(),
            current_vol: 0.0,
            finished_buckets: VecDeque::with_capacity(n_buckets),
            last_price: 0.0,
        }
    }

    /// Feed a tick.  Returns VPIN if at least one bucket is complete.
    ///
    /// A tick may *span* a bucket boundary; in that case volume is split
    /// proportionally between the closing and opening buckets.
    pub fn push(&mut self, tick: &TradeTick) -> Option<f64> {
        let is_buy = tick.is_buy;
        let mut remaining_vol = tick.volume;

        while remaining_vol > 1e-10 {
            let space = self.bucket_size - self.current_vol;
            let fill  = remaining_vol.min(space);

            if is_buy {
                self.current_bucket.buy_vol  += fill;
            } else {
                self.current_bucket.sell_vol += fill;
            }
            self.current_bucket.total += fill;
            self.current_vol          += fill;
            remaining_vol             -= fill;

            if self.current_vol >= self.bucket_size - 1e-10 {
                // Bucket is full — move to completed window
                let closed = std::mem::take(&mut self.current_bucket);
                self.finished_buckets.push_back(closed);
                if self.finished_buckets.len() > self.n_buckets {
                    self.finished_buckets.pop_front();
                }
                self.current_bucket = VpinBucket::default();
                self.current_vol    = 0.0;
            }
        }

        self.last_price = tick.price;

        if self.finished_buckets.is_empty() {
            None
        } else {
            Some(self.vpin())
        }
    }

    /// Calculate VPIN over the completed bucket window.
    ///
    /// VPIN = (1/τ) · Σ |V_b^k − V_s^k| / V_B
    pub fn vpin(&self) -> f64 {
        let tau = self.finished_buckets.len() as f64;
        if tau < 1.0 {
            return 0.0;
        }
        let sum: f64 = self.finished_buckets.iter()
            .map(|b| b.imbalance_frac())
            .sum();
        sum / tau
    }

    /// Number of completed buckets (readiness indicator).
    pub fn buckets_complete(&self) -> usize {
        self.finished_buckets.len()
    }
}

/// Combined OFI + VPIN output signal structure.
#[derive(Debug, Clone)]
pub struct FlowSignal {
    pub ofi:  f64,
    pub vpin: Option<f64>,
    /// Direction inferred from OFI: +1 buy, −1 sell, 0 neutral
    pub direction: i8,
}

impl FlowSignal {
    /// Is VPIN above a given threshold? (informed-trading filter)
    pub fn vpin_confirmed(&self, threshold: f64) -> bool {
        self.vpin.map_or(false, |v| v >= threshold)
    }
}

/// Wrapper that combines OFI + VPIN into a single signal.
pub struct FlowAnalyser {
    pub ofi:  OfiEngine,
    pub vpin: VpinEngine,
    /// Minimum |OFI| to generate a directional signal
    pub ofi_threshold: f64,
}

impl FlowAnalyser {
    pub fn new(
        ofi_window: usize,
        vpin_bucket_size: f64,
        vpin_n_buckets: usize,
        ofi_threshold: f64,
    ) -> Self {
        Self {
            ofi:  OfiEngine::new(ofi_window),
            vpin: VpinEngine::new(vpin_bucket_size, vpin_n_buckets),
            ofi_threshold,
        }
    }

    /// Process a tick and return a combined flow signal.
    pub fn process(&mut self, tick: &TradeTick) -> FlowSignal {
        let ofi       = self.ofi.push(tick);
        let vpin_val  = self.vpin.push(tick);
        let direction = if ofi >  self.ofi_threshold { 1 }
                        else if ofi < -self.ofi_threshold { -1 }
                        else { 0 };

        FlowSignal { ofi, vpin: vpin_val, direction }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn buy_tick(price: f64, vol: f64) -> TradeTick {
        TradeTick { price, volume: vol, is_buy: true, ts_ms: 0 }
    }
    fn sell_tick(price: f64, vol: f64) -> TradeTick {
        TradeTick { price, volume: vol, is_buy: false, ts_ms: 0 }
    }

    #[test]
    fn ofi_all_buys() {
        let mut ofi = OfiEngine::new(10);
        for _ in 0..10 {
            let v = ofi.push(&buy_tick(100.0, 1.0));
            assert!((v - 1.0).abs() < 1e-9, "OFI = {v}");
        }
    }

    #[test]
    fn ofi_balanced() {
        let mut ofi = OfiEngine::new(4);
        ofi.push(&buy_tick(100.0, 1.0));
        ofi.push(&sell_tick(100.0, 1.0));
        ofi.push(&buy_tick(100.0, 1.0));
        ofi.push(&sell_tick(100.0, 1.0));
        assert!(ofi.ofi().abs() < 1e-9);
    }

    #[test]
    fn vpin_monotonic_buys() {
        let mut vpin = VpinEngine::new(100.0, 5);
        for i in 0..600 {
            let tick = buy_tick(100.0 + i as f64, 10.0);
            vpin.push(&tick);
        }
        let v = vpin.vpin();
        // All buys → maximum imbalance → VPIN ≈ 1.0
        assert!(v > 0.8, "VPIN = {v}");
    }
}
