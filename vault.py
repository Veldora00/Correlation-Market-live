
# vault.py
import time
from config import SCALING, MAX_OI_PER_OUTCOME, Q_FLOOR
from models import Outcome
import engine_lmsr as engine
# --- NEW IMPORT ---
from ledger import LEDGER 

class SovereignVault:
    def __init__(self):
        self.balances = {
            "MATH_GENIUS": 100_000 * SCALING,
            "RETAIL_1": 10_000 * SCALING
        }
        self.global_fees = 0
        # User Positions: {user_id: {market_id: {Outcome: shares}}}
        self.positions = {}

    def get_balance(self, user_id):
        return self.balances.get(user_id, 0)

    def execute_trade(self, user_id, market_id, outcome, amount, spec, state):
        if state.is_settled: return False, "Market Settled"

        q = state.q
        
        # 1. Validation
        predicted_q = q[outcome] + amount

        if amount < 0:
            user_pos = self.positions.get(user_id, {}).get(market_id, {}).get(outcome, 0)
            if user_pos < abs(amount): return False, "Insufficient shares"
            if predicted_q < Q_FLOOR: return False, "Q Floor hit"
        else:
            if q[outcome] + amount > MAX_OI_PER_OUTCOME: return False, "OI Cap hit"

        # 2. Math (Shares -> Micros)
        cost_before = engine.calculate_cost_shares(q, spec.lmsr_b)
        
        future_q = q.copy()
        future_q[outcome] += amount
        cost_after = engine.calculate_cost_shares(future_q, spec.lmsr_b)
        
        base_delta_shares = cost_after - cost_before
        base_micros = int(round(base_delta_shares * SCALING))

        # 3. Fees
        p_start = engine.get_prices(q, spec.lmsr_b)[outcome]
        p_end = engine.get_prices(future_q, spec.lmsr_b)[outcome]
        fee_rate = engine.get_dynamic_fee_rate(p_start, p_end)
        
        fee_micros = int(abs(base_micros) * fee_rate)
        fee_micros = min(fee_micros, abs(base_micros)) 

        # 4. Execution
        if amount > 0: # BUY
            total = base_micros + fee_micros
            if self.balances.get(user_id, 0) < total: return False, "Insufficient Funds"
            
            self.balances[user_id] -= total
            state.collateral_micros += base_micros
            self.global_fees += fee_micros
        else: # SELL
            refund_liability = abs(base_micros)
            payout_to_user = refund_liability - fee_micros
            
            # Insolvency Check
            if state.collateral_micros < refund_liability:
                return False, "INSOLVENCY RISK: Collateral too low"

            state.collateral_micros -= refund_liability
            self.balances[user_id] = self.balances.get(user_id, 0) + payout_to_user
            self.global_fees += fee_micros

        # 5. Commit
        state.q[outcome] += amount
        
        if user_id not in self.positions: self.positions[user_id] = {}
        if market_id not in self.positions[user_id]: 
            self.positions[user_id][market_id] = {o: 0 for o in Outcome}
            
        self.positions[user_id][market_id][outcome] += amount
        
        # --- NEW: RECORD TO LEDGER ---
        LEDGER.record({
            "ts": time.time(),
            "market_id": market_id,
            "user_id": user_id,
            "outcome": outcome,
            "amount_shares": amount,
            "price_micros": base_micros,
            "fee_micros": fee_micros,
            "type": "TRADE"
        })
        
        return True, "OK"

    async def settle_market(self, market_id: str, winner: Outcome, state):
        print(f"💰 Settling {market_id} for {winner}")
        
        # Iterate over copy of keys to be safe
        all_users = list(self.positions.keys())
        
        for user in all_users:
            if market_id in self.positions[user]:
                shares = self.positions[user][market_id].get(winner, 0)
                if shares > 0:
                    payout = shares * SCALING
                    self.balances[user] += payout
                    state.collateral_micros -= payout
                    
                    # LOG SETTLEMENT (Optional but good)
                    LEDGER.record({
                        "ts": time.time(),
                        "market_id": market_id,
                        "user_id": user,
                        "outcome": winner,
                        "amount_shares": shares,
                        "price_micros": payout,
                        "fee_micros": 0,
                        "type": "PAYOUT"
                    })
        
        if state.collateral_micros < 0:
            print(f"CRITICAL: Market {market_id} finished insolvent: {state.collateral_micros}")
        
        if state.collateral_micros > 0:
            self.global_fees += state.collateral_micros
            state.collateral_micros = 0

VAULT = SovereignVault()
