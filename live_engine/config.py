"""
config.py — Centralized configuration for the live trading engine.
Uses Pydantic for validation. All values can be overridden via .env.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class TradingConfig(BaseSettings):
    # ── Binance API ──────────────────────────────────────────────
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    binance_use_testnet: bool = Field(default=True, alias="BINANCE_USE_TESTNET")

    # ── Endpoints ────────────────────────────────────────────────
    futures_rest_url: str = Field(
        default="https://fapi.binance.com",
        alias="BINANCE_FUTURES_REST_URL",
    )
    futures_ws_url: str = Field(
        default="wss://fstream.binance.com",
        alias="BINANCE_FUTURES_WS_URL",
    )

    # ── Trading Pairs ────────────────────────────────────────────
    trading_pairs: list[str] = Field(
        default=["BTCUSDT"],
        alias="TRADING_PAIRS",
    )
    leverage: int = 10

    # ── Volume Bar Aggregator ────────────────────────────────────
    volume_bar_threshold_usd: float = 50_000.0

    # ── Indicator Periods ────────────────────────────────────────
    ema_fast: int = 9
    ema_medium: int = 21
    ema_trend: int = 50
    rsi_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    bb_squeeze_lookback: int = 60
    vwap_period: int = 20

    # ── Entry Filters ────────────────────────────────────────────
    rsi_long_min: float = 45.0
    rsi_long_max: float = 68.0
    rsi_short_min: float = 32.0
    rsi_short_max: float = 55.0
    rvol_threshold: float = 1.3
    min_ema_spread_pct: float = 0.0005
    min_atr_pct: float = 0.001
    entry_mode: str = "hybrid"  # breakout | mean_rev | hybrid

    # ── Risk Management ──────────────────────────────────────────
    risk_per_trade_pct: float = 0.01       # 1% risk per trade
    atr_sl_multiplier: float = 2.0
    atr_tp_multiplier: float = 4.0
    trailing_activate_atr: float = 2.0
    trailing_distance_atr: float = 1.0
    max_position_pct: float = 0.25

    # ── Circuit Breakers ─────────────────────────────────────────
    max_daily_loss_pct: float = 0.03       # 3% daily loss → halt
    max_drawdown_pct: float = 0.10         # 10% drawdown → halt
    max_consecutive_losses: int = 5
    max_daily_trades: int = 50
    max_latency_ms: float = 500.0
    cooldown_bars: int = 10
    pause_bars_after_streak: int = 60

    # ── Rate Limiting ────────────────────────────────────────────
    api_weight_limit: int = 2400
    api_weight_window_sec: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def rest_base(self) -> str:
        if self.binance_use_testnet:
            return "https://testnet.binancefuture.com"
        return self.futures_rest_url

    @property
    def ws_base(self) -> str:
        if self.binance_use_testnet:
            return "wss://stream.binancefuture.com"
        return self.futures_ws_url
