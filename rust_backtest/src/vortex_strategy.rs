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
use std::ops::{Deref, DerefMut};

use nautilus_trading::strategy::{Strategy, StrategyCore, StrategyConfig};
use nautilus_common::actor::DataActorCore;
use nautilus_model::{
    enums::{OrderSide, TimeInForce},
    identifiers::{InstrumentId, StrategyId},
    data::{Bar, BarType},
    types::{Quantity},
};
use anyhow::Result;

// ─── Per-symbol state ──────────────────────────────────────────────────────

/// All mutable state for one symbol during the backtest.
#[derive(Debug)]
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
/// Implements the required traits for NautilusTrader integration.
#[derive(Debug)]
pub struct VortexStrategy {
    pub core: StrategyCore,
    /// Per-symbol engine instances.
    pub states: AHashMap<InstrumentId, SymbolState>,
    /// Closed trade log (InstrumentId + exit reason + pnl_frac).
    pub trade_log: Vec<TradeRecord>,
    pub equity: f64,
}

impl Deref for VortexStrategy {
    type Target = DataActorCore;
    
    fn deref(&self) -> &Self::Target {
        &self.core
    }
}

impl DerefMut for VortexStrategy {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.core
    }
}

/// A completed trade record for reporting.
#[allow(dead_code)]
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
        strategy_id: StrategyId,
        symbol_configs: Vec<(InstrumentId, BarType, AppConfig)>,
        initial_equity: f64,
    ) -> Self {
        let mut states = AHashMap::new();
        for (instr_id, _, cfg) in symbol_configs {
            states.insert(instr_id, SymbolState::new(cfg));
        }

        let config = StrategyConfig {
            strategy_id: Some(strategy_id),
            order_id_tag: None,
            oms_type: None,
            external_order_claims: None,
            log_commands: false,
            log_events: false,
            ..Default::default()
        };
        let core = StrategyCore::new(config);
        Self {
            core,
            states,
            trade_log: vec![],
            equity: initial_equity,
        }
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

impl nautilus_common::actor::DataActor for VortexStrategy {
    fn on_bar(&mut self, bar: &Bar) -> Result<()> {
        let instrument_id = bar.bar_type.instrument_id();
        
        // Clone data we need before borrowing mutably
        let close = bar.close.as_f64();
        let open = bar.open.as_f64();
        let volume = bar.volume.as_f64();
        
        if volume <= 0.0 || close <= 0.0 {
            // Update prev_close if we have a state
            if let Some(state) = self.states.get_mut(&instrument_id) {
                state.prev_close = Some(close);
            }
            return Ok(());
        }

        // Get state and calculate signal first
        let (signal, prev_close) = {
            let state = self.states.get_mut(&instrument_id).ok_or_else(|| {
                anyhow::anyhow!("No state found for instrument {:?}", instrument_id)
            })?;
            
            let log_return = match state.prev_close {
                Some(prev) if prev > 0.0 => (close / prev).ln(),
                _ => {
                    state.prev_close = Some(close);
                    return Ok(());
                }
            };
            let prev_close = state.prev_close;
            
            let tick = MftTradeTick {
                price: close,
                volume,
                is_buy: close >= open,
                ts_ms: 0,
            };

            let signal = state.engine.on_bar(close, log_return, &tick);
            (signal, prev_close)
        };
        
        // Update prev_close in state
        if let Some(state) = self.states.get_mut(&instrument_id) {
            state.prev_close = prev_close;
        }
        
        // Simple position tracking - just use our internal state
        let has_open_position = if let Some(state) = self.states.get(&instrument_id) {
            state.qty_open != 0.0
        } else {
            false
        };
        
        // Handle signal for opening position
        if let Some(sig) = signal {
            if !has_open_position {
                let equity = self.equity;
                let base_qty = (equity * sig.size_frac / close).max(1e-8);
                let side = if sig.direction == 1 { OrderSide::Buy } else { OrderSide::Sell };
                
                let order = self.core.order_factory().market(
                    instrument_id,
                    side,
                    Quantity::from(&format!("{:.8}", base_qty)),
                    Some(TimeInForce::Gtc),
                    None, None, None, None, None, None,
                );
                let _ = self.submit_order(order, None, None);
                
                // Update state after order submission
                if let Some(state) = self.states.get_mut(&instrument_id) {
                    state.engine.open_position(sig.clone());
                    state.qty_open = if side == OrderSide::Buy { base_qty } else { -base_qty };
                }
            }
        } else if has_open_position {
            // Check for exit conditions
            let (should_exit, exit_side, exit_qty, trade_record) = {
                if let Some(state) = self.states.get(&instrument_id) {
                    if let Some(ref pos) = state.engine.position {
                        let z = state.engine.ou.last_z().unwrap_or(0.0);
                        if let Some(reason) = state.engine.check_exit(close, z, pos.bars_held) {
                            let side = if state.qty_open > 0.0 { OrderSide::Sell } else { OrderSide::Buy };
                            let qty = state.qty_open.abs();
                            let record = TradeRecord {
                                instrument_id,
                                direction: if state.qty_open > 0.0 { 1 } else { -1 },
                                entry_price: pos.signal.entry_price,
                                exit_price: close,
                                pnl_frac: (close - pos.signal.entry_price) / pos.signal.entry_price * (if state.qty_open > 0.0 { 1.0 } else { -1.0 }),
                                exit_reason: reason.clone(),
                                bars_held: pos.bars_held,
                            };
                            (true, side, qty, Some(record))
                        } else {
                            (false, OrderSide::Buy, 0.0, None)
                        }
                    } else {
                        (false, OrderSide::Buy, 0.0, None)
                    }
                } else {
                    (false, OrderSide::Buy, 0.0, None)
                }
            };
            
            if should_exit {
                let order = self.core.order_factory().market(
                    instrument_id,
                    exit_side,
                    Quantity::from(&format!("{:.8}", exit_qty)),
                    Some(TimeInForce::Gtc),
                    None, None, None, None, None, None,
                );
                let _ = self.submit_order(order, None, None);
                
                if let Some(record) = trade_record {
                    self.trade_log.push(record);
                }
                
                // Update state after order submission
                if let Some(state) = self.states.get_mut(&instrument_id) {
                    if let Some(ref pos) = state.engine.position {
                        let z = state.engine.ou.last_z().unwrap_or(0.0);
                        if let Some(reason) = state.engine.check_exit(close, z, pos.bars_held) {
                            state.engine.close_position(close, reason);
                            state.qty_open = 0.0;
                        }
                    }
                }
            }
        }

        Ok(())
    }
}

impl Strategy for VortexStrategy {
    fn core(&self) -> &StrategyCore {
        &self.core
    }

    fn core_mut(&mut self) -> &mut StrategyCore {
        &mut self.core
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
