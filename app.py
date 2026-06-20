"""Streamlit quoting ticket for an FX swap.

Inputs: pair, side (BUY/SELL the base ccy forward), near + far dates, spot,
forward points (pips), client spread (%), amount + which ccy it's in.

Output: full cashflow ticket showing both legs in both currencies, with
the spread cost in quote ccy and the implied IR differential as a footer.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from fx_swap import compute_ticket, get_pair, make_custom_pair
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


# Pair is outside the form so changing it triggers a rerun and refreshes the
# amount-ccy dropdown options (Streamlit forms suppress reruns until submit).
use_custom_pair = st.checkbox(
    "Custom pair (enter ccy codes manually)",
    value=False,
    help="For pairs not in the dropdown. Pip factor defaults to 100 for JPY-quoted, 10'000 otherwise.",
)

if use_custom_pair:
    c_base, c_quote = st.columns(2)
    with c_base:
        custom_base = st.text_input("Base ccy", value="EUR", max_chars=3).upper().strip()
    with c_quote:
        custom_quote = st.text_input("Quote ccy", value="USD", max_chars=3).upper().strip()
    try:
        pair_obj_form = make_custom_pair(custom_base, custom_quote)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    pair_code = pair_obj_form.code
else:
    pair_code = st.selectbox(
        "Currency pair",
        options=sorted(PAIRS.keys()),
        index=sorted(PAIRS.keys()).index("EURUSD"),
    )
    pair_obj_form = get_pair(pair_code)

with st.form("ticket_inputs"):
    near_side = st.radio(
        "Side (on the base ccy near leg)",
        options=["BUY", "SELL"],
        horizontal=True,
        help="What you do on the near (spot) leg. Far leg is automatically the opposite.",
    )
    # Calculator expects the far-leg side. Near leg is always opposite.
    side = "SELL" if near_side == "BUY" else "BUY"

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

    free_mode = st.checkbox(
        "Uneven swap (set all four cashflows manually)",
        value=False,
        help="Leave off for a standard matched-base swap. Tick to enter the four leg "
             "amounts as magnitudes; the implied rate per leg can differ from spot/forward.",
    )

    if not free_mode:
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
                help="If quote ccy, the base notional is derived from spot.",
            )
        free_amounts = None
    else:
        st.markdown(f"**Near leg ({pair_obj_form.base} / {pair_obj_form.quote})**")
        c_nb, c_nq = st.columns(2)
        with c_nb:
            near_base_amt = st.number_input(
                f"Near {pair_obj_form.base}",
                value=1_000_000.0, min_value=0.0, step=100_000.0, format="%.2f",
                key="free_near_base",
            )
        with c_nq:
            near_quote_amt = st.number_input(
                f"Near {pair_obj_form.quote}",
                value=1_000_000.0 * 1.085, min_value=0.0, step=100_000.0, format="%.2f",
                key="free_near_quote",
            )

        st.markdown(f"**Far leg ({pair_obj_form.base} / {pair_obj_form.quote})** — mid magnitudes; spread applies to the quote-ccy amount.")
        c_fb, c_fq = st.columns(2)
        with c_fb:
            far_base_amt = st.number_input(
                f"Far {pair_obj_form.base}",
                value=1_000_000.0, min_value=0.0, step=100_000.0, format="%.2f",
                key="free_far_base",
            )
        with c_fq:
            far_quote_amt = st.number_input(
                f"Far {pair_obj_form.quote} (mid)",
                value=1_000_000.0 * 1.09, min_value=0.0, step=100_000.0, format="%.2f",
                key="free_far_quote",
            )
        free_amounts = (near_base_amt, near_quote_amt, far_base_amt, far_quote_amt)
        amount = None
        amount_ccy = pair_obj_form.base  # not used but keeps the symbol defined

    submitted = st.form_submit_button("Quote", width="stretch")

if submitted:
    try:
        if free_amounts is not None:
            nb, nq, fb, fq = free_amounts
            t = compute_ticket(
                pair=pair_obj_form if use_custom_pair else pair_code,
                side=side,
                near_date=near_date,
                far_date=far_date,
                spot=spot,
                forward_points=forward_points,
                spread_pct=spread_pct,
                near_base_amount=nb,
                near_quote_amount=nq,
                far_base_amount=fb,
                far_quote_amount=fq,
            )
        else:
            amount_ccy_key = "BASE" if amount_ccy == pair_obj_form.base else "QUOTE"
            t = compute_ticket(
                pair=pair_obj_form if use_custom_pair else pair_code,
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

    # Use the pair object we already built (works for both registry and custom pairs).
    pair_obj = pair_obj_form

    # ---- Header strip ----
    st.subheader("Trade summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pair", t.pair)
    c2.metric(f"Near leg (base ccy)", near_side)
    c3.metric("Days (ACT)", t.days)
    if not t.is_free:
        c4.metric(
            f"Base notional ({t.base_ccy})",
            fmt_money(t.near_base_notional, 2).lstrip("+"),
        )
    else:
        c4.metric(
            f"Notional near / far ({t.base_ccy})",
            f"{fmt_money(t.near_base_notional, 2).lstrip('+')} / {fmt_money(t.far_base_notional, 2).lstrip('+')}",
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

    # ---- Carry rate to the client's side (ACT/360) ----
    # Sign: if the client BUYs base on near, they HOLD base -> carry = -market_rate.
    # If they SELL base on near, they hold quote -> carry = +market_rate.
    # Spread always reduces carry. Rates computed from the leg rates actually applied,
    # so it works in both matched and free-cashflow modes.
    carry_sign = +1.0 if near_side == "SELL" else -1.0
    rate_mid_carry = carry_sign * t.market_swap_rate
    spread_cost_rate = (
        abs(t.far_leg_client.fx_rate - t.far_leg_mid.fx_rate)
        / t.near_leg.fx_rate * 360.0 / t.days
    )
    rate_client_carry = rate_mid_carry - spread_cost_rate

    held_ccy = t.base_ccy if near_side == "BUY" else t.quote_ccy
    st.subheader(f"Carry rate (ACT/360) — you hold {held_ccy} over the period")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Mid",
        fmt_pct(rate_mid_carry),
        help=f"Sign-flipped IR differential, expressed from your side. "
             f"Positive = you earn carry, negative = you pay it. "
             f"= {'+' if carry_sign > 0 else '−'} (F_mid − S)/S × 360/days.",
    )
    c2.metric(
        "Client",
        fmt_pct(rate_client_carry),
        delta=fmt_pct(-spread_cost_rate),
        delta_color="inverse",
        help="Mid carry minus the spread cost (always reduces carry, regardless of side).",
    )
    c3.metric(
        "Spread cost (rate)",
        fmt_pct(spread_cost_rate),
        help="|F_client − F_mid| / S × 360/days. Always positive.",
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
        pip_factor_str = fmt_money(t.pip_factor, 0).lstrip("+")
        mode_label = "free cashflows" if t.is_free else "matched-base swap"
        st.markdown(
            f"""
**Pair**: {t.pair}  (base = {t.base_ccy}, quote = {t.quote_ccy}, pip factor = {pip_factor_str}, mode = {mode_label})

**Market forward mid**: `S + P/pip = {fmt_rate(t.spot, 6)} + {fmt_rate(t.forward_points, 4)} / {pip_factor_str} = {fmt_rate(t.forward_mid, 6)}`

**Market forward client** (spread {('+ ' if t.side == 'BUY' else '− ')}{t.spread_pct:.4f}%): `F_mid × (1 {('+' if t.side == 'BUY' else '−')} s/100) = {fmt_rate(t.forward_client, 6)}`

**Implied rates per leg** (from the cashflows actually used):
- Near: `{fmt_rate(t.near_leg.fx_rate, 6)}` {"(= spot)" if not t.is_free else "(= near_quote / near_base)"}
- Far mid: `{fmt_rate(t.far_leg_mid.fx_rate, 6)}` {"(= forward mid)" if not t.is_free else "(= far_quote / far_base)"}
- Far client: `{fmt_rate(t.far_leg_client.fx_rate, 6)}` {"(= forward client)" if not t.is_free else "(= far_quote × spread_mult / far_base)"}

**IR differential** (market swap rate from implied rates, sign-symmetric):
`(far_rate_mid − near_rate) / near_rate × 360/days = {fmt_pct(t.market_swap_rate)}` — interpretable as `r_{t.quote_ccy.lower()} − r_{t.base_ccy.lower()}`. This is a market property, not side-dependent.

**Carry to your side** (shown above) = `±` IR differential, sign chosen so positive means you earn carry on the ccy you hold over the period. Spread cost is always subtracted.

**Near base notional**: `{fmt_money(t.near_base_notional, 2).lstrip('+')} {t.base_ccy}`
**Far  base notional**: `{fmt_money(t.far_base_notional, 2).lstrip('+')} {t.base_ccy}` ({mode_label})
            """
        )
