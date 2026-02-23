import asyncio
import time

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import engine_lmsr as engine
from config import (
    ALLOWED_ORIGINS,
    APP_MODE,
    CHAIN_ID,
    CONTRACT_ADDRESS,
    FREEZE_WINDOW,
    MARKET_DURATION_SECONDS,
    QUOTE_TTL_SECONDS,
    SCALING,
    SIGNER_PRIVATE_KEY,
)
from ledger import LEDGER
from market_registry import create_next_market, get_all_active_markets, get_lock, get_market
from models import Outcome, QuoteRequest, QuoteResponse, TradeRequest
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
        {"name": "marketId", "type": "bytes32"}, # Changed from string to bytes32
        {"name": "outcome", "type": "uint8"},
        {"name": "shares", "type": "uint256"},  # Changed from int256 to uint256
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

    # Guard: reject quotes for frozen/expired markets
    if time.time() > (spec.expiry_ts - FREEZE_WINDOW):
        raise HTTPException(400, "Market Frozen: quote rejected")

    # Guard: reject quotes when oracle is stale or unhealthy
    if ORACLE_CACHE.is_stale(max_age=5.0) or not ORACLE_CACHE.is_healthy:
        raise HTTPException(503, "Oracle Unstable/Stale: quote rejected")

    delta = cost_after - cost_before
    if delta < 0:
        raise HTTPException(400, "Negative quote cost is not supported")

    total_cost_micros = int(round(delta * SCALING))
    deadline = int(time.time()) + QUOTE_TTL_SECONDS
    outcome_id = OUTCOME_TO_UINT8[req.outcome]
    market_id_bytes = keccak(text=market_id)

    message_data = {
        "user": req.user,
        "marketId": market_id_bytes, # Use the bytes version here
        "outcome": outcome_id,
        "shares": int(req.amount_shares),
        "totalCost": total_cost_micros,
        "nonce": int(req.nonce),
        "deadline": deadline,
    }

    signable = encode_typed_data(DOMAIN_DATA, MESSAGE_TYPES, message_data)
    signed = Account.sign_message(signable, private_key=SIGNER_PRIVATE_KEY)

    return QuoteResponse(
        user=req.user,
        market_id="0x" + market_id_bytes.hex(),
        outcome=outcome_id,
        shares=req.amount_shares,
        total_cost_micros=total_cost_micros,
        nonce=req.nonce,
        deadline=deadline,
        signature="0x" + signed.signature.hex(),
    )


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

@app.get("/health")
async def health():
    return {
        "oracle_healthy": ORACLE_CACHE.is_healthy,
        "oracle_stale": ORACLE_CACHE.is_stale(max_age=5.0),
        "active_markets": len(get_all_active_markets()),
    }



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)