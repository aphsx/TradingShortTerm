/// config.rs — Centralised configuration loaded from .env
///
/// All parameters consumed by the MFT engine are defined here.
/// Loading happens once at startup; every module borrows &AppConfig.
use anyhow::Result;
use std::env;

/// Fee model constants (Binance USDT-M Futures defaults)
/// Maker:  0.02% = 0.0002
/// Taker:  0.05% = 0.0005
/// Total round-trip (taker in + taker out): 0.0010
pub const DEFAULT_MAKER_FEE: f64 = 0.0002;
pub const DEFAULT_TAKER_FEE: f64 = 0.0005;
pub const DEFAULT_SLIPPAGE:  f64 = 0.0003; // 3bps conservative estimate

#[derive(Debug, Clone)]
pub struct AppConfig {
    // ── Binance credentials ───────────────────────────────────────────
    pub api_key:    String,
    pub api_secret: String,
    pub use_testnet: bool,

    // ── REST / WS endpoints ──────────────────────────────────────────
    pub rest_url: String,
    pub ws_url:   String,

    // ── Trading universe ─────────────────────────────────────────────
    pub trading_pairs: Vec<String>,

    // ── Capital & risk ───────────────────────────────────────────────
    /// Initial account equity in USDT
    pub initial_capital: f64,
    /// Fraction of equity risked per trade (Kelly-capped)
    pub risk_per_trade:  f64,
    /// Maximum leverage multiplier
    pub max_leverage: u32,

    // ── Fee / slippage model ─────────────────────────────────────────
    pub maker_fee:  f64,
    pub taker_fee:  f64,
    pub slippage:   f64,

    // ── GARCH(1,1) priors ────────────────────────────────────────────
    /// Long-run variance ω — tune to asset's typical daily vol²
    pub garch_omega: f64,
    /// ARCH coefficient α (shock sensitivity)
    pub garch_alpha: f64,
    /// GARCH coefficient β (variance persistence)
    pub garch_beta:  f64,

    // ── Ornstein-Uhlenbeck entry/exit thresholds ─────────────────────
    /// Enter when |Z-score| >= ou_entry_z  (default: 2.0 σ)
    pub ou_entry_z: f64,
    /// Exit  when |Z-score| <= ou_exit_z   (default: 0.5 σ)
    pub ou_exit_z:  f64,
    /// OU estimation window (number of bars)
    pub ou_window:  usize,

    // ── OFI / VPIN settings ──────────────────────────────────────────
    /// Number of ticks in each VPIN "volume bucket"
    pub vpin_bucket_size: usize,
    /// Number of buckets in rolling VPIN window
    pub vpin_n_buckets:   usize,
    /// Minimum VPIN to confirm directional signal
    pub vpin_threshold:   f64,

    // ── EV gate ─────────────────────────────────────────────────────
    /// Minimum fee-adjusted Expected Value to open a position
    pub min_ev: f64,
    /// Minimum probability of winning (from PDF model)
    pub min_p_win: f64,

    // ── Position management ──────────────────────────────────────────
    /// Hard stop-loss as fraction of entry price (e.g. 0.003 = 30bps)
    pub stop_loss_frac: f64,
    /// Probability threshold: exit when P(continue) < this value
    pub exit_prob_threshold: f64,
    /// Maximum bars a position may be held (time-stop)
    pub max_hold_bars: usize,

    // ── Backtesting data ─────────────────────────────────────────────
    pub kline_interval:  String,
    pub backtest_symbol: String,
    pub backtest_limit:  u64,
}

impl AppConfig {
    /// Load configuration from environment variables (after dotenv).
    pub fn from_env() -> Result<Self> {
        dotenv::dotenv().ok(); // ignore missing .env

        let api_key    = env::var("BINANCE_API_KEY").unwrap_or_default();
        let api_secret = env::var("BINANCE_API_SECRET").unwrap_or_default();
        let use_testnet = env::var("BINANCE_USE_TESTNET")
            .unwrap_or_else(|_| "true".into())
            .to_lowercase()
            == "true";

        let rest_url = env::var("BINANCE_FUTURES_REST_URL").unwrap_or_else(|_| {
            if use_testnet {
                "https://testnet.binancefuture.com".into()
            } else {
                "https://fapi.binance.com".into()
            }
        });
        let ws_url = env::var("BINANCE_FUTURES_WS_URL")
            .unwrap_or_else(|_| "wss://fstream.binancefuture.com".into());

        let trading_pairs: Vec<String> = env::var("TRADING_PAIRS")
            .unwrap_or_else(|_| "BTCUSDT".into())
            .split(',')
            .map(|s| s.trim().to_owned())
            .collect();

        Ok(Self {
            api_key,
            api_secret,
            use_testnet,
            rest_url,
            ws_url,
            trading_pairs,

            initial_capital: parse_env("INITIAL_CAPITAL", 1000.0)?,
            risk_per_trade:  parse_env("RISK_PER_TRADE",  0.01)?,
            max_leverage:    parse_env::<u32>("MAX_LEVERAGE", 10)?,

            maker_fee: parse_env("MAKER_FEE", DEFAULT_MAKER_FEE)?,
            taker_fee: parse_env("TAKER_FEE", DEFAULT_TAKER_FEE)?,
            slippage:  parse_env("SLIPPAGE",  DEFAULT_SLIPPAGE)?,

            // GARCH priors — can be overridden via env once stability measured
            garch_omega: parse_env("GARCH_OMEGA", 1e-6)?,
            garch_alpha: parse_env("GARCH_ALPHA", 0.10)?,
            garch_beta:  parse_env("GARCH_BETA",  0.85)?,

            ou_entry_z: parse_env("OU_ENTRY_Z", 2.0)?,
            ou_exit_z:  parse_env("OU_EXIT_Z",  0.5)?,
            ou_window:  parse_env("OU_WINDOW",  120usize)?,

            vpin_bucket_size: parse_env("VPIN_BUCKET_SIZE", 50usize)?,
            vpin_n_buckets:   parse_env("VPIN_N_BUCKETS",   50usize)?,
            vpin_threshold:   parse_env("VPIN_THRESHOLD",   0.35)?,

            min_ev:    parse_env("MIN_EV",     0.0001)?,
            min_p_win: parse_env("MIN_P_WIN",  0.52)?,

            stop_loss_frac:       parse_env("STOP_LOSS_FRAC",        0.003)?,
            exit_prob_threshold:  parse_env("EXIT_PROB_THRESHOLD",   0.30)?,
            max_hold_bars:        parse_env("MAX_HOLD_BARS",         60usize)?,

            kline_interval:  env::var("KLINE_INTERVAL").unwrap_or_else(|_| "1m".into()),
            backtest_symbol: env::var("BACKTEST_SYMBOL").unwrap_or_else(|_| "BTCUSDT".into()),
            backtest_limit:  parse_env("BACKTEST_LIMIT", 1000u64)?,
        })
    }
}

fn parse_env<T>(key: &str, default: T) -> Result<T>
where
    T: std::str::FromStr + Copy,
    T::Err: std::fmt::Display,
{
    match env::var(key) {
        Ok(v) => v
            .parse::<T>()
            .map_err(|e| anyhow::anyhow!("Config key {key}: {e}")),
        Err(_) => Ok(default),
    }
}
