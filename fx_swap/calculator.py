"""FX swap quoting ticket: cashflows on both legs in both currencies.

Conventions
-----------
* Forward rate from spot and forward points (in pips):
      F = S + P / pip_factor
* The trade is a matched-notional FX swap: same base-currency notional on
  both legs, exchanged in opposite directions. The "side" refers to the
  far leg's base-currency direction:
      BUY  forward = SELL base spot + BUY  base forward (sell/buy swap)
      SELL forward = BUY  base spot + SELL base forward (buy/sell swap)
* Cashflow sign convention (from the client's point of view):
      +  -> client receives
      -  -> client pays
* Amount input can be in either ccy. If in quote ccy, the base notional is
  derived from spot so the near-leg quote-ccy amount matches the input.
* Spread is applied to the far leg only, always against the client:
      BUY  -> F_client = F_mid * (1 + s/100)   (client pays more quote ccy)
      SELL -> F_client = F_mid * (1 - s/100)   (client receives less quote ccy)
* days = (far_date - near_date) in calendar days, ACT/360.
* The annualised swap rate (F-S)/S * 360/days is the implied IR differential
  r_quote - r_base. Reported as informational footer only.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from .pairs import FXPair, get_pair

Side = Literal["BUY", "SELL"]
AmountCcy = Literal["BASE", "QUOTE"]


@dataclass(frozen=True)
class Leg:
    """One leg of the swap, from the client's perspective."""
    value_date: date
    fx_rate: float        # rate applied to this leg
    base_flow: float      # signed: + receive, - pay
    quote_flow: float     # signed: + receive, - pay


@dataclass(frozen=True)
class SwapTicket:
    pair: str
    base_ccy: str
    quote_ccy: str
    side: Side
    days: int
    spot: float
    forward_points: float
    pip_factor: float
    forward_mid: float
    forward_client: float
    spread_pct: float
    base_notional: float

    near_leg: Leg            # same regardless of spread (spot leg)
    far_leg_mid: Leg         # at the mid forward
    far_leg_client: Leg      # at the client forward

    spread_cost_quote: float # bank revenue = -(client's cost), positive number
    market_swap_rate: float  # (F_mid - S)/S * 360/days, informational


def _resolve_base_notional(amount: float, amount_ccy: AmountCcy, spot: float) -> float:
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if amount_ccy == "BASE":
        return amount
    if amount_ccy == "QUOTE":
        return amount / spot
    raise ValueError(f"amount_ccy must be BASE or QUOTE, got {amount_ccy!r}")


def _build_legs(
    side: Side,
    base_notional: float,
    spot: float,
    forward: float,
    near_date: date,
    far_date: date,
) -> tuple[Leg, Leg]:
    """Return (near_leg, far_leg) with signed cashflows.

    BUY forward = SELL spot + BUY forward
        Near: -base, +base*spot (sell base, receive quote at spot)
        Far : +base, -base*F   (buy base, pay quote at forward)

    SELL forward = BUY spot + SELL forward
        Near: +base, -base*spot
        Far : -base, +base*F
    """
    if side == "BUY":
        near_base, near_quote = -base_notional, +base_notional * spot
        far_base, far_quote = +base_notional, -base_notional * forward
    else:  # SELL
        near_base, near_quote = +base_notional, -base_notional * spot
        far_base, far_quote = -base_notional, +base_notional * forward
    near = Leg(value_date=near_date, fx_rate=spot, base_flow=near_base, quote_flow=near_quote)
    far = Leg(value_date=far_date, fx_rate=forward, base_flow=far_base, quote_flow=far_quote)
    return near, far


def compute_ticket(
    pair: str | FXPair,
    side: Side,
    near_date: date,
    far_date: date,
    spot: float,
    forward_points: float,
    spread_pct: float,
    amount: float,
    amount_ccy: AmountCcy = "BASE",
) -> SwapTicket:
    if isinstance(pair, str):
        pair = get_pair(pair)
    side = side.upper()  # type: ignore[assignment]
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    amount_ccy = amount_ccy.upper()  # type: ignore[assignment]
    if far_date <= near_date:
        raise ValueError("far_date must be strictly after near_date")
    if spot <= 0:
        raise ValueError("spot must be positive")

    days = (far_date - near_date).days
    forward_mid = spot + forward_points / pair.pip_factor

    cf_sign = 1.0 if side == "BUY" else -1.0
    forward_client = forward_mid * (1.0 + cf_sign * spread_pct / 100.0)

    base_notional = _resolve_base_notional(amount, amount_ccy, spot)

    near_leg, far_leg_mid = _build_legs(side, base_notional, spot, forward_mid, near_date, far_date)
    _, far_leg_client = _build_legs(side, base_notional, spot, forward_client, near_date, far_date)

    # Spread cost = how much more quote ccy the client pays (or less receives) vs mid.
    # The signed difference of far-leg quote_flow points away from the client when worse.
    # Absolute value gives the bank's revenue in quote ccy.
    spread_cost_quote = abs(far_leg_client.quote_flow - far_leg_mid.quote_flow)

    market_swap_rate = (forward_mid - spot) / spot * 360.0 / days

    return SwapTicket(
        pair=pair.code,
        base_ccy=pair.base,
        quote_ccy=pair.quote,
        side=side,  # type: ignore[arg-type]
        days=days,
        spot=spot,
        forward_points=forward_points,
        pip_factor=pair.pip_factor,
        forward_mid=forward_mid,
        forward_client=forward_client,
        spread_pct=spread_pct,
        base_notional=base_notional,
        near_leg=near_leg,
        far_leg_mid=far_leg_mid,
        far_leg_client=far_leg_client,
        spread_cost_quote=spread_cost_quote,
        market_swap_rate=market_swap_rate,
    )
