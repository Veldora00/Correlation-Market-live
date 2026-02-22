# Moving from Simulation to Live Environment

This codebase was originally simulation-first. Use this checklist to harden it for production.

## 1) Disable simulation behavior

Set these environment variables:

- `APP_MODE=chain`
- `ENABLE_BOT_TRADING=0`
- `ENABLE_SIMULATION_ENDPOINTS=0`

Why:

- Prevents background bot swarm from trading with unlimited top-ups.
- Blocks `/markets/{market_id}/simulate-bots` in live mode.

## 2) Replace permissive CORS

Set a strict allowlist:

- `ALLOWED_ORIGINS=https://your-frontend.example.com`

Do **not** leave `*` for production unless this API is intentionally public and unauthenticated.

## 3) Use production market durations

Set:

- `MARKET_DURATION_SECONDS` to your desired market cadence (e.g. `3600` or `86400`)

## 4) Pin and monitor oracle sources

Set:

- `BTC_ORACLE_URL`
- `ETH_ORACLE_URL`
- `ORACLE_TIMEOUT_SECONDS`

Use a monitored/redundant data source and alert on stale oracle updates.

## 5) Recommended code-level deletions/refactors (next pass)

Before real-money deployment, remove or redesign:

- Infinite bot funding logic in `bot_manager`.
- Any endpoints intended only for simulation workflows.
- Global in-memory state for balances/positions if you need fault tolerance.

## 6) Non-negotiable live requirements (not yet in this repo)

- Authentication + authorization for trade endpoints.
- Persistent database for users, balances, trades, and market states.
- Idempotency keys and replay protection on order submission.
- Rate limiting + abuse protection.
- Full audit logging and reconciliation jobs.
- Secrets management and key rotation.
- Observability: metrics, structured logs, tracing, alerting.

## Example env file

```bash
APP_MODE=chain
RUN_BOTS=0
ENABLE_SIMULATION_ENDPOINTS=0
ALLOWED_ORIGINS=https://your-frontend.example.com
MARKET_DURATION_SECONDS=3600
BTC_ORACLE_URL=https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
ETH_ORACLE_URL=https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT
ORACLE_TIMEOUT_SECONDS=3
```


## 7) CHAIN mode signer requirements

In `APP_MODE=chain`, backend signs quotes for the contract. Set:

- `SIGNER_PRIVATE_KEY`
- `CHAIN_ID`
- `CONTRACT_ADDRESS`
- `QUOTE_TTL_SECONDS`

The app now fails fast on startup if signer key or contract address are missing in CHAIN mode.
