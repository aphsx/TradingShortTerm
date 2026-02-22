import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_API_SECRET", os.getenv("BINANCE_SECRET_KEY", ""))
TESTNET_ENV = os.getenv("BINANCE_USE_TESTNET", os.getenv("BINANCE_TESTNET", "true"))
TESTNET = TESTNET_ENV.lower() == "true"

BINANCE_FUTURES_REST_URL = os.getenv("BINANCE_FUTURES_REST_URL", "")
BINANCE_FUTURES_WS_URL = os.getenv("BINANCE_FUTURES_WS_URL", "")

TRADING_PAIRS = os.getenv("TRADING_PAIRS", "BTCUSDT,ETHUSDT").split(",")
BASE_BALANCE = float(os.getenv("BASE_BALANCE", "100"))
MIN_LEVERAGE = int(os.getenv("MIN_LEVERAGE", "10"))
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "30"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

EXCHANGE_TAKER_FEE = float(os.getenv("EXCHANGE_TAKER_FEE", "0.0005")) # Binance Futures 0.05%
SLIPPAGE_BUFFER = float(os.getenv("SLIPPAGE_BUFFER", "0.0004"))       # 0.04% slippage expectation
MIN_RR_RATIO = float(os.getenv("MIN_RR_RATIO", "0.8"))                # Scalper R:R floor

E1_IMBALANCE_THRESHOLD = float(os.getenv("E1_IMBALANCE_THRESHOLD", "0.15"))
E2_MOMENTUM_THRESHOLD = float(os.getenv("E2_MOMENTUM_THRESHOLD", "0.55"))
E4_FUNDING_RATE_THRESHOLD = float(os.getenv("E4_FUNDING_RATE_THRESHOLD", "0.00015"))

STRAT_MIN_SCORE = float(os.getenv("STRAT_MIN_SCORE", "0.25"))
STRAT_AGREEMENT_REQ = int(os.getenv("STRAT_AGREEMENT_REQ", "2"))

STRATA_V_RAT_TRIGGER = float(os.getenv("STRATA_V_RAT_TRIGGER", "1.5"))
STRATA_STREAK_TRIGGER = int(os.getenv("STRATA_STREAK_TRIGGER", "5"))
STRATA_S_RAT_TRIGGER = float(os.getenv("STRATA_S_RAT_TRIGGER", "1.8"))

STRATB_RSI_LOWER = float(os.getenv("STRATB_RSI_LOWER", "35"))
STRATB_RSI_UPPER = float(os.getenv("STRATB_RSI_UPPER", "65"))

STRATC_LIQ_PROXIMITY = float(os.getenv("STRATC_LIQ_PROXIMITY", "0.40"))
STRATC_S_RAT_TRIGGER = float(os.getenv("STRATC_S_RAT_TRIGGER", "1.5"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# --- Database Saving Policy ---
# Only save non-trading signals every X seconds to reduce Supabase load.
# Trades and their corresponding signals are always saved immediately.
DB_LOG_INTERVAL = int(os.getenv("DB_LOG_INTERVAL", "300")) 

