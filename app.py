"""Streamlit UI for the FX swap annualised-rate calculator.

Inputs: pair, side (buy/sell the base ccy forward), near and far dates,
spot, forward points (in pips), client spread in percent.

Outputs: forward mid, annualised rate before spread, forward client,
annualised rate after spread, and the spread cost in rate terms.
"""

from datetime import date, timedelta

import streamlit as st

from fx_swap import compute_swap, get_pair
from fx_swap.pairs import PAIRS

st.set_page_config(page_title="FX Swap Rate Calculator", layout="centered")

st.title("FX Swap Rate Calculator")
st.caption("ACT/360 day count. Forward points use market-standard pip factor (100 for JPY-quoted pairs, 10'000 otherwise).")


def fmt_money(x: float, dp: int = 4) -> str:
    """Swiss-style number formatting: 1'234.5678."""
    s = f"{x:,.{dp}f}"
    return s.replace(",", "'")


def fmt_pct(x: float, dp: int = 4) -> str:
    return f"{x * 100:.{dp}f}%"


with st.form("swap_inputs"):
    col1, col2 = st.columns(2)
    with col1:
        pair_code = st.selectbox(
            "Currency pair",
            options=sorted(PAIRS.keys()),
            index=sorted(PAIRS.keys()).index("EURUSD"),
            help="Stored in market-standard direction. Base is the first ccy.",
        )
    with col2:
        side = st.radio(
            "Side (on the base ccy forward)",
            options=["BUY", "SELL"],
            horizontal=True,
            help="BUY = client buys the base ccy forward. Spread always against the client.",
        )

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
            help="In pips. Sign matters. 50 = +50 pips, -50 = base ccy at discount.",
        )
    with col7:
        spread_pct = st.number_input(
            "Client spread (%)",
            value=0.10,
            min_value=0.0,
            format="%.4f",
            help="Applied to the far leg only, always against the client.",
        )

    submitted = st.form_submit_button("Compute", width="stretch")

if submitted:
    try:
        result = compute_swap(
            pair=pair_code,
            side=side,
            near_date=near_date,
            far_date=far_date,
            spot=spot,
            forward_points=forward_points,
            spread_pct=spread_pct,
        )
    except (ValueError, KeyError) as e:
        st.error(str(e))
        st.stop()

    pair_obj = get_pair(pair_code)

    st.subheader("Trade")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pair", result.pair)
    c2.metric("Side (base ccy)", result.side)
    c3.metric("Days (ACT)", result.days)
    c4.metric("Pip factor", f"{int(result.pip_factor):,}".replace(",", "'"))

    st.subheader("Pre-spread (mid)")
    c1, c2 = st.columns(2)
    c1.metric("Forward mid", fmt_money(result.forward_mid, 6))
    c2.metric("Annualised rate (ACT/360)", fmt_pct(result.rate_mid))

    st.subheader("Post-spread (client)")
    c1, c2 = st.columns(2)
    c1.metric("Forward client", fmt_money(result.forward_client, 6))
    c2.metric(
        "Annualised rate (ACT/360)",
        fmt_pct(result.rate_client),
        delta=fmt_pct(result.rate_difference),
        delta_color="inverse",
    )

    with st.expander("Details and formulas"):
        st.markdown(
            f"""
- **Pair**: {pair_obj.code}  (base = {pair_obj.base}, quote = {pair_obj.quote})
- **Pip factor**: {int(result.pip_factor):,}
- **Days**: ({result.far_date} − {result.near_date}) = **{result.days}**
- **Forward mid**: `S + P/pip = {fmt_money(result.spot, 6)} + {fmt_money(result.forward_points, 4)} / {int(result.pip_factor)} = {fmt_money(result.forward_mid, 6)}`
- **Annualised rate (mid)**: `(F − S)/S × 360/days = {fmt_pct(result.rate_mid)}`
- **Client far leg**: `F × (1 {'+' if result.side == 'BUY' else '−'} s/100) = {fmt_money(result.forward_client, 6)}`
- **Annualised rate (client)**: `{fmt_pct(result.rate_client)}`
- **Spread cost in rate terms**: `{fmt_pct(result.rate_difference)}`
            """
        )
