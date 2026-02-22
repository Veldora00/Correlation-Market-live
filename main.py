import asyncio
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import engine_lmsr as engine
from bot_simulator import _make_bots, run_live_bot_tick, run_market_bot_simulation
from config import (
    ALLOWED_ORIGINS,
    APP_MODE,
    CHAIN_ID,
    CONTRACT_ADDRESS,
    ENABLE_SIMULATION_ENDPOINTS,
    FREEZE_WINDOW,
    MARKET_DURATION_SECONDS,
    QUOTE_TTL_SECONDS,
    RUN_BOTS,
    SCALING,
    SIGNER_PRIVATE_KEY,
)
from ledger import LEDGER
from market_registry import create_next_market, get_all_active_markets, get_lock, get_market
from models import Outcome, QuoteRequest, QuoteResponse, SimulationRequest, TradeRequest
from oracle import ORACLE_CACHE
from vault import VAULT


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

BALANCE_LOCK = asyncio.Lock()
BOT_SWARM = _make_bots(max_shares=20)

OUTCOME_TO_UINT8 = {
    Outcome.YY: 0,
    Outcome.YN: 1,
    Outcome.NY: 2,
    Outcome.NN: 3,
}

DOMAIN_DATA = {
    "name": "CorrelationMarket",
    "version": "1",
    "chainId": CHAIN_ID,
    "verifyingContract": CONTRACT_ADDRESS,
}

MESSAGE_TYPES = {
    "Quote": [
        {"name": "user", "type": "address"},
        {"name": "marketId", "type": "string"},
        {"name": "outcome", "type": "uint8"},
        {"name": "shares", "type": "int256"},
        {"name": "totalCost", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ]
}


@app.on_event("startup")
async def startup():
    asyncio.create_task(LEDGER.start_worker())
    asyncio.create_task(ORACLE_CACHE.loop())
    await asyncio.sleep(2)
    asyncio.create_task(lifecycle_manager())
    if RUN_BOTS and APP_MODE == "sim":
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
                        for bot in BOT_SWARM:
                            current_balance = VAULT.balances.get(bot.user_id, 0)
                            if current_balance < 10_000 * SCALING:
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
                            if btc_win and eth_win:
                                winner = Outcome.YY
                            elif btc_win and not eth_win:
                                winner = Outcome.YN
                            elif not btc_win and eth_win:
                                winner = Outcome.NY

                            state.is_settled = True
                            state.winner = winner
                            await VAULT.settle_market(mid, winner, state)
                            asyncio.create_task(create_next_market(duration=MARKET_DURATION_SECONDS))
        except Exception as e:
            print(f"Lifecycle Error: {e}")

        await asyncio.sleep(1)


@app.post("/markets/{market_id}/trade")
async def trade_endpoint(market_id: str, req: TradeRequest):
    if APP_MODE == "chain":
        raise HTTPException(400, "CHAIN mode active: use /markets/{market_id}/quote")

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
                state=state,
            )

    if not success:
        raise HTTPException(400, msg)

    prices = engine.get_prices(state.q, spec.lmsr_b)
    return {"status": "success", "prices": prices}


@app.post("/markets/{market_id}/quote", response_model=QuoteResponse)
async def quote_endpoint(market_id: str, req: QuoteRequest):
    if APP_MODE != "chain":
        raise HTTPException(400, "Quotes only available in CHAIN mode")
    if req.market_id != market_id:
        raise HTTPException(400, "Path market_id must match request body market_id")

    try:
        lock = get_lock(market_id)
        async with lock:
            spec, state = get_market(market_id)
            cost_before = engine.calculate_cost_shares(state.q, spec.lmsr_b)
            predicted_q = dict(state.q)
            predicted_q[req.outcome] += req.amount_shares
            cost_after = engine.calculate_cost_shares(predicted_q, spec.lmsr_b)
    except KeyError:
        raise HTTPException(404, "Market not found")

    delta = cost_after - cost_before
    if delta < 0:
        raise HTTPException(400, "Negative quote cost is not supported")

    total_cost_micros = int(round(delta * SCALING))
    deadline = int(time.time()) + QUOTE_TTL_SECONDS
    outcome_id = OUTCOME_TO_UINT8[req.outcome]

    message_data = {
        "user": req.user,
        "marketId": req.market_id,
        "outcome": outcome_id,
        "shares": int(req.amount_shares),
        "totalCost": total_cost_micros,
        "nonce": int(req.nonce),
        "deadline": deadline,
    }

    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except Exception as exc:
        raise HTTPException(500, f"eth-account dependency unavailable: {exc}")

    signable = encode_typed_data(DOMAIN_DATA, MESSAGE_TYPES, message_data)
    signed = Account.sign_message(signable, private_key=SIGNER_PRIVATE_KEY)

    return QuoteResponse(
        user=req.user,
        market_id=req.market_id,
        outcome=outcome_id,
        shares=req.amount_shares,
        total_cost_micros=total_cost_micros,
        nonce=req.nonce,
        deadline=deadline,
        signature="0x" + signed.signature.hex(),
    )


@app.post("/markets/{market_id}/simulate-bots")
async def simulate_bots_endpoint(market_id: str, req: SimulationRequest):
    if not ENABLE_SIMULATION_ENDPOINTS:
        raise HTTPException(403, "Simulation endpoint disabled in current mode")
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

    return {"market_id": market_id, "simulation": summary}


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
        "targets": spec.targets,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
