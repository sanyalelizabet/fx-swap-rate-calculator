"""FX swap math: forward rate, ACT/360 annualised swap rate, client spread.

Conventions
-----------
* Forward rate is built from spot and forward points using the pair's pip factor:
      F = S + P / pip_factor
* The annualised swap rate is the cost of carry expressed per annum, ACT/360:
      r = (F - S) / S * 360 / days
* Client spread (in percent) is applied to the far leg only, always against
  the client:
      BUY  (client buys the base ccy forward) -> F_client = F_mid * (1 + s/100)
      SELL (client sells the base ccy forward) -> F_client = F_mid * (1 - s/100)
* days = (far_date - near_date) in calendar days, ACT/360 day count.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from .pairs import FXPair, get_pair

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class SwapResult:
    pair: str
    side: Side
    near_date: date
    far_date: date
    days: int
    spot: float
    forward_points: float
    pip_factor: float
    spread_pct: float
    forward_mid: float
    rate_mid: float          # annualised, decimal (0.025 = 2.5%)
    forward_client: float
    rate_client: float       # annualised, decimal
    rate_difference: float   # rate_client - rate_mid, decimal
    notional_base: float           # trade amount in base ccy
    near_leg_quote: float          # near-leg counter-amount in quote ccy (notional * spot)
    far_leg_quote_mid: float       # far-leg counter-amount, mid (notional * F_mid)
    far_leg_quote_client: float    # far-leg counter-amount, client (notional * F_client)
    spread_pnl_quote: float        # client cost from spread, in quote ccy


def compute_swap(
    pair: str | FXPair,
    side: Side,
    near_date: date,
    far_date: date,
    spot: float,
    forward_points: float,
    spread_pct: float,
    notional_base: float = 0.0,
) -> SwapResult:
    if isinstance(pair, str):
        pair = get_pair(pair)
    side = side.upper()  # type: ignore[assignment]
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    if far_date <= near_date:
        raise ValueError("far_date must be strictly after near_date")
    if spot <= 0:
        raise ValueError("spot must be positive")
    if notional_base < 0:
        raise ValueError("notional_base must be non-negative")

    days = (far_date - near_date).days
    forward_mid = spot + forward_points / pair.pip_factor
    rate_mid = (forward_mid - spot) / spot * 360.0 / days

    sign = 1.0 if side == "BUY" else -1.0
    forward_client = forward_mid * (1.0 + sign * spread_pct / 100.0)
    rate_client = (forward_client - spot) / spot * 360.0 / days

    near_leg_quote = notional_base * spot
    far_leg_quote_mid = notional_base * forward_mid
    far_leg_quote_client = notional_base * forward_client
    spread_pnl_quote = far_leg_quote_client - far_leg_quote_mid

    return SwapResult(
        pair=pair.code,
        side=side,  # type: ignore[arg-type]
        near_date=near_date,
        far_date=far_date,
        days=days,
        spot=spot,
        forward_points=forward_points,
        pip_factor=pair.pip_factor,
        spread_pct=spread_pct,
        forward_mid=forward_mid,
        rate_mid=rate_mid,
        forward_client=forward_client,
        rate_client=rate_client,
        rate_difference=rate_client - rate_mid,
        notional_base=notional_base,
        near_leg_quote=near_leg_quote,
        far_leg_quote_mid=far_leg_quote_mid,
        far_leg_quote_client=far_leg_quote_client,
        spread_pnl_quote=spread_pnl_quote,
    )
