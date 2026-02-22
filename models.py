from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field


class Outcome(str, Enum):
    YY = "YY"
    YN = "YN"
    NY = "NY"
    NN = "NN"


class MarketState(BaseModel):
    # q is stored as INTEGERS (atomic shares) to prevent float drift
    q: Dict[Outcome, int] = Field(default_factory=lambda: {
        Outcome.YY: 0,
        Outcome.YN: 0,
        Outcome.NY: 0,
        Outcome.NN: 0,
    })
    # This is the ONLY pot of money for the market
    collateral_micros: int = 0
    winner: Optional[Outcome] = None
    is_settled: bool = False


class MarketSpec(BaseModel):
    market_id: str
    targets: Dict[str, float]
    expiry_ts: float
    lmsr_b: float


class TradeRequest(BaseModel):
    market_id: str
    user_id: str
    outcome: Outcome
    amount_shares: int = Field(ge=-2_000, le=2_000)


class QuoteRequest(BaseModel):
    user: str
    market_id: str
    outcome: Outcome
    amount_shares: int = Field(ge=1, le=2_000)
    nonce: int = Field(ge=0)


class QuoteResponse(BaseModel):
    user: str
    market_id: str
    outcome: int
    shares: int
    total_cost_micros: int
    nonce: int
    deadline: int
    signature: str


