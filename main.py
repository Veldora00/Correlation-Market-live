import asyncio
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from config import (
    FREEZE_WINDOW,
    SCALING,
    ALLOWED_ORIGINS,
    ENABLE_BOT_TRADING,
    ENABLE_SIMULATION_ENDPOINTS,
    MARKET_DURATION_SECONDS,
)
from models import TradeRequest, Outcome, SimulationRequest
from oracle import ORACLE_CACHE
from market_registry import get_market, create_next_market, get_lock, get_all_active_markets
from vault import VAULT
from ledger import LEDGER
import engine_lmsr as engine
# UPDATED IMPORT:
from bot_simulator import run_market_bot_simulation, _make_bots, run_live_bot_tick


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])

BALANCE_LOCK = asyncio.Lock() 

# INITIALIZE BOT SWARM
BOT_SWARM = _make_bots(max_shares=20)


@app.on_event("startup")
async def startup():
    asyncio.create_task(LEDGER.start_worker())  # ✅ ADD THIS
    asyncio.create_task(ORACLE_CACHE.loop())
    await asyncio.sleep(2)
    asyncio.create_task(lifecycle_manager())
    if ENABLE_BOT_TRADING:
        asyncio.create_task(bot_manager())

async def bot_manager():
    """Background task: Bots trade every 3 seconds"""
    print("🤖 Bot Swarm Activated")
    while True:
        try:
            await asyncio.sleep(3.0) 
            active_ids = get_all_active_markets()
            
            for mid in active_ids:
                spec, state = get_market(mid)
                
                if time.time() > (spec.expiry_ts - FREEZE_WINDOW):
                    continue
                    
                lock = get_lock(mid)
                async with lock:
                    async with BALANCE_LOCK:
                        # Infinite Money Glitch for Bots (Keep them funded)
                        for bot in BOT_SWARM:
                            # FIX: Use .get() to avoid KeyError if bot is new
                            current_balance = VAULT.balances.get(bot.user_id, 0)
                            if current_balance < 10_000 * SCALING:
                                # This creates the key if it's missing
                                VAULT.balances[bot.user_id] = current_balance + 100_000 * SCALING

                        trades = await run_live_bot_tick(mid, spec, state, VAULT, BOT_SWARM)

                        if trades > 0:
                          
                          print(f"🤖 Bots just made {trades} trades on {mid}")
        except Exception as e:
            print(f"Bot Error: {e}")

async def lifecycle_manager():
    """Background task that manages ALL active markets."""
    await create_next_market(duration=MARKET_DURATION_SECONDS)
    
    while True:
        try:
            active_ids = get_all_active_markets()
            
            if not active_ids: 
                 await create_next_market(duration=MARKET_DURATION_SECONDS)

            for mid in active_ids:
                spec, state = get_market(mid)
                
                if time.time() > spec.expiry_ts:
                    lock = get_lock(mid)
                    async with lock:
                        if not state.is_settled:
                            btc_end = ORACLE_CACHE.prices["BTC"]
                            eth_end = ORACLE_CACHE.prices["ETH"]
                            
                            btc_win = btc_end > spec.targets["BTC"]
                            eth_win = eth_end > spec.targets["ETH"]
                            
                            winner = Outcome.NN
                            if btc_win and eth_win: winner = Outcome.YY
                            elif btc_win and not eth_win: winner = Outcome.YN
                            elif not btc_win and eth_win: winner = Outcome.NY
                            
                            state.is_settled = True
                            state.winner = winner
                            await VAULT.settle_market(mid, winner, state)
                            asyncio.create_task(create_next_market(duration=MARKET_DURATION_SECONDS))
        except Exception as e:
            print(f"Lifecycle Error: {e}")
            
        await asyncio.sleep(1)

@app.post("/markets/{market_id}/trade")
async def trade_endpoint(market_id: str, req: TradeRequest):
    if req.market_id != market_id:
        raise HTTPException(400, "Path market_id must match request body market_id")

    if ORACLE_CACHE.is_stale(max_age=5.0) or not ORACLE_CACHE.is_healthy:
        raise HTTPException(503, "Oracle Unstable/Stale")

    try:
        spec, state = get_market(market_id)
    except KeyError:
        raise HTTPException(404, "Market not found")

    if time.time() > (spec.expiry_ts - FREEZE_WINDOW):
        raise HTTPException(400, "Market Frozen")

    lock = get_lock(market_id)
    async with lock:
        async with BALANCE_LOCK:
            success, msg = VAULT.execute_trade(
                user_id=req.user_id,
                market_id=market_id,
                outcome=req.outcome,
                amount=req.amount_shares,
                spec=spec,
                state=state
            )

    if not success:
        raise HTTPException(400, msg)

    prices = engine.get_prices(state.q, spec.lmsr_b)
    return {"status": "success", "prices": prices}

@app.post("/markets/{market_id}/simulate-bots")
async def simulate_bots_endpoint(market_id: str, req: SimulationRequest):
    if not ENABLE_SIMULATION_ENDPOINTS:
        raise HTTPException(403, "Simulation endpoint disabled in live mode")
    if req.market_id != market_id:
        raise HTTPException(400, "Path market_id must match request body market_id")

    try:
        spec, state = get_market(market_id)
    except KeyError:
        raise HTTPException(404, "Market not found")

    summary = run_market_bot_simulation(
        spec=spec,
        initial_state=state,
        steps=req.steps,
        starting_balance=req.starting_balance * SCALING,
        max_shares_per_trade=req.max_shares_per_trade,
        seed=req.seed,
    )

    return {
        "market_id": market_id,
        "simulation": summary
    }

@app.get("/markets")
async def list_markets():
    ids = get_all_active_markets()
    return {"active_markets": ids}

@app.get("/markets/{market_id}")
async def get_market_info(market_id: str):
    try:
        spec, state = get_market(market_id)
    except KeyError:
        raise HTTPException(404, "Market not found")

    prices = engine.get_prices(state.q, spec.lmsr_b)
    
    return {
        "market_id": spec.market_id,
        "prices": prices,
        "collateral": state.collateral_micros / SCALING,
        "seconds_left": max(0, int(spec.expiry_ts - time.time())),
        "targets": spec.targets
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
