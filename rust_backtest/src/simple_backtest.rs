/// simple_backtest.rs — Simplified Backtest Implementation
///
/// A simplified backtest implementation that works with the MFT engine
/// without the complexity of NautilusTrader integration. This provides
/// a working backtest system that can be easily extended.

use anyhow::Result;
use chrono::{DateTime, Utc};
use tracing::info;

use mft_engine::{
    config::AppConfig,
    strategy::{StrategyEngine, TradeSignal},
    data::Kline,
    metrics::PerfReport,
};

/// Simple backtest configuration
#[derive(Debug, Clone)]
pub struct SimpleBacktestConfig {
    pub mft_config: AppConfig,
    pub initial_capital: f64,
    pub commission_rate: f64,
    pub slippage_bps: f64, // Basis points
}

impl Default for SimpleBacktestConfig {
    fn default() -> Self {
        Self {
            mft_config: AppConfig::from_env().unwrap_or_else(|_| {
                // Fallback config if env variables not set
                AppConfig {
                    api_key: "".to_string(),
                    api_secret: "".to_string(),
                    use_testnet: true,
                    rest_url: "".to_string(),
                    ws_url: "".to_string(),
                    trading_pairs: vec!["BTCUSDT".to_string()],
                    initial_capital: 100_000.0,
                    risk_per_trade: 0.02,
                    max_leverage: 10,
                    maker_fee: 0.0002,
                    taker_fee: 0.0005,
                    slippage: 0.0003,
                    garch_omega: 0.00001,
                    garch_alpha: 0.1,
                    garch_beta: 0.85,
                    ou_entry_z: 2.0,
                    ou_exit_z: 0.5,
                    ou_window: 100,
                    vpin_bucket_size: 1000,
                    vpin_n_buckets: 50,
                    vpin_threshold: 0.025,
                    min_ev: 0.001,
                    min_p_win: 0.55,
                    stop_loss_frac: 0.02,
                    exit_prob_threshold: 0.3,
                    max_hold_bars: 1000,
                    kline_interval: "1m".to_string(),
                    backtest_symbol: "BTCUSDT".to_string(),
                    backtest_limit: 10000,
                }
            }),
            initial_capital: 100_000.0,
            commission_rate: 0.001, // 0.1%
            slippage_bps: 5.0, // 5 basis points
        }
    }
}

/// Trade record
#[derive(Debug, Clone)]
pub struct Trade {
    pub entry_time: DateTime<Utc>,
    pub exit_time: DateTime<Utc>,
    pub direction: i8, // 1 for long, -1 for short
    pub entry_price: f64,
    pub exit_price: f64,
    pub quantity: f64,
    pub pnl: f64,
    pub commission: f64,
    pub return_pct: f64,
}

/// Backtest results
#[derive(Debug, Clone)]
pub struct BacktestResults {
    pub trades: Vec<Trade>,
    pub equity_curve: Vec<EquityPoint>,
    pub performance_metrics: PerfReport,
    pub final_capital: f64,
    pub total_return: f64,
    pub max_drawdown: f64,
    pub sharpe_ratio: f64,
}

/// Equity curve point
#[derive(Debug, Clone)]
pub struct EquityPoint {
    pub timestamp: DateTime<Utc>,
    pub equity: f64,
    pub returns: f64,
    pub drawdown: f64,
}

/// Simple backtest engine
pub struct SimpleBacktestEngine {
    config: SimpleBacktestConfig,
    strategy: StrategyEngine,
    trades: Vec<Trade>,
    equity_curve: Vec<EquityPoint>,
    current_position: Option<Position>,
    current_equity: f64,
    peak_equity: f64,
}

#[derive(Debug, Clone)]
struct Position {
    direction: i8,
    entry_price: f64,
    quantity: f64,
    entry_time: DateTime<Utc>,
}

impl SimpleBacktestEngine {
    /// Create new simple backtest engine
    pub fn new(config: SimpleBacktestConfig) -> Result<Self> {
        let strategy = StrategyEngine::new(config.mft_config.clone());
        
        Ok(Self {
            config: config.clone(),
            strategy,
            trades: Vec::new(),
            equity_curve: Vec::new(),
            current_position: None,
            current_equity: config.initial_capital,
            peak_equity: config.initial_capital,
        })
    }

    /// Run backtest on kline data
    pub fn run(&mut self, klines: &[Kline]) -> Result<BacktestResults> {
        info!("Starting simple backtest with {} bars", klines.len());
        
        // Initialize equity curve
        self.equity_curve.push(EquityPoint {
            timestamp: chrono::DateTime::from_timestamp_millis(klines[0].open_time).unwrap_or_else(|| Utc::now()),
            equity: self.current_equity,
            returns: 0.0,
            drawdown: 0.0,
        });

        // Process each bar
        for (i, kline) in klines.iter().enumerate() {
            // Check for exit signal if we have a position
            if self.current_position.is_some() {
                self.check_exit_signals(kline)?;
            }

            // Process bar through strategy
            let log_return = if i > 0 { 
                (kline.close / klines[i-1].close).ln() 
            } else { 
                0.0 
            };
            
            // Create a mock tick for the strategy
            let tick = mft_engine::models::ofi::TradeTick {
                price: kline.close,
                volume: kline.volume,
                ts_ms: kline.open_time,
                is_buy: kline.close > kline.open,
            };
            
            let signal = self.strategy.on_bar(kline.close, log_return, &tick);
            
            // Handle entry signals
            if let Some(trade_signal) = signal {
                if self.current_position.is_none() && trade_signal.direction != 0 {
                    self.open_position(trade_signal, kline)?;
                }
            }

            // Update equity curve
            self.update_equity_curve(chrono::DateTime::from_timestamp_millis(kline.open_time).unwrap_or_else(|| Utc::now()), kline.close);
            
            if i % 1000 == 0 {
                info!("Processed {} bars, current equity: ${:.2}", i + 1, self.current_equity);
            }
        }

        // Close any remaining position
        if self.current_position.is_some() && !klines.is_empty() {
            let last_kline = &klines[klines.len() - 1];
            self.close_position(last_kline.close, chrono::DateTime::from_timestamp_millis(last_kline.open_time).unwrap_or_else(|| Utc::now()))?;
        }

        // Calculate performance metrics
        let performance_metrics = self.calculate_performance_metrics()?;
        
        let results = BacktestResults {
            trades: self.trades.clone(),
            equity_curve: self.equity_curve.clone(),
            performance_metrics,
            final_capital: self.current_equity,
            total_return: (self.current_equity - self.config.initial_capital) / self.config.initial_capital,
            max_drawdown: self.calculate_max_drawdown(),
            sharpe_ratio: self.calculate_sharpe_ratio(),
        };

        info!("Backtest completed. Final capital: ${:.2}, Total return: {:.2}%", 
              results.final_capital, results.total_return * 100.0);
        info!("Total trades: {}, Win rate: {:.1}%", 
              results.trades.len(), 
              self.calculate_win_rate(&results.trades) * 100.0);

        Ok(results)
    }

    /// Open a new position
    fn open_position(&mut self, signal: TradeSignal, kline: &Kline) -> Result<()> {
        let position_value = self.current_equity * signal.size_frac;
        let entry_price = kline.open; // Use open price for entry
        let quantity = position_value / entry_price;
        
        // Apply slippage
        let adjusted_price = if signal.direction > 0 {
            entry_price * (1.0 + self.config.slippage_bps / 10000.0)
        } else {
            entry_price * (1.0 - self.config.slippage_bps / 10000.0)
        };

        let commission = position_value * self.config.commission_rate;
        
        self.current_position = Some(Position {
            direction: signal.direction,
            entry_price: adjusted_price,
            quantity,
            entry_time: chrono::DateTime::from_timestamp_millis(kline.open_time).unwrap_or_else(|| Utc::now()),
        });

        self.current_equity -= commission;
        
        info!("Opened {} position: {:.6} @ ${:.6}, cost: ${:.2}", 
              if signal.direction > 0 { "LONG" } else { "SHORT" },
              quantity, adjusted_price, commission);

        Ok(())
    }

    /// Close current position
    fn close_position(&mut self, exit_price: f64, exit_time: DateTime<Utc>) -> Result<()> {
        if let Some(position) = self.current_position.take() {
            // Apply slippage
            let adjusted_price = if position.direction > 0 {
                exit_price * (1.0 - self.config.slippage_bps / 10000.0)
            } else {
                exit_price * (1.0 + self.config.slippage_bps / 10000.0)
            };

            let position_value = position.quantity * position.entry_price;
            let exit_value = position.quantity * adjusted_price;
            let commission = exit_value * self.config.commission_rate;
            
            let pnl = if position.direction > 0 {
                exit_value - position_value - commission
            } else {
                position_value - exit_value - commission
            };

            let return_pct = pnl / position_value;
            
            self.current_equity += pnl;

            let trade = Trade {
                entry_time: position.entry_time,
                exit_time,
                direction: position.direction,
                entry_price: position.entry_price,
                exit_price: adjusted_price,
                quantity: position.quantity,
                pnl,
                commission,
                return_pct,
            };

            self.trades.push(trade);
            
            info!("Closed position: PnL ${:.2} ({:.2}%), commission ${:.2}", 
                  pnl, return_pct * 100.0, commission);
        }

        Ok(())
    }

    /// Check for exit signals
    fn check_exit_signals(&mut self, kline: &Kline) -> Result<()> {
        // Simple exit logic - close position if price moves against us by 2%
        // In practice, this would use MFT engine's exit signals
        if let Some(position) = &self.current_position {
            let price_change_pct = (kline.close - position.entry_price) / position.entry_price;
            
            let should_exit = if position.direction > 0 {
                price_change_pct < -0.02 // 2% loss on long
            } else {
                price_change_pct > 0.02 // 2% loss on short
            };

            if should_exit {
                self.close_position(kline.close, chrono::DateTime::from_timestamp_millis(kline.open_time).unwrap_or_else(|| Utc::now()))?;
            }
        }

        Ok(())
    }

    /// Update equity curve
    fn update_equity_curve(&mut self, timestamp: DateTime<Utc>, current_price: f64) {
        let mut equity = self.current_equity;
        
        // Add unrealized P&L if we have an open position
        if let Some(position) = &self.current_position {
            let unrealized_pnl = if position.direction > 0 {
                (current_price - position.entry_price) * position.quantity
            } else {
                (position.entry_price - current_price) * position.quantity
            };
            equity += unrealized_pnl;
        }

        let returns = if self.equity_curve.is_empty() {
            0.0
        } else {
            (equity - self.equity_curve.last().unwrap().equity) / self.equity_curve.last().unwrap().equity
        };

        if equity > self.peak_equity {
            self.peak_equity = equity;
        }

        let drawdown = (self.peak_equity - equity) / self.peak_equity;

        self.equity_curve.push(EquityPoint {
            timestamp,
            equity,
            returns,
            drawdown,
        });
    }

    /// Calculate performance metrics
    fn calculate_performance_metrics(&self) -> Result<PerfReport> {
        // Convert trades to format expected by compute_metrics
        let returns: Vec<f64> = self.equity_curve.iter()
            .skip(1)
            .map(|point| point.returns)
            .collect();

        if returns.is_empty() {
            return Ok(PerfReport {
                n_trades: 0,
                win_rate: 0.0,
                avg_win: 0.0,
                avg_loss: 0.0,
                profit_factor: 0.0,
                total_return: 0.0,
                sharpe: 0.0,
                sortino: 0.0,
                max_drawdown: 0.0,
                calmar: 0.0,
                initial_equity: self.config.initial_capital,
                final_equity: self.current_equity,
            });
        }

        // Simple performance calculation
        let mean_return = returns.iter().sum::<f64>() / returns.len() as f64;
        let variance = returns.iter()
            .map(|r| (r - mean_return).powi(2))
            .sum::<f64>() / returns.len() as f64;
        let volatility = variance.sqrt();

        let _total_return = (self.current_equity - self.config.initial_capital) / self.config.initial_capital;
        let max_drawdown = self.calculate_max_drawdown();
        let sharpe_ratio = if volatility > 0.0 { mean_return / volatility } else { 0.0 };

        Ok(PerfReport {
            n_trades: self.trades.len(),
            win_rate: self.calculate_win_rate(&self.trades),
            avg_win: self.calculate_avg_win(&self.trades),
            avg_loss: self.calculate_avg_loss(&self.trades),
            profit_factor: self.calculate_profit_factor(&self.trades),
            total_return: (self.current_equity - self.config.initial_capital) / self.config.initial_capital,
            sharpe: sharpe_ratio,
            sortino: sharpe_ratio, // Simplified
            max_drawdown: self.calculate_max_drawdown(),
            calmar: if max_drawdown != 0.0 { sharpe_ratio / max_drawdown.abs() } else { 0.0 },
            initial_equity: self.config.initial_capital,
            final_equity: self.current_equity,
        })
    }

    /// Calculate maximum drawdown
    fn calculate_max_drawdown(&self) -> f64 {
        self.equity_curve.iter()
            .map(|point| point.drawdown)
            .fold(0.0, f64::max)
    }

    /// Calculate Sharpe ratio
    fn calculate_sharpe_ratio(&self) -> f64 {
        let returns: Vec<f64> = self.equity_curve.iter()
            .skip(1)
            .map(|point| point.returns)
            .collect();

        if returns.is_empty() {
            return 0.0;
        }

        let mean_return = returns.iter().sum::<f64>() / returns.len() as f64;
        let variance = returns.iter()
            .map(|r| (r - mean_return).powi(2))
            .sum::<f64>() / returns.len() as f64;
        let volatility = variance.sqrt();

        if volatility > 0.0 {
            mean_return / volatility
        } else {
            0.0
        }
    }

    /// Calculate win rate
    fn calculate_win_rate(&self, trades: &[Trade]) -> f64 {
        if trades.is_empty() {
            return 0.0;
        }

        let winning_trades = trades.iter().filter(|t| t.pnl > 0.0).count();
        winning_trades as f64 / trades.len() as f64
    }

    /// Calculate average win
    fn calculate_avg_win(&self, trades: &[Trade]) -> f64 {
        let winning_trades: Vec<&Trade> = trades.iter().filter(|t| t.pnl > 0.0).collect();
        if winning_trades.is_empty() {
            return 0.0;
        }
        winning_trades.iter().map(|t| t.return_pct).sum::<f64>() / winning_trades.len() as f64
    }

    /// Calculate average loss
    fn calculate_avg_loss(&self, trades: &[Trade]) -> f64 {
        let losing_trades: Vec<&Trade> = trades.iter().filter(|t| t.pnl <= 0.0).collect();
        if losing_trades.is_empty() {
            return 0.0;
        }
        losing_trades.iter().map(|t| t.return_pct.abs()).sum::<f64>() / losing_trades.len() as f64
    }

    /// Calculate profit factor
    fn calculate_profit_factor(&self, trades: &[Trade]) -> f64 {
        let (gross_profit, gross_loss) = trades.iter().fold((0.0, 0.0), |(gp, gl), trade| {
            if trade.pnl > 0.0 {
                (gp + trade.pnl, gl)
            } else {
                (gp, gl + trade.pnl.abs())
            }
        });

        if gross_loss > 0.0 {
            gross_profit / gross_loss
        } else {
            0.0
        }
    }
}

pub fn generate_text_report(results: &BacktestResults) -> String {
    let mut report = String::new();
    
    report.push_str("=== MFT SIMPLE BACKTEST REPORT ===\n\n");
    report.push_str(&format!("Initial Capital: ${:.2}\n", 100_000.0));
    report.push_str(&format!("Final Capital: ${:.2}\n", results.final_capital));
    report.push_str(&format!("Total Return: {:.2}%\n\n", results.total_return * 100.0));
    
    report.push_str("PERFORMANCE METRICS:\n");
    report.push_str(&format!("  Sharpe Ratio: {:.2}\n", results.performance_metrics.sharpe));
    report.push_str(&format!("  Sortino Ratio: {:.2}\n", results.performance_metrics.sortino));
    report.push_str(&format!("  Maximum Drawdown: {:.2}%\n\n", results.max_drawdown * 100.0));
    
    report.push_str("TRADE ANALYSIS:\n");
    report.push_str(&format!("  Total Trades: {}\n", results.performance_metrics.n_trades));
    report.push_str(&format!("  Win Rate: {:.1}%\n", results.performance_metrics.win_rate * 100.0));
    report.push_str(&format!("  Profit Factor: {:.2}\n\n", results.performance_metrics.profit_factor));
    
    if !results.trades.is_empty() {
        let winning_trades: Vec<&Trade> = results.trades.iter().filter(|t| t.pnl > 0.0).collect();
        let losing_trades: Vec<&Trade> = results.trades.iter().filter(|t| t.pnl <= 0.0).collect();
        
        let avg_win = if !winning_trades.is_empty() {
            winning_trades.iter().map(|t| t.pnl).sum::<f64>() / winning_trades.len() as f64
        } else {
            0.0
        };
        
        let avg_loss = if !losing_trades.is_empty() {
            losing_trades.iter().map(|t| t.pnl.abs()).sum::<f64>() / losing_trades.len() as f64
        } else {
            0.0
        };
        
        report.push_str(&format!("  Average Win: {:.2}%\n", avg_win * 100.0));
        report.push_str(&format!("  Average Loss: {:.2}%\n", avg_loss * 100.0));
        
        if let Some(best_trade) = results.trades.iter().max_by(|a, b| a.pnl.partial_cmp(&b.pnl).unwrap()) {
            report.push_str(&format!("  Best Trade: ${:.2}\n", best_trade.pnl));
        }
        
        if let Some(worst_trade) = results.trades.iter().min_by(|a, b| a.pnl.partial_cmp(&b.pnl).unwrap()) {
            report.push_str(&format!("  Worst Trade: ${:.2}\n", worst_trade.pnl));
        }
    }
    
    report.push_str("\n=== END REPORT ===\n");
    
    report
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    #[test]
    fn test_simple_backtest_config() {
        let config = SimpleBacktestConfig::default();
        assert_eq!(config.initial_capital, 100_000.0);
        assert_eq!(config.commission_rate, 0.001);
    }

    #[test]
    fn test_simple_backtest_engine() -> Result<()> {
        let config = SimpleBacktestConfig::default();
        let engine = SimpleBacktestEngine::new(config)?;
        assert_eq!(engine.current_equity, 100_000.0);
        Ok(())
    }
}
