"""FX swap quoting ticket: cashflows on both legs in both currencies.

Modes
-----
**Matched** (default): the user supplies a single amount + currency. The
base notional is derived (directly if BASE, or via spot if QUOTE) and
re-used for both legs. The rates applied on each leg are the market spot
and the market forward (= spot + points / pip_factor).

**Free cashflows**: the user supplies all four leg-amount magnitudes
(near_base, near_quote, far_base, far_quote). Signs are applied based on
the side. Implied rates per leg are derived from the ratios; they need
not match spot / forward. Useful for tailored / off-market deals.

Conventions
-----------
* Forward rate from spot and forward points:
      F = S + P / pip_factor      (matched mode only; in free mode rates are implied)
* The trade is an FX swap. "side" refers to the far-leg base-ccy direction:
      BUY  forward = SELL base spot + BUY  base forward
      SELL forward = BUY  base spot + SELL base forward
* Cashflow sign convention (from the client's point of view):
      +  -> client receives
      -  -> client pays
* Spread is applied to the far-leg quote amount, always against the client:
      BUY  -> far quote magnitude * (1 + s/100)   (client pays more)
      SELL -> far quote magnitude * (1 - s/100)   (client receives less)
  In matched mode this is equivalent to F_client = F_mid * (1 +/- s/100).
* days = (far_date - near_date) in calendar days, ACT/360.
* The annualised swap rate (far_rate_mid - near_rate) / near_rate * 360/days
  reduces to (F_mid - S)/S * 360/days in matched mode. In free mode it
  reflects the IR differential implied by the actual cashflows.
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
    fx_rate: float        # rate applied on this leg (= |quote_flow / base_flow|)
    base_flow: float      # signed: + receive, - pay
    quote_flow: float     # signed: + receive, - pay


@dataclass(frozen=True)
class SwapTicket:
    pair: str
    base_ccy: str
    quote_ccy: str
    side: Side
    days: int
    spot: float                  # market reference
    forward_points: float
    pip_factor: float
    forward_mid: float           # market reference: S + P/pip
    forward_client: float        # market reference: F_mid * (1 +/- s/100)
    spread_pct: float
    near_base_notional: float    # |near_leg.base_flow|
    far_base_notional: float     # |far_leg_mid.base_flow|
    is_free: bool                # True if free-cashflow mode

    near_leg: Leg
    far_leg_mid: Leg
    far_leg_client: Leg

    spread_cost_quote: float     # bank revenue in quote ccy, positive
    market_swap_rate: float      # (far_rate_mid - near_rate)/near_rate * 360/days


def _resolve_base_notional(amount: float, amount_ccy: AmountCcy, leg_rate: float) -> float:
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if amount_ccy == "BASE":
        return amount
    if amount_ccy == "QUOTE":
        return amount / leg_rate
    raise ValueError(f"amount_ccy must be BASE or QUOTE, got {amount_ccy!r}")


def _signed_legs(
    side: Side,
    near_base_amt: float, near_quote_amt: float,
    far_base_amt: float, far_quote_amt: float,
    near_date: date, far_date: date,
) -> tuple[Leg, Leg]:
    """Apply signs to four positive magnitudes based on the swap side."""
    if side == "BUY":
        near = Leg(near_date, near_quote_amt / near_base_amt if near_base_amt else 0.0,
                   -near_base_amt, +near_quote_amt)
        far = Leg(far_date, far_quote_amt / far_base_amt if far_base_amt else 0.0,
                  +far_base_amt, -far_quote_amt)
    else:  # SELL
        near = Leg(near_date, near_quote_amt / near_base_amt if near_base_amt else 0.0,
                   +near_base_amt, -near_quote_amt)
        far = Leg(far_date, far_quote_amt / far_base_amt if far_base_amt else 0.0,
                  -far_base_amt, +far_quote_amt)
    return near, far


def compute_ticket(
    pair: str | FXPair,
    side: Side,
    near_date: date,
    far_date: date,
    spot: float,
    forward_points: float,
    spread_pct: float,
    # Matched mode:
    amount: float | None = None,
    amount_ccy: AmountCcy = "BASE",
    # Free-cashflow mode (all four required together):
    near_base_amount: float | None = None,
    near_quote_amount: float | None = None,
    far_base_amount: float | None = None,
    far_quote_amount: float | None = None,
) -> SwapTicket:
    if isinstance(pair, str):
        pair = get_pair(pair)
    side = side.upper()  # type: ignore[assignment]
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    if far_date <= near_date:
        raise ValueError("far_date must be strictly after near_date")
    if spot <= 0:
        raise ValueError("spot must be positive")

    free_args = (near_base_amount, near_quote_amount, far_base_amount, far_quote_amount)
    is_free = any(a is not None for a in free_args)
    if is_free:
        if any(a is None for a in free_args):
            raise ValueError(
                "Free-cashflow mode requires all four amounts: "
                "near_base_amount, near_quote_amount, far_base_amount, far_quote_amount"
            )
        if amount is not None:
            raise ValueError("Cannot mix matched 'amount' with free-cashflow amounts")
        for a, name in zip(free_args, ("near_base", "near_quote", "far_base", "far_quote")):
            if a <= 0:
                raise ValueError(f"{name}_amount must be strictly positive in free mode")
    else:
        if amount is None:
            raise ValueError("Provide either 'amount' (matched) or the four free-mode amounts")
        amount_ccy = amount_ccy.upper()  # type: ignore[assignment]

    days = (far_date - near_date).days
    forward_mid = spot + forward_points / pair.pip_factor
    cf_sign = 1.0 if side == "BUY" else -1.0
    spread_mult = 1.0 + cf_sign * spread_pct / 100.0
    forward_client = forward_mid * spread_mult

    if is_free:
        near_base_amt = near_base_amount  # type: ignore[assignment]
        near_quote_amt = near_quote_amount  # type: ignore[assignment]
        far_base_amt_mid = far_base_amount  # type: ignore[assignment]
        far_quote_amt_mid = far_quote_amount  # type: ignore[assignment]
    else:
        near_base_amt = _resolve_base_notional(amount, amount_ccy, spot)  # type: ignore[arg-type]
        near_quote_amt = near_base_amt * spot
        far_base_amt_mid = near_base_amt
        far_quote_amt_mid = near_base_amt * forward_mid

    # Spread modifies the FAR leg's quote amount; base is unchanged.
    far_quote_amt_client = far_quote_amt_mid * spread_mult

    near_leg, far_leg_mid = _signed_legs(
        side, near_base_amt, near_quote_amt, far_base_amt_mid, far_quote_amt_mid,
        near_date, far_date,
    )
    _, far_leg_client = _signed_legs(
        side, near_base_amt, near_quote_amt, far_base_amt_mid, far_quote_amt_client,
        near_date, far_date,
    )

    spread_cost_quote = abs(far_leg_client.quote_flow - far_leg_mid.quote_flow)

    # Swap rate from rates actually applied on the legs (works in both modes).
    market_swap_rate = (far_leg_mid.fx_rate - near_leg.fx_rate) / near_leg.fx_rate * 360.0 / days

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
        near_base_notional=abs(near_leg.base_flow),
        far_base_notional=abs(far_leg_mid.base_flow),
        is_free=is_free,
        near_leg=near_leg,
        far_leg_mid=far_leg_mid,
        far_leg_client=far_leg_client,
        spread_cost_quote=spread_cost_quote,
        market_swap_rate=market_swap_rate,
    )
