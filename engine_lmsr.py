
import math
from typing import Dict
from models import Outcome

def calculate_cost_shares(q: Dict[Outcome, int], b: float) -> float:
    # Convert INT shares to FLOAT for log/exp math
    vals = [float(val) / b for val in q.values()]
    m = max(vals)
    sum_exp = sum(math.exp(v - m) for v in vals)
    return b * (m + math.log(sum_exp))

def get_prices(q: Dict[Outcome, int], b: float) -> Dict[Outcome, float]:
    # Compute softmax over scaled inventory values (q_i / b).
    # Keep the scaled form explicit to avoid accidental double-scaling regressions.
    scaled = {k: float(v) / b for k, v in q.items()}
    m = max(scaled.values())
    denom = sum(math.exp(v - m) for v in scaled.values())
    return {k: math.exp(v - m) / denom for k, v in scaled.items()}

def get_dynamic_fee_rate(current_p: float, future_p: float) -> float:
    midpoint = (current_p + future_p) / 2
    dist = abs(midpoint - 0.5)
    
    MAX_FEE = 0.03   # 3%
    MIN_FEE = 0.005  # 0.5%
    
    # Quadratic curve
    x = dist / 0.5
    fee = MAX_FEE - (MAX_FEE - MIN_FEE) * (x**4)
    return max(fee, MIN_FEE)
