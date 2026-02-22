
# market_registry.py
import time
import asyncio
import math
from typing import Dict, List, Tuple
from config import SCALING, LMSR_B
from models import MarketSpec, MarketState
from oracle import ORACLE_CACHE

# DATA STORES
MARKET_SPECS: Dict[str, MarketSpec] = {}
MARKET_STATES: Dict[str, MarketState] = {}
MARKET_LOCKS: Dict[str, asyncio.Lock] = {}

def get_market(market_id: str) -> Tuple[MarketSpec, MarketState]:
    if market_id not in MARKET_SPECS:
        raise KeyError("Market not found")
    return MARKET_SPECS[market_id], MARKET_STATES[market_id]

def get_lock(market_id: str) -> asyncio.Lock:
    if market_id not in MARKET_LOCKS:
        MARKET_LOCKS[market_id] = asyncio.Lock()
    return MARKET_LOCKS[market_id]

def get_all_active_markets() -> List[str]:
    return [mid for mid, state in MARKET_STATES.items() if not state.is_settled]

async def create_next_market(duration=60):
    # Wait for oracle
    while not ORACLE_CACHE.is_healthy:
        await asyncio.sleep(1)

    market_id = f"CORR_{int(time.time())}"
    expiry = time.time() + duration
    
    targets = {
        "BTC": ORACLE_CACHE.prices["BTC"],
        "ETH": ORACLE_CACHE.prices["ETH"]
    }

    spec = MarketSpec(market_id=market_id, targets=targets, expiry_ts=expiry, lmsr_b=LMSR_B)
    state = MarketState()
    
    # Seed Subsidy
    subsidy_shares = LMSR_B * math.log(4)
    state.collateral_micros = int(math.ceil(subsidy_shares * SCALING))

    MARKET_SPECS[market_id] = spec
    MARKET_STATES[market_id] = state
    MARKET_LOCKS[market_id] = asyncio.Lock()
    
    print(f"🏁 Created Market: {market_id} | Targets: {targets}")
    return market_id
