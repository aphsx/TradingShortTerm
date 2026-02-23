/// lib.rs — Unified Backtest Library
///
/// Main library for the MFT unified backtest system that integrates the MFT engine
/// with NautilusTrader for comprehensive backtesting capabilities.

pub mod simple_backtest;

pub use simple_backtest::*;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_library_imports() {
        // Test that all modules can be imported
        let _config = SimpleBacktestConfig::default();
    }
}
