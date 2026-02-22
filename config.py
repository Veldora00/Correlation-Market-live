import os

SCALING = 1_000_000  # $1.00 = 1,000,000 micros
LMSR_B = float(os.getenv("LMSR_B", "500.0"))
Q_FLOOR = int(os.getenv("Q_FLOOR", "-5000"))
MAX_OI_PER_OUTCOME = int(os.getenv("MAX_OI_PER_OUTCOME", "20000"))
TRADES_FILE = os.getenv("TRADES_FILE", "trades.csv")
FREEZE_WINDOW = int(os.getenv("FREEZE_WINDOW", "15"))  # Seconds before close where trading stops

# Runtime mode switches
APP_MODE = os.getenv("APP_MODE", "simulation").strip().lower()
IS_LIVE_MODE = APP_MODE == "live"
ENABLE_BOT_TRADING = os.getenv("ENABLE_BOT_TRADING", "0" if IS_LIVE_MODE else "1") == "1"
ENABLE_SIMULATION_ENDPOINTS = os.getenv("ENABLE_SIMULATION_ENDPOINTS", "0" if IS_LIVE_MODE else "1") == "1"
MARKET_DURATION_SECONDS = int(os.getenv("MARKET_DURATION_SECONDS", "3600" if IS_LIVE_MODE else "60"))

# API safety defaults
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
