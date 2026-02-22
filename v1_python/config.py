"""
config.py – Centralised configuration with Pydantic v2 validation.

All settings are loaded from environment variables (via .env).
Pydantic validates types, ranges, and mandatory fields at startup so the bot
fails fast with a clear message instead of silently trading with bad values.
"""

import os
import sys
from typing import List

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Optional Pydantic import – fail clearly if it's missing
# ---------------------------------------------------------------------------
try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    from pydantic import ValidationError
    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False


def _env_list(key: str, default: str) -> List[str]:
    """Read a comma-separated env var and return a list of stripped strings."""
    return [s.strip() for s in os.getenv(key, default).split(",") if s.strip()]


# ---------------------------------------------------------------------------
# Pydantic settings model
# ---------------------------------------------------------------------------
if _PYDANTIC_AVAILABLE:
    class BotConfig(BaseModel):
        # ── Exchange credentials ──────────────────────────────────────────
        api_key: str = Field(default="")
        secret_key: str = Field(default="")
        testnet: bool = Field(default=True)

        binance_futures_rest_url: str = Field(default="")
        binance_futures_ws_url: str = Field(default="")

        # ── Trading pairs & capital ───────────────────────────────────────
        trading_pairs: List[str] = Field(default=["BTCUSDT", "ETHUSDT"])
        base_balance: float = Field(default=100.0, gt=0)
        min_leverage: int = Field(default=10, ge=1, le=125)
        max_leverage: int = Field(default=30, ge=1, le=125)
        risk_per_trade: float = Field(default=0.01, gt=0, le=0.10)

        # ── Fee & slippage model ──────────────────────────────────────────
        exchange_taker_fee: float = Field(default=0.0005, ge=0, le=0.01)
        slippage_buffer: float = Field(default=0.0004, ge=0, le=0.05)
        min_rr_ratio: float = Field(default=2.0, gt=0)

        # ── Engine sensitivities ──────────────────────────────────────────
        e1_imbalance_threshold: float = Field(default=0.15, gt=0, lt=1)
        e2_momentum_threshold: float = Field(default=0.55, gt=0.5, lt=1)
        e4_funding_rate_threshold: float = Field(default=0.00015, ge=0)

        # ── DecisionEngine predictive filters ────────────────────────────
        # These were previously hardcoded inside core.py
        decision_vpin_min: float = Field(default=0.35, ge=0, le=1)
        decision_ofi_velocity_min: float = Field(default=1.5, ge=0)
        decision_alignment_min: float = Field(default=0.35, ge=0, le=1)

        # ── Strategy global thresholds ────────────────────────────────────
        strat_min_score: float = Field(default=0.18, ge=0, lt=1)
        strat_agreement_req: int = Field(default=1, ge=1, le=4)

        # ── Strategy A (Momentum Breakout) ────────────────────────────────
        strata_v_rat_trigger: float = Field(default=1.2, gt=0)
        strata_streak_trigger: int = Field(default=3, ge=1)
        strata_s_rat_trigger: float = Field(default=1.4, gt=0)

        # ── Strategy B (Mean Reversion) ────────────────────────────────────
        stratb_rsi_lower: float = Field(default=35.0, ge=0, le=50)
        stratb_rsi_upper: float = Field(default=65.0, ge=50, le=100)

        # ── Strategy C (Liquidation Scalp) ────────────────────────────────
        stratc_liq_proximity: float = Field(default=0.40, ge=0, le=1)
        stratc_s_rat_trigger: float = Field(default=1.5, gt=0)

        # ── Infrastructure ────────────────────────────────────────────────
        redis_host: str = Field(default="localhost")
        redis_port: int = Field(default=6379, ge=1, le=65535)
        supabase_url: str = Field(default="")
        supabase_key: str = Field(default="")
        db_log_interval: int = Field(default=300, ge=10)

        # ── Optional integrations ─────────────────────────────────────────
        telegram_bot_token: str = Field(default="")
        telegram_chat_id: str = Field(default="")
        dashboard_secret: str = Field(default="password")

        # ── Cross-field validation ────────────────────────────────────────
        @model_validator(mode="after")
        def validate_leverage_order(self) -> "BotConfig":
            if self.min_leverage > self.max_leverage:
                raise ValueError(
                    f"MIN_LEVERAGE ({self.min_leverage}) must be ≤ MAX_LEVERAGE ({self.max_leverage})"
                )
            return self

        @model_validator(mode="after")
        def validate_rsi_order(self) -> "BotConfig":
            if self.stratb_rsi_lower >= self.stratb_rsi_upper:
                raise ValueError(
                    f"STRATB_RSI_LOWER ({self.stratb_rsi_lower}) must be < STRATB_RSI_UPPER ({self.stratb_rsi_upper})"
                )
            return self

        @field_validator("trading_pairs")
        @classmethod
        def validate_pairs(cls, v: List[str]) -> List[str]:
            if not v:
                raise ValueError("TRADING_PAIRS must contain at least one symbol")
            for pair in v:
                if not pair.endswith("USDT"):
                    raise ValueError(f"Trading pair '{pair}' must end with 'USDT'")
            return v


    def _load_config() -> BotConfig:
        """Load and validate configuration from environment variables."""
        testnet_raw = os.getenv("BINANCE_USE_TESTNET", os.getenv("BINANCE_TESTNET", "true"))

        try:
            cfg = BotConfig(
                api_key=os.getenv("BINANCE_API_KEY", ""),
                secret_key=os.getenv("BINANCE_API_SECRET", os.getenv("BINANCE_SECRET_KEY", "")),
                testnet=testnet_raw.lower() == "true",
                binance_futures_rest_url=os.getenv("BINANCE_FUTURES_REST_URL", ""),
                binance_futures_ws_url=os.getenv("BINANCE_FUTURES_WS_URL", ""),
                trading_pairs=_env_list("TRADING_PAIRS", "BTCUSDT,ETHUSDT"),
                base_balance=float(os.getenv("BASE_BALANCE", "100")),
                min_leverage=int(os.getenv("MIN_LEVERAGE", "10")),
                max_leverage=int(os.getenv("MAX_LEVERAGE", "30")),
                risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.01")),
                exchange_taker_fee=float(os.getenv("EXCHANGE_TAKER_FEE", "0.0005")),
                slippage_buffer=float(os.getenv("SLIPPAGE_BUFFER", "0.0004")),
                min_rr_ratio=float(os.getenv("MIN_RR_RATIO", "2.0")),
                e1_imbalance_threshold=float(os.getenv("E1_IMBALANCE_THRESHOLD", "0.15")),
                e2_momentum_threshold=float(os.getenv("E2_MOMENTUM_THRESHOLD", "0.55")),
                e4_funding_rate_threshold=float(os.getenv("E4_FUNDING_RATE_THRESHOLD", "0.00015")),
                decision_vpin_min=float(os.getenv("DECISION_VPIN_MIN", "0.35")),
                decision_ofi_velocity_min=float(os.getenv("DECISION_OFI_VELOCITY_MIN", "1.5")),
                decision_alignment_min=float(os.getenv("DECISION_ALIGNMENT_MIN", "0.35")),
                strat_min_score=float(os.getenv("STRAT_MIN_SCORE", "0.18")),
                strat_agreement_req=int(os.getenv("STRAT_AGREEMENT_REQ", "1")),
                strata_v_rat_trigger=float(os.getenv("STRATA_V_RAT_TRIGGER", "1.2")),
                strata_streak_trigger=int(os.getenv("STRATA_STREAK_TRIGGER", "3")),
                strata_s_rat_trigger=float(os.getenv("STRATA_S_RAT_TRIGGER", "1.4")),
                stratb_rsi_lower=float(os.getenv("STRATB_RSI_LOWER", "35")),
                stratb_rsi_upper=float(os.getenv("STRATB_RSI_UPPER", "65")),
                stratc_liq_proximity=float(os.getenv("STRATC_LIQ_PROXIMITY", "0.40")),
                stratc_s_rat_trigger=float(os.getenv("STRATC_S_RAT_TRIGGER", "1.5")),
                redis_host=os.getenv("REDIS_HOST", "localhost"),
                redis_port=int(os.getenv("REDIS_PORT", "6379")),
                supabase_url=os.getenv("SUPABASE_URL", ""),
                supabase_key=os.getenv("SUPABASE_KEY", ""),
                db_log_interval=int(os.getenv("DB_LOG_INTERVAL", "300")),
                telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
                dashboard_secret=os.getenv("DASHBOARD_SECRET", "password"),
            )
            return cfg

        except ValidationError as exc:
            print("\n" + "="*60)
            print("❌  CONFIG VALIDATION ERROR — Bot cannot start!")
            print("="*60)
            for err in exc.errors():
                field = " → ".join(str(x) for x in err["loc"])
                print(f"  • [{field}]  {err['msg']}")
            print("="*60 + "\n")
            sys.exit(1)
        except (ValueError, TypeError) as exc:
            print(f"\n❌  CONFIG PARSE ERROR: {exc}\n")
            sys.exit(1)


    _cfg = _load_config()

    # ---------------------------------------------------------------------------
    # Public constants – same names as before so imports don't need changing
    # ---------------------------------------------------------------------------
    API_KEY = _cfg.api_key
    SECRET_KEY = _cfg.secret_key
    TESTNET = _cfg.testnet

    BINANCE_FUTURES_REST_URL = _cfg.binance_futures_rest_url
    BINANCE_FUTURES_WS_URL = _cfg.binance_futures_ws_url

    TRADING_PAIRS = _cfg.trading_pairs
    BASE_BALANCE = _cfg.base_balance
    MIN_LEVERAGE = _cfg.min_leverage
    MAX_LEVERAGE = _cfg.max_leverage
    RISK_PER_TRADE = _cfg.risk_per_trade

    EXCHANGE_TAKER_FEE = _cfg.exchange_taker_fee
    SLIPPAGE_BUFFER = _cfg.slippage_buffer
    MIN_RR_RATIO = _cfg.min_rr_ratio

    E1_IMBALANCE_THRESHOLD = _cfg.e1_imbalance_threshold
    E2_MOMENTUM_THRESHOLD = _cfg.e2_momentum_threshold
    E4_FUNDING_RATE_THRESHOLD = _cfg.e4_funding_rate_threshold

    # Predictive-filter thresholds (previously hardcoded in core.py)
    DECISION_VPIN_MIN = _cfg.decision_vpin_min
    DECISION_OFI_VELOCITY_MIN = _cfg.decision_ofi_velocity_min
    DECISION_ALIGNMENT_MIN = _cfg.decision_alignment_min

    STRAT_MIN_SCORE = _cfg.strat_min_score
    STRAT_AGREEMENT_REQ = _cfg.strat_agreement_req

    STRATA_V_RAT_TRIGGER = _cfg.strata_v_rat_trigger
    STRATA_STREAK_TRIGGER = _cfg.strata_streak_trigger
    STRATA_S_RAT_TRIGGER = _cfg.strata_s_rat_trigger

    STRATB_RSI_LOWER = _cfg.stratb_rsi_lower
    STRATB_RSI_UPPER = _cfg.stratb_rsi_upper

    STRATC_LIQ_PROXIMITY = _cfg.stratc_liq_proximity
    STRATC_S_RAT_TRIGGER = _cfg.stratc_s_rat_trigger

    REDIS_HOST = _cfg.redis_host
    REDIS_PORT = _cfg.redis_port
    SUPABASE_URL = _cfg.supabase_url
    SUPABASE_KEY = _cfg.supabase_key
    DB_LOG_INTERVAL = _cfg.db_log_interval

    TELEGRAM_BOT_TOKEN = _cfg.telegram_bot_token
    TELEGRAM_CHAT_ID = _cfg.telegram_chat_id
    DASHBOARD_SECRET = _cfg.dashboard_secret

else:
    # ---------------------------------------------------------------------------
    # Fallback: Pydantic not installed → read env vars directly (no validation)
    # ---------------------------------------------------------------------------
    import warnings
    warnings.warn(
        "pydantic is not installed — config validation is DISABLED. "
        "Run `pip install pydantic` for safer operation.",
        stacklevel=2,
    )

    _testnet_raw = os.getenv("BINANCE_USE_TESTNET", os.getenv("BINANCE_TESTNET", "true"))

    API_KEY   = os.getenv("BINANCE_API_KEY", "")
    SECRET_KEY = os.getenv("BINANCE_API_SECRET", os.getenv("BINANCE_SECRET_KEY", ""))
    TESTNET   = _testnet_raw.lower() == "true"

    BINANCE_FUTURES_REST_URL = os.getenv("BINANCE_FUTURES_REST_URL", "")
    BINANCE_FUTURES_WS_URL   = os.getenv("BINANCE_FUTURES_WS_URL", "")

    TRADING_PAIRS = _env_list("TRADING_PAIRS", "BTCUSDT,ETHUSDT")
    BASE_BALANCE  = float(os.getenv("BASE_BALANCE", "100"))
    MIN_LEVERAGE  = int(os.getenv("MIN_LEVERAGE", "10"))
    MAX_LEVERAGE  = int(os.getenv("MAX_LEVERAGE", "30"))
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

    EXCHANGE_TAKER_FEE = float(os.getenv("EXCHANGE_TAKER_FEE", "0.0005"))
    SLIPPAGE_BUFFER    = float(os.getenv("SLIPPAGE_BUFFER", "0.0004"))
    MIN_RR_RATIO       = float(os.getenv("MIN_RR_RATIO", "2.0"))

    E1_IMBALANCE_THRESHOLD    = float(os.getenv("E1_IMBALANCE_THRESHOLD", "0.15"))
    E2_MOMENTUM_THRESHOLD     = float(os.getenv("E2_MOMENTUM_THRESHOLD", "0.55"))
    E4_FUNDING_RATE_THRESHOLD = float(os.getenv("E4_FUNDING_RATE_THRESHOLD", "0.00015"))

    DECISION_VPIN_MIN          = float(os.getenv("DECISION_VPIN_MIN", "0.35"))
    DECISION_OFI_VELOCITY_MIN  = float(os.getenv("DECISION_OFI_VELOCITY_MIN", "1.5"))
    DECISION_ALIGNMENT_MIN     = float(os.getenv("DECISION_ALIGNMENT_MIN", "0.35"))

    STRAT_MIN_SCORE     = float(os.getenv("STRAT_MIN_SCORE", "0.18"))
    STRAT_AGREEMENT_REQ = int(os.getenv("STRAT_AGREEMENT_REQ", "1"))

    STRATA_V_RAT_TRIGGER  = float(os.getenv("STRATA_V_RAT_TRIGGER", "1.2"))
    STRATA_STREAK_TRIGGER = int(os.getenv("STRATA_STREAK_TRIGGER", "3"))
    STRATA_S_RAT_TRIGGER  = float(os.getenv("STRATA_S_RAT_TRIGGER", "1.4"))

    STRATB_RSI_LOWER = float(os.getenv("STRATB_RSI_LOWER", "35"))
    STRATB_RSI_UPPER = float(os.getenv("STRATB_RSI_UPPER", "65"))

    STRATC_LIQ_PROXIMITY  = float(os.getenv("STRATC_LIQ_PROXIMITY", "0.40"))
    STRATC_S_RAT_TRIGGER  = float(os.getenv("STRATC_S_RAT_TRIGGER", "1.5"))

    REDIS_HOST    = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT    = int(os.getenv("REDIS_PORT", "6379"))
    SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY  = os.getenv("SUPABASE_KEY", "")
    DB_LOG_INTERVAL = int(os.getenv("DB_LOG_INTERVAL", "300"))

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
    DASHBOARD_SECRET   = os.getenv("DASHBOARD_SECRET", "password")
