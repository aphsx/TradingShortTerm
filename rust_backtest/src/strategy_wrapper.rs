/// strategy_wrapper.rs — Strategy Wrapper for NautilusTrader Integration
///
/// Wraps the MFT engine's StrategyEngine to work with NautilusTrader's strategy framework.
/// Handles event translation, order management, and state synchronization between the two systems.
///
/// Architecture:
/// ┌─────────────────────────────────────────────────────┐
/// │  NautilusTrader Strategy Framework                   │
/// │        │                                            │
/// │        ▼                                            │
/// │  MFTStrategyWrapper (Adapter)                       │
/// │        │                                            │
/// │   ┌────┴──────────────────────────────────┐        │
/// │   │  Event Translation                     │        │
/// │   │  ├─ QuoteTick → MFT price update      │        │
/// │   │  ├─ TradeTick → MFT flow data         │        │
/// │   │  └─ Bar → MFT OHLCV data              │        │
/// │   └────────────────────────────────────────┘        │
/// │        │                                            │
/// │   ┌────┴──────────────────────────────────┐        │
/// │   │  Order Management                     │        │
/// │   │  ├─ TradeSignal → MarketOrder         │        │
/// │   │  ├─ Position tracking                 │        │
/// │   │  └─ Risk management integration       │        │
/// │   └────────────────────────────────────────┘        │
/// │        │                                            │
/// │        ▼                                            │
/// │  MFT Engine StrategyEngine                          │
/// └─────────────────────────────────────────────────────┘

use std::collections::HashMap;
use std::sync::Arc;
use anyhow::{Result, anyhow};
use nautilus_core::uuid::UUID4;
use nautilus_core::nanos::UnixNanos;
use nautilus_common::clients::execution::ExecutionClient;
use nautilus_model::data::{Bar, QuoteTick, TradeTick};
use nautilus_model::enums::{OrderSide, OrderType, TimeInForce};
use nautilus_model::events::{OrderAccepted, OrderFilled, OrderRejected};
use nautilus_model::identifiers::{
    InstrumentId,
    order_id::OrderId,
    client_order_id::ClientOrderId,
};
use nautilus_model::orders::{MarketOrder, Order};
use nautilus_model::types::{Price, Quantity};
use nautilus_trading::strategy::Strategy;
use tracing::{info, warn, debug};

use mft_engine::{
    config::AppConfig,
    strategy::{StrategyEngine, TradeSignal},
    data::Kline,
};

/// Configuration for the strategy wrapper
#[derive(Debug, Clone)]
pub struct StrategyWrapperConfig {
    /// MFT engine configuration
    pub mft_config: AppConfig,
    /// Strategy ID
    pub strategy_id: UUID4,
    /// Whether to log all events
    pub verbose_logging: bool,
    /// Maximum position size as fraction of equity
    pub max_position_frac: f64,
}

impl Default for StrategyWrapperConfig {
    fn default() -> Self {
        Self {
            mft_config: AppConfig::default(),
            strategy_id: UUID4::new(),
            verbose_logging: false,
            max_position_frac: 0.95, // 95% max position
        }
    }
}

/// Strategy wrapper that integrates MFT engine with NautilusTrader
pub struct MFTStrategyWrapper {
    config: StrategyWrapperConfig,
    mft_engine: StrategyEngine,
    execution_client: Option<Arc<dyn ExecutionClient>>,
    current_instrument: Option<InstrumentId>,
    current_position: Option<f64>,
    pending_orders: HashMap<ClientOrderId, Order>,
    filled_trades: Vec<TradeInfo>,
    last_bar: Option<Bar>,
    last_quote: Option<QuoteTick>,
    
    // Performance tracking
    total_pnl: f64,
    max_drawdown: f64,
    peak_equity: f64,
    trade_count: usize,
    win_count: usize,
}

#[derive(Debug, Clone)]
struct TradeInfo {
    instrument_id: InstrumentId,
    side: OrderSide,
    quantity: Quantity,
    price: Price,
    timestamp: UnixNanos,
    pnl: f64,
}

impl MFTStrategyWrapper {
    /// Create new strategy wrapper
    pub fn new(config: StrategyWrapperConfig) -> Result<Self> {
        let mft_engine = StrategyEngine::new(config.mft_config.clone())?;
        
        Ok(Self {
            config,
            mft_engine,
            execution_client: None,
            current_instrument: None,
            current_position: None,
            pending_orders: HashMap::new(),
            filled_trades: Vec::new(),
            last_bar: None,
            last_quote: None,
            total_pnl: 0.0,
            max_drawdown: 0.0,
            peak_equity: 0.0,
            trade_count: 0,
            win_count: 0,
        })
    }

    /// Set the execution client for order submission
    pub fn set_execution_client(&mut self, client: Arc<dyn ExecutionClient>) {
        self.execution_client = Some(client);
    }

    /// Set the current trading instrument
    pub fn set_instrument(&mut self, instrument_id: InstrumentId) {
        self.current_instrument = Some(instrument_id);
        info!("Set trading instrument: {}", instrument_id);
    }

    /// Process a bar event from NautilusTrader
    pub fn on_bar(&mut self, bar: Bar) -> Result<()> {
        if self.config.verbose_logging {
            debug!("Processing bar: {}", bar);
        }
        
        self.last_bar = Some(bar.clone());
        
        // Convert bar to Kline format for MFT engine
        let kline = self.bar_to_kline(&bar)?;
        
        // Process through MFT engine
        let signal = self.mft_engine.on_bar(&kline)?;
        
        // Handle generated signal
        if let Some(trade_signal) = signal {
            self.handle_trade_signal(trade_signal)?;
        }
        
        Ok(())
    }

    /// Process a quote tick event from NautilusTrader
    pub fn on_quote_tick(&mut self, quote: QuoteTick) -> Result<()> {
        if self.config.verbose_logging {
            debug!("Processing quote tick: {}", quote);
        }
        
        self.last_quote = Some(quote);
        
        // Update MFT engine with latest price information
        // This would be used for real-time risk management and position updates
        self.update_risk_management()?;
        
        Ok(())
    }

    /// Process a trade tick event from NautilusTrader
    pub fn on_trade_tick(&mut self, trade: TradeTick) -> Result<()> {
        if self.config.verbose_logging {
            debug!("Processing trade tick: {}", trade);
        }
        
        // Convert trade tick to flow data for MFT engine
        // This would update the OFI/VPIN calculations
        self.update_flow_data(&trade)?;
        
        Ok(())
    }

    /// Handle order acceptance event
    pub fn on_order_accepted(&mut self, event: OrderAccepted) {
        info!("Order accepted: {}", event.client_order_id);
        
        // Update order status
        if let Some(order) = self.pending_orders.get_mut(&event.client_order_id) {
            // Update order state
        }
    }

    /// Handle order fill event
    pub fn on_order_filled(&mut self, event: OrderFilled) {
        info!("Order filled: {} qty: {} price: {}", 
              event.client_order_id, event.last_qty, event.last_px);
        
        // Update position tracking
        let side = event.order_side;
        let quantity = event.last_qty.as_f64();
        let price = event.last_px.as_f64();
        
        match side {
            OrderSide::Buy => {
                self.current_position = Some(self.current_position.unwrap_or(0.0) + quantity);
            }
            OrderSide::Sell => {
                self.current_position = Some(self.current_position.unwrap_or(0.0) - quantity);
            }
        }
        
        // Record trade
        let trade_info = TradeInfo {
            instrument_id: event.instrument_id,
            side,
            quantity: event.last_qty,
            price: event.last_px,
            timestamp: event.ts_event,
            pnl: self.calculate_trade_pnl(side, quantity, price),
        };
        
        self.filled_trades.push(trade_info);
        self.update_performance_metrics();
        
        // Remove from pending orders
        self.pending_orders.remove(&event.client_order_id);
    }

    /// Handle order rejection event
    pub fn on_order_rejected(&mut self, event: OrderRejected) {
        warn!("Order rejected: {} reason: {}", event.client_order_id, event.reason);
        
        // Remove from pending orders
        self.pending_orders.remove(&event.client_order_id);
    }

    /// Convert NautilusTrader Bar to MFT Kline
    fn bar_to_kline(&self, bar: &Bar) -> Result<Kline> {
        let symbol = self.extract_symbol_from_instrument(&bar.bar_type.instrument_id)?;
        let open_time = chrono::DateTime::from_timestamp(
            bar.ts_event.as_nanos() / 1_000_000_000,
            (bar.ts_event.as_nanos() % 1_000_000_000) as u32
        ).ok_or_else(|| anyhow!("Invalid timestamp"))?;
        
        Ok(Kline {
            symbol,
            open_time,
            close_time: open_time + chrono::Duration::minutes(1), // Assuming 1-minute bars
            open: bar.open.as_f64(),
            high: bar.high.as_f64(),
            low: bar.low.as_f64(),
            close: bar.close.as_f64(),
            volume: bar.volume.as_f64(),
            quote_volume: bar.volume.as_f64() * bar.close.as_f64(),
            count: 0,
            taker_buy_volume: bar.volume.as_f64() * 0.5, // Estimate
            taker_buy_quote_volume: bar.volume.as_f64() * bar.close.as_f64() * 0.5,
        })
    }

    /// Handle a trade signal from MFT engine
    fn handle_trade_signal(&mut self, signal: TradeSignal) -> Result<()> {
        info!("Trade signal: direction={}, size={:.4}, entry_price={:.6}, z_score={:.2}",
              signal.direction, signal.size_frac, signal.entry_price, signal.z_score);
        
        // Check if we should exit existing position first
        if let Some(current_pos) = self.current_position {
            if (current_pos > 0.0 && signal.direction < 0) || 
               (current_pos < 0.0 && signal.direction > 0) {
                // Close existing position
                self.close_position()?;
            }
        }
        
        // Open new position if signal is strong enough
        if signal.direction != 0 && signal.ev > 0.0 {
            self.open_position(signal)?;
        }
        
        Ok(())
    }

    /// Open a new position based on trade signal
    fn open_position(&mut self, signal: TradeSignal) -> Result<()> {
        let instrument_id = self.current_instrument
            .ok_or_else(|| anyhow!("No instrument set"))?;
        
        // Calculate position size
        let equity = 100_000.0; // This should come from portfolio
        let position_value = equity * signal.size_frac.min(self.config.max_position_frac);
        let price = signal.entry_price;
        let quantity = position_value / price;
        
        let order_side = if signal.direction > 0 { 
            OrderSide::Buy 
        } else { 
            OrderSide::Sell 
        };
        
        // Create market order
        let client_order_id = ClientOrderId::new(format!("mft_{}", UUID4::new()));
        let order = MarketOrder::new(
            client_order_id.clone(),
            instrument_id,
            order_side,
            Quantity::from(quantity),
            OrderType::Market,
            TimeInForce::IOC,
            UnixNanos::now(),
        );
        
        // Submit order
        if let Some(exec_client) = &self.execution_client {
            exec_client.submit_order(order)?;
            
            // Track pending order
            self.pending_orders.insert(client_order_id, order);
            
            info!("Submitted {} order: qty={:.6}, price={:.6}", 
                  order_side, quantity, price);
        } else {
            warn!("No execution client available - cannot submit order");
        }
        
        Ok(())
    }

    /// Close current position
    fn close_position(&mut self) -> Result<()> {
        if let Some(position_size) = self.current_position {
            if position_size.abs() > 0.0 {
                let instrument_id = self.current_instrument
                    .ok_or_else(|| anyhow!("No instrument set"))?;
                
                let order_side = if position_size > 0.0 { 
                    OrderSide::Sell 
                } else { 
                    OrderSide::Buy 
                };
                
                let quantity = position_size.abs();
                
                // Create market order to close
                let client_order_id = ClientOrderId::new(format!("mft_close_{}", UUID4::new()));
                let order = MarketOrder::new(
                    client_order_id.clone(),
                    instrument_id,
                    order_side,
                    Quantity::from(quantity),
                    OrderType::Market,
                    TimeInForce::IOC,
                    UnixNanos::now(),
                );
                
                // Submit order
                if let Some(exec_client) = &self.execution_client {
                    exec_client.submit_order(order)?;
                    self.pending_orders.insert(client_order_id, order);
                    
                    info!("Submitted closing order: qty={:.6}", quantity);
                }
            }
        }
        
        Ok(())
    }

    /// Update risk management based on current market data
    fn update_risk_management(&mut self) -> Result<()> {
        // Check if stop-loss or take-profit should be triggered
        // This would integrate with MFT engine's risk management
        
        if let Some(current_pos) = self.current_position {
            if let Some(quote) = &self.last_quote {
                let current_price = quote.mid_price().as_f64();
                
                // Simple risk check - in practice, use MFT engine's risk levels
                let max_loss_pct = 0.02; // 2% max loss
                
                // This is simplified - real implementation would use MFT risk calculations
                if current_pos > 0.0 && current_price < 0.98 * current_pos {
                    self.close_position()?;
                } else if current_pos < 0.0 && current_price > 1.02 * current_pos.abs() {
                    self.close_position()?;
                }
            }
        }
        
        Ok(())
    }

    /// Update flow data with trade tick
    fn update_flow_data(&mut self, trade: &TradeTick) -> Result<()> {
        // Convert trade tick to flow data for MFT engine
        // This would update the OFI/VPIN calculations
        
        // For now, just log the trade
        if self.config.verbose_logging {
            debug!("Flow data update: {} @ {}", trade.price, trade.size);
        }
        
        Ok(())
    }

    /// Calculate P&L for a trade
    fn calculate_trade_pnl(&self, side: OrderSide, quantity: f64, price: f64) -> f64 {
        // Simplified P&L calculation
        // In practice, this would account for fees, financing, etc.
        match side {
            OrderSide::Buy => -quantity * price, // Buying costs money
            OrderSide::Sell => quantity * price, // Selling makes money
        }
    }

    /// Update performance metrics
    fn update_performance_metrics(&mut self) {
        if let Some(last_trade) = self.filled_trades.last() {
            self.total_pnl += last_trade.pnl;
            self.trade_count += 1;
            
            if last_trade.pnl > 0.0 {
                self.win_count += 1;
            }
            
            // Update peak equity and drawdown
            let current_equity = 100_000.0 + self.total_pnl; // Starting from 100k
            if current_equity > self.peak_equity {
                self.peak_equity = current_equity;
            }
            
            let drawdown = (self.peak_equity - current_equity) / self.peak_equity;
            if drawdown > self.max_drawdown {
                self.max_drawdown = drawdown;
            }
        }
    }

    /// Extract symbol from instrument ID
    fn extract_symbol_from_instrument(&self, instrument_id: &InstrumentId) -> Result<String> {
        let id_str = instrument_id.to_string();
        if let Some(dot_pos) = id_str.find('.') {
            Ok(id_str[..dot_pos].to_string())
        } else {
            Ok(id_str)
        }
    }

    /// Get current performance statistics
    pub fn get_performance_stats(&self) -> HashMap<String, f64> {
        let mut stats = HashMap::new();
        
        stats.insert("total_pnl".to_string(), self.total_pnl);
        stats.insert("trade_count".to_string(), self.trade_count as f64);
        stats.insert("win_count".to_string(), self.win_count as f64);
        stats.insert("win_rate".to_string(), 
                    if self.trade_count > 0 { 
                        self.win_count as f64 / self.trade_count as f64 
                    } else { 
                        0.0 
                    });
        stats.insert("max_drawdown".to_string(), self.max_drawdown);
        stats.insert("current_position".to_string(), self.current_position.unwrap_or(0.0));
        
        stats
    }

    /// Get strategy state
    pub fn get_strategy_state(&self) -> HashMap<String, String> {
        let mut state = HashMap::new();
        
        state.insert("strategy_id".to_string(), self.config.strategy_id.to_string());
        state.insert("current_instrument".to_string(), 
                    self.current_instrument.as_ref()
                        .map(|id| id.to_string())
                        .unwrap_or_else(|| "None".to_string()));
        state.insert("pending_orders".to_string(), self.pending_orders.len().to_string());
        state.insert("filled_trades".to_string(), self.filled_trades.len().to_string());
        
        state
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    #[test]
    fn test_strategy_wrapper_config() {
        let config = StrategyWrapperConfig::default();
        assert_eq!(config.max_position_frac, 0.95);
        assert!(!config.verbose_logging);
    }

    #[test]
    fn test_performance_stats() -> Result<()> {
        let config = StrategyWrapperConfig::default();
        let wrapper = MFTStrategyWrapper::new(config)?;
        
        let stats = wrapper.get_performance_stats();
        assert_eq!(stats.get("total_pnl"), Some(&0.0));
        assert_eq!(stats.get("trade_count"), Some(&0.0));
        
        Ok(())
    }
}
