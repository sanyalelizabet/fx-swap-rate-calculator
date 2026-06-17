"""FX swap math: forward rate, ACT/360 annualised carry rate, client spread.

Conventions
-----------
* Forward rate from spot and forward points (in pips):
      F = S + P / pip_factor
* The annualised rate is expressed as the carry to the client's side of
  the swap (ACT/360), so that a SELL of a base ccy that trades at forward
  discount returns a positive number:
      market swap rate     m = (F - S) / S * 360 / days       (= r_quote - r_base)
      client carry (mid)   r_mid = side_sign * m
                                where side_sign = +1 for BUY, -1 for SELL.
  Rationale: a BUY-forward swap (sell base spot, buy base forward) leaves the
  client holding the quote ccy over the period, so their carry = r_quote - r_base.
  A SELL-forward swap leaves the client holding the base ccy, so their carry
  = r_base - r_quote = -m. Sign therefore flips with side.
* Client spread (in percent) is applied to the far leg only, always against
  the client. The far-leg quote-ccy amount moves against the client:
      BUY  -> F_client = F_mid * (1 + s/100)   (client pays more quote ccy)
      SELL -> F_client = F_mid * (1 - s/100)   (client receives less quote ccy)
  The spread cost as an annualised rate is always positive, and is subtracted
  from the carry regardless of side (a bank spread can never make the carry
  better for the client):
      spread_cost = |F_client - F_mid| / S * 360 / days
      r_client    = r_mid - spread_cost
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
    rate_mid: float          # client carry at mid, annualised, decimal (0.025 = 2.5%)
    market_swap_rate: float  # objective (F-S)/S * 360/days, sign-symmetric in side
    forward_client: float
    rate_client: float       # client carry after spread = rate_mid - spread_cost
    spread_cost: float       # always >= 0, annualised, decimal
    rate_difference: float   # rate_client - rate_mid = -spread_cost
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

    # Market swap rate = implied IR differential (r_quote - r_base), sign-symmetric.
    market_swap_rate = (forward_mid - spot) / spot * 360.0 / days

    # Client carry = market rate flipped by side so SELL of a base ccy trading
    # at forward discount returns a positive carry (client holds the higher-yield ccy).
    side_sign = 1.0 if side == "BUY" else -1.0
    rate_mid = side_sign * market_swap_rate

    # Cashflow far leg moves against the client (BUY pays more, SELL receives less).
    cf_sign = 1.0 if side == "BUY" else -1.0
    forward_client = forward_mid * (1.0 + cf_sign * spread_pct / 100.0)

    # Spread cost in rate terms is always positive and always reduces the client's carry.
    spread_cost = abs(forward_client - forward_mid) / spot * 360.0 / days
    rate_client = rate_mid - spread_cost

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
        market_swap_rate=market_swap_rate,
        forward_client=forward_client,
        rate_client=rate_client,
        spread_cost=spread_cost,
        rate_difference=rate_client - rate_mid,
        notional_base=notional_base,
        near_leg_quote=near_leg_quote,
        far_leg_quote_mid=far_leg_quote_mid,
        far_leg_quote_client=far_leg_quote_client,
        spread_pnl_quote=spread_pnl_quote,
    )
