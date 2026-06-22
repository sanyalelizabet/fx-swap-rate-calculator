"""FX swap quoting ticket: cashflows on both legs in both currencies.

The user supplies one amount per leg (near required, far optional). Each
amount can be in BASE or QUOTE ccy independently. QUOTE amounts are
converted to a base notional using the rate that applies on that leg:
spot for the near leg, forward_client for the far leg (so a user-entered
far quote amount is preserved as the actual client cashflow).

If the far amount is omitted, the near base notional is reused for the
far leg (matched swap). If specified, the legs can have different base
notionals (uneven swap), but the FX rates applied on each leg remain the
market spot and the client forward respectively.

Conventions
-----------
* Forward rate: F_mid = S + P / pip_factor.
* The trade is an FX swap. "side" refers to the far-leg base-ccy direction:
      BUY  forward = SELL base spot + BUY  base forward
      SELL forward = BUY  base spot + SELL base forward
* Cashflow sign (from the client's point of view): + receive, - pay.
* Spread is an absolute rate add-on applied to the forward, always against
  the client:
      F_client = F_mid + spread_rate    (BUY  -> client pays more quote per base)
      F_client = F_mid - spread_rate    (SELL -> client receives less quote per base)
* days = (far_date - near_date), ACT/360.
* market_swap_rate = (forward_mid - spot) / spot * 360/days, the implied
  IR differential r_quote - r_base.
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
    forward_client: float        # F_mid +/- spread_rate (sign depends on side)
    spread_rate: float           # absolute rate add-on, always >= 0
    near_base_notional: float    # |near_leg.base_flow|
    far_base_notional: float     # |far_leg_mid.base_flow|
    is_uneven: bool              # True if near and far base notionals differ

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
    spread_rate: float,
    near_amount: float,
    near_amount_ccy: AmountCcy = "BASE",
    far_amount: float | None = None,
    far_amount_ccy: AmountCcy = "BASE",
) -> SwapTicket:
    """Build a swap ticket with one amount per leg (near is required; far is
    optional and defaults to the near base notional for a matched swap).

    Each amount can be in BASE or QUOTE ccy. QUOTE amounts are converted to a
    base notional using the rate that applies on that leg: spot for the near
    leg, forward_client for the far leg (so the user-entered far quote amount
    is preserved as the client's actual cashflow). The mid leg shows what the
    quote would have been at the fair forward for the same base notional.

    `spread_rate` is an absolute rate add-on (e.g. 0.001395 for EUR/CHF),
    applied to the forward against the client:
        F_client = F_mid + spread_rate   (side=BUY:  client pays more quote)
        F_client = F_mid - spread_rate   (side=SELL: client receives less quote)
    """
    if isinstance(pair, str):
        pair = get_pair(pair)
    side = side.upper()  # type: ignore[assignment]
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    if far_date <= near_date:
        raise ValueError("far_date must be strictly after near_date")
    if spot <= 0:
        raise ValueError("spot must be positive")
    if spread_rate < 0:
        raise ValueError("spread_rate must be non-negative")

    near_amount_ccy = near_amount_ccy.upper()  # type: ignore[assignment]
    far_amount_ccy = far_amount_ccy.upper()    # type: ignore[assignment]

    days = (far_date - near_date).days
    forward_mid = spot + forward_points / pair.pip_factor
    cf_sign = 1.0 if side == "BUY" else -1.0
    forward_client = forward_mid + cf_sign * spread_rate

    near_base_amt = _resolve_base_notional(near_amount, near_amount_ccy, spot)
    if far_amount is None:
        far_base_amt = near_base_amt
    else:
        far_base_amt = _resolve_base_notional(far_amount, far_amount_ccy, forward_client)
    is_uneven = (far_base_amt != near_base_amt)

    near_quote_amt = near_base_amt * spot
    far_quote_amt_mid = far_base_amt * forward_mid
    far_quote_amt_client = far_base_amt * forward_client

    near_leg, far_leg_mid = _signed_legs(
        side, near_base_amt, near_quote_amt, far_base_amt, far_quote_amt_mid,
        near_date, far_date,
    )
    _, far_leg_client = _signed_legs(
        side, near_base_amt, near_quote_amt, far_base_amt, far_quote_amt_client,
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
        spread_rate=spread_rate,
        near_base_notional=abs(near_leg.base_flow),
        far_base_notional=abs(far_leg_mid.base_flow),
        is_uneven=is_uneven,
        near_leg=near_leg,
        far_leg_mid=far_leg_mid,
        far_leg_client=far_leg_client,
        spread_cost_quote=spread_cost_quote,
        market_swap_rate=market_swap_rate,
    )
