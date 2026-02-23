use anyhow::Result;
use log::info;
use crate::models::{Side, Signal};

pub struct RiskManager {
    pub fractional_kelly: f64, // e.g., 0.2
    pub max_drawdown: f64,    // e.g., 0.1 (10%)
    pub current_drawdown: f64,
}

impl RiskManager {
    pub fn new(kelly: f64, max_dd: f64) -> Self {
        Self {
            fractional_kelly: kelly,
            max_drawdown: max_dd,
            current_drawdown: 0.0,
        }
    }

    pub fn calculate_position_size(&self, balance: f64, atr: f64, win_rate: f64, risk_reward: f64) -> f64 {
        // Fractional Kelly: f = (w * (R + 1) - 1) / R
        // w = win_rate, R = risk_reward ratio
        let kelly_f = (win_rate * (risk_reward + 1.0) - 1.0) / risk_reward;
        let constrained_kelly = kelly_f.max(0.0).min(1.0) * self.fractional_kelly;
        
        let amount_to_risk = balance * constrained_kelly;
        
        // ATR-based Stop distance (e.g., 2 * ATR)
        let stop_distance = atr * 2.0;
        
        if stop_distance <= 0.0 {
            return 0.0;
        }

        info!("Fractional Kelly: {}, Amount to risk: {}", constrained_kelly, amount_to_risk);
        amount_to_risk / stop_distance
    }

    pub fn chandelier_exit(&self, high: f64, low: f64, atr: f64, side: Side) -> f64 {
        match side {
            Side::Buy => high - (atr * 3.0),
            Side::Sell => low + (atr * 3.0),
            Side::None => 0.0,
        }
    }

    pub fn check_circuit_breaker(&self) -> bool {
        self.current_drawdown >= self.max_drawdown
    }
}
