
import os

# --- MANDATORY BLOCK FOR CHAIN MODE ---
APP_MODE = "chain"  # Force chain mode
CONTRACT_ADDRESS = "0xf8e81D47203A594245E36C48e151709F0C19fBe8"
CHAIN_ID = 1337     # Match Remix VM
# You MUST set this in your terminal or .env file
SIGNER_PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY") 

# --- LMSR & Market Logic ---
SCALING = 1_000_000
LMSR_B = float(os.getenv("LMSR_B", "500.0"))
Q_FLOOR = int(os.getenv("Q_FLOOR", "-5000"))
MAX_OI_PER_OUTCOME = int(os.getenv("MAX_OI_PER_OUTCOME", "20000"))
TRADES_FILE = os.getenv("TRADES_FILE", "trades.csv")
FREEZE_WINDOW = int(os.getenv("FREEZE_WINDOW", "15"))
QUOTE_TTL_SECONDS = int(os.getenv("QUOTE_TTL_SECONDS", "10"))
MARKET_DURATION_SECONDS = 3600 

# --- Helpers ---
IS_CHAIN_MODE = True
IS_LIVE_MODE = False
ALLOWED_ORIGINS = ["*"]

# --- Safety Check ---
if not SIGNER_PRIVATE_KEY:
    raise RuntimeError("SIGNER_PRIVATE_KEY environment variable is missing!")

# CHAIN mode signer configuration
SIGNER_PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY")
CHAIN_ID = int(os.getenv("CHAIN_ID", "421614"))
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
QUOTE_TTL_SECONDS = int(os.getenv("QUOTE_TTL_SECONDS", "10"))

if IS_CHAIN_MODE and not SIGNER_PRIVATE_KEY:
    raise RuntimeError("SIGNER_PRIVATE_KEY is required in CHAIN mode")
if IS_CHAIN_MODE and not CONTRACT_ADDRESS:
    raise RuntimeError("CONTRACT_ADDRESS is required in CHAIN mode")

# API safety defaults
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]


SCALING = 1_000_000  # $1.00 = 1,000,000 micros
LMSR_B = float(os.getenv("LMSR_B", "500.0"))
Q_FLOOR = int(os.getenv("Q_FLOOR", "-5000"))
MAX_OI_PER_OUTCOME = int(os.getenv("MAX_OI_PER_OUTCOME", "20000"))
TRADES_FILE = os.getenv("TRADES_FILE", "trades.csv")
FREEZE_WINDOW = int(os.getenv("FREEZE_WINDOW", "15"))

# Runtime mode switches
APP_MODE = os.getenv("APP_MODE", "sim").strip().lower()  # sim | chain | live
IS_LIVE_MODE = APP_MODE == "live"
IS_CHAIN_MODE = APP_MODE == "chain"


MARKET_DURATION_SECONDS = int(os.getenv("MARKET_DURATION_SECONDS", "3600" if (IS_LIVE_MODE or IS_CHAIN_MODE) else "60"))

# CHAIN mode signer configuration
SIGNER_PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY")
CHAIN_ID = int(os.getenv("CHAIN_ID", "421614"))
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
QUOTE_TTL_SECONDS = int(os.getenv("QUOTE_TTL_SECONDS", "10"))

if IS_CHAIN_MODE and not SIGNER_PRIVATE_KEY:
    raise RuntimeError("SIGNER_PRIVATE_KEY is required in CHAIN mode")
if IS_CHAIN_MODE and not CONTRACT_ADDRESS:
    raise RuntimeError("CONTRACT_ADDRESS is required in CHAIN mode")

# API safety defaults
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
