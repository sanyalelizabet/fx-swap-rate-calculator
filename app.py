"""Streamlit quoting ticket for an FX swap.

Inputs: pair, side (BUY/SELL the base ccy forward), near + far dates, spot,
forward points (pips), client spread (%), amount + which ccy it's in.

Output: full cashflow ticket showing both legs in both currencies, with
the spread cost in quote ccy and the implied IR differential as a footer.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from fx_swap import compute_ticket, get_pair
from fx_swap.pairs import PAIRS

st.set_page_config(page_title="FX Swap Quoting Ticket", layout="centered")

st.title("FX Swap Quoting Ticket")
st.caption(
    "ACT/360. Matched-notional FX swap. Cashflows are signed from the client's "
    "perspective: positive = the client receives, negative = the client pays. "
    "Spread is applied to the far leg only and always disadvantages the client."
)


def fmt_money(x: float, dp: int = 2) -> str:
    """Swiss-style with apostrophe thousands and an explicit sign for non-zero."""
    if x == 0:
        return f"{0:,.{dp}f}".replace(",", "'")
    sign = "+" if x > 0 else "-"
    return f"{sign}{abs(x):,.{dp}f}".replace(",", "'")


def fmt_rate(x: float, dp: int = 6) -> str:
    return f"{x:,.{dp}f}".replace(",", "'")


def fmt_pct(x: float, dp: int = 4) -> str:
    return f"{x * 100:.{dp}f}%"


with st.form("ticket_inputs"):
    col1, col2 = st.columns(2)
    with col1:
        pair_code = st.selectbox(
            "Currency pair",
            options=sorted(PAIRS.keys()),
            index=sorted(PAIRS.keys()).index("EURUSD"),
        )
    with col2:
        side = st.radio(
            "Side (on the base ccy forward)",
            options=["BUY", "SELL"],
            horizontal=True,
            help="BUY = client buys the base ccy on the far date. Near leg is opposite.",
        )

    pair_obj_form = get_pair(pair_code)

    col3, col4 = st.columns(2)
    today = date.today()
    with col3:
        near_date = st.date_input("Near date", value=today + timedelta(days=2))
    with col4:
        far_date = st.date_input("Far date", value=today + timedelta(days=92))

    col5, col6, col7 = st.columns(3)
    with col5:
        spot = st.number_input("Spot rate", value=1.0850, format="%.6f", min_value=0.0)
    with col6:
        forward_points = st.number_input(
            "Forward points (pips)",
            value=50.0,
            format="%.4f",
            help="Sign matters. Positive = base ccy at premium forward.",
        )
    with col7:
        spread_pct = st.number_input(
            "Client spread (%)",
            value=0.10,
            min_value=0.0,
            format="%.4f",
            help="Applied to the far leg only, always against the client.",
        )

    col8, col9 = st.columns([2, 1])
    with col8:
        amount = st.number_input(
            "Trade amount",
            value=1_000_000.0,
            min_value=0.0,
            step=100_000.0,
            format="%.2f",
        )
    with col9:
        amount_ccy = st.selectbox(
            "Amount in",
            options=[pair_obj_form.base, pair_obj_form.quote],
            help="Which currency the amount is expressed in. If quote, the base notional is derived from spot.",
        )

    submitted = st.form_submit_button("Quote", width="stretch")

if submitted:
    amount_ccy_key = "BASE" if amount_ccy == pair_obj_form.base else "QUOTE"
    try:
        t = compute_ticket(
            pair=pair_code,
            side=side,
            near_date=near_date,
            far_date=far_date,
            spot=spot,
            forward_points=forward_points,
            spread_pct=spread_pct,
            amount=amount,
            amount_ccy=amount_ccy_key,
        )
    except (ValueError, KeyError) as e:
        st.error(str(e))
        st.stop()

    pair_obj = get_pair(pair_code)

    # ---- Header strip ----
    st.subheader("Trade summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pair", t.pair)
    c2.metric("Side (base ccy)", t.side)
    c3.metric("Days (ACT)", t.days)
    c4.metric(
        f"Base notional ({t.base_ccy})",
        fmt_money(t.base_notional, 2).lstrip("+"),
    )

    # ---- Rates strip ----
    st.subheader("Rates")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Spot", fmt_rate(t.spot, 6))
    c2.metric("Forward mid", fmt_rate(t.forward_mid, 6))
    c3.metric(
        "Forward client",
        fmt_rate(t.forward_client, 6),
        delta=fmt_rate(t.forward_client - t.forward_mid, 6),
        delta_color="inverse",
    )
    c4.metric("Forward points (mid)", fmt_rate(t.forward_points, 4))

    # ---- Cashflows table ----
    st.subheader("Cashflows (from the client's perspective)")
    rows = [
        {
            "Leg": "Near (spot)",
            "Value date": t.near_leg.value_date.isoformat(),
            "Rate": fmt_rate(t.near_leg.fx_rate, 6),
            f"{t.base_ccy}": fmt_money(t.near_leg.base_flow, 2),
            f"{t.quote_ccy}": fmt_money(t.near_leg.quote_flow, 2),
        },
        {
            "Leg": "Far (mid)",
            "Value date": t.far_leg_mid.value_date.isoformat(),
            "Rate": fmt_rate(t.far_leg_mid.fx_rate, 6),
            f"{t.base_ccy}": fmt_money(t.far_leg_mid.base_flow, 2),
            f"{t.quote_ccy}": fmt_money(t.far_leg_mid.quote_flow, 2),
        },
        {
            "Leg": "Far (client)",
            "Value date": t.far_leg_client.value_date.isoformat(),
            "Rate": fmt_rate(t.far_leg_client.fx_rate, 6),
            f"{t.base_ccy}": fmt_money(t.far_leg_client.base_flow, 2),
            f"{t.quote_ccy}": fmt_money(t.far_leg_client.quote_flow, 2),
        },
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch")

    st.caption(
        "Signs: **+ you receive**, **− you pay**. Near leg is the spot exchange. "
        "Far leg at mid is the fair forward. Far leg at client rate is what you "
        "actually quote — the difference is the spread."
    )

    # ---- Annualised rates (ACT/360, market convention) ----
    # Same formula at mid and at client forward; sign-symmetric in BUY/SELL.
    # Negative = base ccy at forward discount (higher base ccy rate).
    rate_mid = t.market_swap_rate
    rate_client = (t.forward_client - t.spot) / t.spot * 360.0 / t.days
    rate_spread = rate_client - rate_mid

    st.subheader("Annualised rate (ACT/360)")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Mid",
        fmt_pct(rate_mid),
        help="(F_mid − S) / S × 360/days. Market swap rate = implied IR differential.",
    )
    c2.metric(
        "Client",
        fmt_pct(rate_client),
        delta=fmt_pct(rate_spread),
        delta_color="inverse",
        help="(F_client − S) / S × 360/days. Delta vs mid = spread cost in rate terms.",
    )
    c3.metric(
        "Spread cost (rate)",
        fmt_pct(abs(rate_spread)),
        help="Absolute difference between client and mid annualised rates.",
    )

    # ---- Spread P&L in quote ccy ----
    st.subheader("Spread (quote ccy)")
    c1, c2 = st.columns(2)
    c1.metric(
        f"Bank revenue ({t.quote_ccy})",
        fmt_money(t.spread_cost_quote, 2).lstrip("+"),
        help="Difference between far-leg quote-ccy amount at client rate vs mid. "
             "This is what the client pays extra (or receives less) compared to mid.",
    )
    c2.metric(
        "Spread (% of far leg)",
        fmt_pct(t.spread_pct / 100, 4),
    )

    # ---- Footer: informational rate ----
    with st.expander("Implied IR differential and formulas"):
        st.markdown(
            f"""
**Pair**: {t.pair}  (base = {t.base_ccy}, quote = {t.quote_ccy}, pip factor = {int(t.pip_factor):,})

**Forward mid**: `S + P/pip = {fmt_rate(t.spot, 6)} + {fmt_rate(t.forward_points, 4)} / {int(t.pip_factor)} = {fmt_rate(t.forward_mid, 6)}`

**Forward client** (spread {('+ ' if t.side == 'BUY' else '− ')}{t.spread_pct:.4f}%): `F_mid × (1 {('+' if t.side == 'BUY' else '−')} s/100) = {fmt_rate(t.forward_client, 6)}`

**Implied IR differential** (market swap rate, sign-symmetric):
`(F_mid − S) / S × 360/days = {fmt_pct(t.market_swap_rate)}` — interpretable as `r_{t.quote_ccy.lower()} − r_{t.base_ccy.lower()}`.

**Base notional**: `{fmt_money(t.base_notional, 2).lstrip('+')} {t.base_ccy}` ({"entered in " + t.base_ccy if amount_ccy_key == "BASE" else f"derived from {amount} {t.quote_ccy} / spot {fmt_rate(t.spot, 6)}"}).
            """
        )
