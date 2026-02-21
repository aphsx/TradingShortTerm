import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_API_SECRET", os.getenv("BINANCE_SECRET_KEY", ""))
TESTNET_ENV = os.getenv("BINANCE_USE_TESTNET", os.getenv("BINANCE_TESTNET", "true"))
TESTNET = TESTNET_ENV.lower() == "true"

TRADING_PAIRS = os.getenv("TRADING_PAIRS", "BTCUSDT,ETHUSDT").split(",")
BASE_BALANCE = float(os.getenv("BASE_BALANCE", "500"))
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "12"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
