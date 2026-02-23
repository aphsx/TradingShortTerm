use nautilus_backtest::engine::BacktestEngine;
use nautilus_backtest::config::BacktestEngineConfig;

fn main() {
    let mut engine = BacktestEngine::new(BacktestEngineConfig::default()).unwrap();
    // let _ = engine.trader(); // Try this
}
