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
QUOTE_TTL_SECONDS = int(os.getenv("QUOTE_TTL_SECONDS", "300"))
MARKET_DURATION_SECONDS = 3600 

# --- Helpers ---
IS_CHAIN_MODE = True
IS_LIVE_MODE = False
ALLOWED_ORIGINS = ["*"]

# --- Safety Check ---
if not SIGNER_PRIVATE_KEY:
    raise RuntimeError("SIGNER_PRIVATE_KEY environment variable is missing!")
