/// vortex_strategy.rs — VORTEX-7 NautilusTrader Strategy
///
/// Wraps mft_engine::StrategyEngine (GARCH + OU + OFI + VPIN + EV + Kelly)
/// for each symbol in a HashMap and delegates every bar event to the engine.
///
/// Nautilus integration:
///   - on_start()  → subscribe BarType per symbol
///   - on_bar(bar) → call engine.on_bar() → Option<TradeSignal>
///                 → submit_market_order / close_position via Nautilus OMS
///
/// NOTE: This file is compiled as a module included by backtest.rs
///       (use mod vortex_strategy; at the top of backtest.rs).

use ahash::AHashMap;
use mft_engine::{
    config::AppConfig,
    models::ofi::TradeTick as MftTradeTick,
    strategy::{ExitReason, StrategyEngine},
};
use nautilus_model::{
    enums::OrderSide,
    identifiers::InstrumentId,
    data::{Bar, BarType},
};

// ─── Per-symbol state ──────────────────────────────────────────────────────

/// All mutable state for one symbol during the backtest.
pub struct SymbolState {
    pub engine: StrategyEngine,
    /// The previous-bar close price, used to compute log-returns.
    pub prev_close: Option<f64>,
    /// Total quantity open (positive = net long, negative = net short).
    pub qty_open: f64,
}

impl SymbolState {
    pub fn new(cfg: AppConfig) -> Self {
        let engine = StrategyEngine::new(cfg);
        Self { engine, prev_close: None, qty_open: 0.0 }
    }
}

// ─── VortexStrategy ────────────────────────────────────────────────────────

/// Strategy that runs VORTEX-7 logic per symbol and issues Nautilus orders.
///
/// Because the Nautilus Rust `Strategy` trait requires linking against the
/// Python extension (pyo3) and a live MessageBus, for a pure-Rust backtest
/// we use a *manual driver loop* inside `backtest.rs` instead of implementing
/// the trait.  The struct is still self-contained and fully testable.
pub struct VortexStrategy {
    /// Per-symbol engine instances.
    pub states: AHashMap<InstrumentId, SymbolState>,
    /// Bar types we are subscribed to (one per symbol).
    pub bar_types: Vec<BarType>,
    /// Nautilus account equity (synced per-fill in a live driver).
    pub equity: f64,
    /// Total trades executed across all symbols.
    pub total_trades: usize,
    /// Closed trade log (InstrumentId + exit reason + pnl_frac).
    pub trade_log: Vec<TradeRecord>,
}

/// A completed trade record for reporting.
#[derive(Debug, Clone)]
pub struct TradeRecord {
    pub instrument_id: InstrumentId,
    pub direction: i8,
    pub entry_price: f64,
    pub exit_price: f64,
    pub pnl_frac: f64,
    pub exit_reason: ExitReason,
    pub bars_held: usize,
}

impl VortexStrategy {
    /// Create with a config per symbol.
    pub fn new(
        symbol_configs: Vec<(InstrumentId, BarType, AppConfig)>,
        initial_equity: f64,
    ) -> Self {
        let mut states = AHashMap::new();
        let mut bar_types = Vec::new();

        for (instr_id, bar_type, cfg) in symbol_configs {
            states.insert(instr_id, SymbolState::new(cfg));
            bar_types.push(bar_type);
        }

        Self {
            states,
            bar_types,
            equity: initial_equity,
            total_trades: 0,
            trade_log: vec![],
        }
    }

    /// Called by the backtest driver for every incoming bar.
    ///
    /// # Returns
    /// An optional `(OrderSide, quantity_base)` representing the order to
    /// submit to the Nautilus `SimulatedExchange`.  The driver is responsible
    /// for actually placing the order via `engine.add_order(...)`.
    pub fn on_bar(
        &mut self,
        bar: &Bar,
        instrument_id: InstrumentId,
    ) -> Option<BarAction> {
        let state = self.states.get_mut(&instrument_id)?;

        let close = bar.close.as_f64();
        let open  = bar.open.as_f64();
        let volume = bar.volume.as_f64();

        // Skip zero-volume bars
        if volume <= 0.0 || close <= 0.0 {
            state.prev_close = Some(close);
            return None;
        }

        // Compute log-return (needs at least one previous bar)
        let log_return = match state.prev_close {
            Some(prev) if prev > 0.0 => (close / prev).ln(),
            _ => {
                state.prev_close = Some(close);
                return None; // first bar — no return yet
            }
        };
        state.prev_close = Some(close);

        // Build a synthetic MFT TradeTick from bar data
        // Heuristic: use volume/2 as net buy/sell depending on direction
        let is_buy = close >= open;
        let tick = MftTradeTick {
            price: close,
            volume,
            is_buy,
            ts_ms: 0, // not needed by StrategyEngine
        };

        // ── Run the VORTEX-7 engine ─────────────────────────────────────
        let signal = state.engine.on_bar(close, log_return, &tick);

        // ── Check whether we have an open position that was just closed ──
        // (StrategyEngine.on_bar closes a position internally before returning
        //  a new entry signal, so we check after the call)
        let action = if let Some(sig) = signal {
            // New entry signal
            let base_qty = (self.equity * sig.size_frac / close).max(1e-8);
            let side = if sig.direction == 1 {
                OrderSide::Buy
            } else {
                OrderSide::Sell
            };
            state.engine.open_position(sig.clone());
            state.qty_open = if side == OrderSide::Buy { base_qty } else { -base_qty };
            self.total_trades += 1;
            Some(BarAction::Enter { side, qty: base_qty })
        } else if let Some(ref pos) = state.engine.position {
            // Position still open; check for an exit triggered externally.
            // NOTE: on_bar() above already called ou.push(close) internally.
            // We retrieve the last computed Z-score via the OU signal at the
            // *current* price WITHOUT pushing again (avoids double-counting).
            // ou.signal() does not mutate state — it only reads.
            let z = state.engine.ou.last_z().unwrap_or(0.0);
            if let Some(reason) = state.engine.check_exit(close, z, pos.bars_held) {
                let prev_qty = state.qty_open;
                let prev_dir = if prev_qty > 0.0 { 1i8 } else { -1 };
                let pnl_frac = (close - pos.signal.entry_price)
                    / pos.signal.entry_price
                    * prev_dir as f64;

                self.trade_log.push(TradeRecord {
                    instrument_id,
                    direction: prev_dir,
                    entry_price: pos.signal.entry_price,
                    exit_price: close,
                    pnl_frac,
                    exit_reason: reason.clone(),
                    bars_held: pos.bars_held,
                });
                state.engine.close_position(close, reason);
                let flat_qty = prev_qty.abs();
                let flat_side = if prev_qty > 0.0 {
                    OrderSide::Sell
                } else {
                    OrderSide::Buy
                };
                state.qty_open = 0.0;
                Some(BarAction::Exit { side: flat_side, qty: flat_qty })
            } else {
                None
            }
        } else {
            None
        };

        action
    }

    /// Print a summary of all closed trades.
    pub fn print_summary(&self) {
        let wins: Vec<_> = self.trade_log.iter().filter(|t| t.pnl_frac > 0.0).collect();
        let losses: Vec<_> = self.trade_log.iter().filter(|t| t.pnl_frac <= 0.0).collect();

        let total = self.trade_log.len();
        let win_rate = if total > 0 {
            wins.len() as f64 / total as f64
        } else {
            0.0
        };

        let avg_win: f64 = if !wins.is_empty() {
            wins.iter().map(|t| t.pnl_frac).sum::<f64>() / wins.len() as f64
        } else {
            0.0
        };
        let avg_loss: f64 = if !losses.is_empty() {
            losses.iter().map(|t| t.pnl_frac).sum::<f64>() / losses.len() as f64
        } else {
            0.0
        };

        println!("\n╔══════════════════════════════════════════════════════════╗");
        println!("║           VORTEX-7  STRATEGY  SUMMARY                   ║");
        println!("╠══════════════════════════════════════════════════════════╣");
        println!("║ Total Closed Trades : {:<36}║", total);
        println!("║ Win Rate            : {:<35.2}%║", win_rate * 100.0);
        println!("║ Avg Win  (frac)     : {:<35.6}║", avg_win);
        println!("║ Avg Loss (frac)     : {:<35.6}║", avg_loss);
        println!("╠══════════════════════════════════════════════════════════╣");

        // Per-symbol breakdown
        let mut per_symbol: AHashMap<&str, (usize, f64)> = AHashMap::new();
        for t in &self.trade_log {
            let sym = t.instrument_id.symbol.as_str();
            let entry = per_symbol.entry(sym).or_insert((0, 0.0));
            entry.0 += 1;
            entry.1 += t.pnl_frac;
        }
        let mut symbols: Vec<(&str, (usize, f64))> = per_symbol.into_iter().collect();
        symbols.sort_by(|a, b| a.0.cmp(b.0));
        for (sym, (n, total_pnl)) in symbols {
            println!("║  {:10} trades={:<5} total_pnl={:<18.6}║", sym, n, total_pnl);
        }

        println!("╚══════════════════════════════════════════════════════════╝");
    }
}

// ─── Action returned to the driver ────────────────────────────────────────

/// Instruction from VortexStrategy back to the backtest driver.
#[derive(Debug, Clone)]
pub enum BarAction {
    /// Open a new position.
    Enter { side: OrderSide, qty: f64 },
    /// Flatten an existing position.
    Exit { side: OrderSide, qty: f64 },
}
