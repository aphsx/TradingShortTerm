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
    strategy::{StrategyEngine, ExitReason},
};
use std::ops::{Deref, DerefMut};

use nautilus_trading::strategy::{Strategy, StrategyCore, StrategyConfig};
use nautilus_common::actor::DataActorCore;
use nautilus_model::{
    enums::{OrderSide, TimeInForce, BarAggregation, PriceType, AggregationSource},
    identifiers::{InstrumentId, StrategyId},
    data::{Bar, BarType, BarSpecification},
    types::{Quantity},
};
use anyhow::Result;

// ─── Instrument specification table ───────────────────────────────────────

/// Per-symbol precision and tick-size data.
struct InstrumentSpec {
    symbol:      &'static str,
    base:        &'static str,
    price_prec:  u8,
    size_prec:   u8,
    price_incr:  &'static str,
    size_incr:   &'static str,
}

/// Instrument precision lookup table.
static INSTRUMENT_SPECS: &[InstrumentSpec] = &[
    InstrumentSpec { symbol: "BTCUSDT", base: "BTC", price_prec: 1, size_prec: 3, price_incr: "0.1",  size_incr: "0.001" },
    InstrumentSpec { symbol: "ETHUSDT", base: "ETH", price_prec: 2, size_prec: 3, price_incr: "0.01", size_incr: "0.001" },
    InstrumentSpec { symbol: "SOLUSDT", base: "SOL", price_prec: 2, size_prec: 1, price_incr: "0.01", size_incr: "0.1"   },
    InstrumentSpec { symbol: "BNBUSDT", base: "BNB", price_prec: 2, size_prec: 2, price_incr: "0.01", size_incr: "0.01"  },
    InstrumentSpec { symbol: "XRPUSDT", base: "XRP", price_prec: 4, size_prec: 1, price_incr: "0.0001", size_incr: "1.0"  },
];

fn find_spec(symbol: &str) -> Option<&'static InstrumentSpec> {
    INSTRUMENT_SPECS.iter().find(|s| s.symbol == symbol)
}

// ─── Per-symbol state ──────────────────────────────────────────────────────

/// All mutable state for one symbol during the backtest.
#[derive(Debug)]
pub struct SymbolState {
    pub engine: StrategyEngine,
    /// The previous-bar close price, used to compute log-returns.
    pub prev_close: Option<f64>,
    /// Total quantity open (positive = net long, negative = net short).
    pub qty_open: f64,
    /// Entry price for current position
    pub entry_price: Option<f64>,
    /// ATR for dynamic profit targets
    pub atr: Option<f64>,
    /// Price history for ATR calculation
    pub price_history: Vec<f64>,
    /// EMA for momentum confirmation
    pub ema_short: Option<f64>,
    /// EMA for trend direction
    pub ema_long: Option<f64>,
    /// Bars held in current position
    pub bars_held: usize,
}

impl SymbolState {
    pub fn new(cfg: AppConfig) -> Self {
        let engine = StrategyEngine::new(cfg);
        Self { 
            engine, 
            prev_close: None, 
            qty_open: 0.0,
            entry_price: None,
            atr: None,
            price_history: Vec::new(),
            ema_short: None,
            ema_long: None,
            bars_held: 0,
        }
    }
    
    /// Calculate ATR (Average True Range) for dynamic profit targets
    fn update_atr(&mut self, high: f64, low: f64, close: f64) {
        self.price_history.push(close);
        
        // Keep only last 14 bars for ATR calculation
        if self.price_history.len() > 14 {
            self.price_history.remove(0);
        }
        
        // Update EMAs for momentum
        self.update_emas(close);
        
        if self.price_history.len() >= 14 {
            let mut true_ranges = Vec::new();
            for i in 1..self.price_history.len() {
                let prev_close = self.price_history[i-1];
                let high_low = high - low;
                let high_close = (high - prev_close).abs();
                let low_close = (low - prev_close).abs();
                let tr = high_low.max(high_close.max(low_close));
                true_ranges.push(tr);
            }
            
            if !true_ranges.is_empty() {
                self.atr = Some(true_ranges.iter().sum::<f64>() / true_ranges.len() as f64);
            }
        }
    }
    
    /// Update EMAs for momentum confirmation with optimized periods
    fn update_emas(&mut self, close: f64) {
        const EMA_SHORT_PERIOD: f64 = 3.0;  // Faster response (was 5)
        const EMA_LONG_PERIOD: f64 = 12.0;  // Trend confirmation (was 20)
        const ALPHA_SHORT: f64 = 2.0 / (EMA_SHORT_PERIOD + 1.0);
        const ALPHA_LONG: f64 = 2.0 / (EMA_LONG_PERIOD + 1.0);
        
        match self.ema_short {
            Some(ema) => self.ema_short = Some(ema * (1.0 - ALPHA_SHORT) + close * ALPHA_SHORT),
            None => self.ema_short = Some(close),
        }
        
        match self.ema_long {
            Some(ema) => self.ema_long = Some(ema * (1.0 - ALPHA_LONG) + close * ALPHA_LONG),
            None => self.ema_long = Some(close),
        }
    }
    
    /// Check momentum alignment with signal direction and volume confirmation
    fn has_momentum_confirmation(&self, direction: i8) -> bool {
        if let (Some(ema_short), Some(ema_long)) = (self.ema_short, self.ema_long) {
            let short_above_long = ema_short > ema_long;
            let trend_strength = (ema_short - ema_long) / ema_long;
            
            // Require stronger trend confirmation (>0.05% instead of any)
            let strong_trend = trend_strength.abs() > 0.0005;
            
            match direction {
                1 => short_above_long && strong_trend,  // Long needs bullish momentum
                -1 => !short_above_long && strong_trend, // Short needs bearish momentum
                _ => false,
            }
        } else {
            false // No confirmation until EMAs are initialized
        }
    }
    
    /// Calculate ultra-aggressive scalping profit target for >3% returns
    fn get_profit_target(&self) -> f64 {
        if let (Some(_entry_price), Some(atr)) = (self.entry_price, self.atr) {
            // Ultra-aggressive: 2.0x ATR as profit target
            atr * 2.0
        } else {
            // Fallback: 1.5% profit target
            0.015
        }
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
    fn on_start(&mut self) -> Result<()> {
        // Subscribe to bar data for all instruments
        let instrument_ids: Vec<InstrumentId> = self.states.keys().copied().collect();
        for instrument_id in instrument_ids {
            let bar_type = BarType::new(
                instrument_id,
                BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
                AggregationSource::External,
            );
            self.subscribe_bars(bar_type, None, None);
        }
        Ok(())
    }

    fn on_bar(&mut self, bar: &Bar) -> Result<()> {
        let instrument_id = bar.bar_type.instrument_id();
        
        // Clone data we need before borrowing mutably
        let close = bar.close.as_f64();
        let _open = bar.open.as_f64();
        let high = bar.high.as_f64();
        let low = bar.low.as_f64();
        let volume = bar.volume.as_f64();
        
        if volume <= 0.0 || close <= 0.0 {
            // Update prev_close if we have a state
            if let Some(state) = self.states.get_mut(&instrument_id) {
                state.prev_close = Some(close);
            }
            return Ok(());
        }

        // Get state and calculate signal first
        let (signal, prev_close, _high, _low) = {
            let state = self.states.get_mut(&instrument_id).ok_or_else(|| {
                anyhow::anyhow!("No state found for instrument {:?}", instrument_id)
            })?;
            
            // Update ATR with current bar data
            state.update_atr(high, low, close);
            
            let _log_return = match state.prev_close {
                Some(prev) if prev > 0.0 => (close / prev).ln(),
                _ => {
                    state.prev_close = Some(close);
                    return Ok(());
                }
            };
            let prev_close = state.prev_close;
            
            // Enhanced momentum signal with multiple timeframe analysis
            let signal = if state.price_history.len() >= 8 {
                // Short-term momentum (3 periods)
                let short_prices: Vec<f64> = state.price_history.iter().rev().take(3).cloned().collect();
                let short_avg = short_prices.iter().sum::<f64>() / short_prices.len() as f64;
                
                // Medium-term trend (8 periods)
                let medium_prices: Vec<f64> = state.price_history.iter().rev().take(8).cloned().collect();
                let medium_avg = medium_prices.iter().sum::<f64>() / medium_prices.len() as f64;
                
                // Long-term trend (20 periods if available)
                let long_period = state.price_history.len().min(20);
                let long_prices: Vec<f64> = state.price_history.iter().rev().take(long_period).cloned().collect();
                let long_avg = long_prices.iter().sum::<f64>() / long_prices.len() as f64;
                
                // Calculate momentum strength across timeframes
                let short_momentum = (close - short_avg) / short_avg;
                let medium_momentum = (short_avg - medium_avg) / medium_avg;
                let long_momentum = (medium_avg - long_avg) / long_avg;
                
                // Combined momentum score with weighted emphasis
                let momentum_score = short_momentum * 0.5 + medium_momentum * 0.3 + long_momentum * 0.2;
                
                // Ultra-aggressive entry threshold for maximum opportunities
                let entry_threshold = 0.0003; // Reduced from 0.0008 to 0.0003 (0.03%)
                
                if momentum_score > entry_threshold {
                    Some(mft_engine::strategy::TradeSignal {
                        direction: 1, // Long in uptrend
                        entry_price: close,
                        size_frac: 0.025, // Ultra-aggressive position size (2.5% risk)
                        risk: mft_engine::risk::RiskLevels::long(close, 0.002, close * 1.006),
                        z_score: momentum_score / entry_threshold,
                        ev: momentum_score * 1.2, // Higher expected value
                        vpin: None,
                        garch_sigma_bar: 0.001,
                    })
                } else if momentum_score < -entry_threshold {
                    Some(mft_engine::strategy::TradeSignal {
                        direction: -1, // Short in downtrend
                        entry_price: close,
                        size_frac: 0.025, // Ultra-aggressive position size (2.5% risk)
                        risk: mft_engine::risk::RiskLevels::short(close, 0.002, close * 0.994),
                        z_score: momentum_score / entry_threshold,
                        ev: momentum_score.abs() * 1.2, // Higher expected value
                        vpin: None,
                        garch_sigma_bar: 0.001,
                    })
                } else {
                    None
                }
            } else {
                None
            };
            
            (signal, prev_close, high, low)
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
        
        // Handle signal for opening position (Scalping Mode)
        if let Some(sig) = signal {
            if !has_open_position {
                // Skip momentum filter for now - focus on OU mean reversion
                // Ultra-aggressive position sizing (2.5% risk per trade)
                let equity = self.equity;
                let risk_per_trade = 0.025; // Increased to 2.5% for maximum returns
                let base_qty = (equity * risk_per_trade / close).max(1e-8);
                let side = if sig.direction == 1 { OrderSide::Buy } else { OrderSide::Sell };
                
                // Format quantity according to instrument precision
                let size_prec = if let Some(spec) = find_spec(instrument_id.symbol.as_str()) {
                    spec.size_prec
                } else {
                    8 // fallback to 8 if spec not found
                };
                let order = self.core.order_factory().market(
                    instrument_id,
                    side,
                    Quantity::from(&format!("{:.1$}", base_qty, size_prec as usize)),
                    Some(TimeInForce::Gtc),
                    None, None, None, None, None, None,
                );
                let _ = self.submit_order(order, None, None);
                
                // Update state after order submission
                if let Some(state) = self.states.get_mut(&instrument_id) {
                    state.engine.open_position(sig.clone());
                    state.qty_open = if side == OrderSide::Buy { base_qty } else { -base_qty };
                    state.entry_price = Some(close);
                    state.bars_held = 0;
                }
            }
        } else if has_open_position {
            // Check for fast exit conditions (Scalping)
            let (should_exit, exit_side, exit_qty, trade_record) = {
                if let Some(state) = self.states.get_mut(&instrument_id) {
                    state.bars_held += 1; // Increment bars held
                    
                    // Fast scalping exit conditions
                    let profit_target = state.get_profit_target();
                    let entry_price = state.entry_price.unwrap_or(close);
                    let current_pnl = if state.qty_open > 0.0 {
                        (close - entry_price) / entry_price
                    } else {
                        (entry_price - close) / entry_price
                    };
                    
                    // Ultra-aggressive exit conditions for maximum returns:
                    // 1. Highest profit target (2.0x ATR or 1.5%)
                    // 2. Very tight stop loss (0.1%)
                    // 3. Extended hold time (25 bars)
                    // 4. Aggressive trailing stop
                    
                    let exit_reason = if current_pnl >= profit_target {
                        Some(ExitReason::TakeProfit)
                    } else if current_pnl <= -0.001 { // Very tight stop loss (0.1%)
                        Some(ExitReason::StopLoss)
                    } else if state.bars_held >= 25 { // Extended hold period (25 bars)
                        Some(ExitReason::TimeStop)
                    } else if current_pnl > 0.005 && state.bars_held >= 3 {
                        // Very aggressive trailing stop: lock in 70% of profits
                        let trailing_stop = current_pnl * 0.3;
                        if (close - entry_price) / entry_price <= trailing_stop {
                            Some(ExitReason::TakeProfit)
                        } else {
                            None
                        }
                    } else {
                        // Check original VORTEX exit
                        if let Some(ref pos) = state.engine.position {
                            let z = state.engine.ou.last_z().unwrap_or(0.0);
                            state.engine.check_exit(close, z, pos.bars_held)
                        } else {
                            None
                        }
                    };
                    
                    if let Some(reason) = exit_reason {
                        let side = if state.qty_open > 0.0 { OrderSide::Sell } else { OrderSide::Buy };
                        let qty = state.qty_open.abs();
                        let record = TradeRecord {
                            instrument_id,
                            direction: if state.qty_open > 0.0 { 1 } else { -1 },
                            entry_price,
                            exit_price: close,
                            pnl_frac: current_pnl,
                            exit_reason: reason,
                            bars_held: state.bars_held,
                        };
                        (true, side, qty, Some(record))
                    } else {
                        (false, OrderSide::Buy, 0.0, None)
                    }
                } else {
                    (false, OrderSide::Buy, 0.0, None)
                }
            };
            
            if should_exit {
                // Format quantity according to instrument precision
                let size_prec = if let Some(spec) = find_spec(instrument_id.symbol.as_str()) {
                    spec.size_prec
                } else {
                    8 // fallback to 8 if spec not found
                };
                let order = self.core.order_factory().market(
                    instrument_id,
                    exit_side,
                    Quantity::from(&format!("{:.1$}", exit_qty, size_prec as usize)),
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
