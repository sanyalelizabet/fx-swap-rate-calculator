"""Streamlit quoting ticket for an FX swap.

Inputs: pair, side (BUY/SELL the base ccy forward), near + far dates, spot,
forward points (pips), client spread (%), amount + which ccy it's in.

Output: full cashflow ticket showing both legs in both currencies, with
the spread cost in quote ccy and the implied IR differential as a footer.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from fx_swap import compute_ticket, make_custom_pair

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




def render_cheat_sheet() -> None:
    st.markdown(
        """
### Forward points and interest rates

| Forward points | Forward vs spot | Means |
|---|---|---|
| **Positive** (F > S) | base ccy at **premium** | base ccy interest rate is **lower** than quote ccy |
| **Negative** (F < S) | base ccy at **discount** | base ccy interest rate is **higher** than quote ccy |

The forward is just the no-arbitrage price built from `F = S × (1 + r_quote × t/360) / (1 + r_base × t/360)`. If quote yields more, F has to be higher to compensate.

---

### Bank spread direction (always against the client)

Spread is taken on the **far leg only**. Direction depends on what the client does on the near leg:

| Client on near leg | Client on far leg | To take spread, bank shifts F | Forward points |
|---|---|---|---|
| **SELLS base** | buys base back | quote a **higher** far rate | **GO UP** |
| **BUYS base** | sells base back | quote a **lower** far rate | **GO DOWN** |

Mnemonic: the bank always quotes a far rate that is **worse** for whatever direction the client trades on the far leg.

---

### Who earns carry over the swap

Whichever ccy the client **bought on the near leg** is the one they hold until the far date — and that is the rate they earn.

| Client near | Holds over period | Carry to client |
|---|---|---|
| BUYS base | base | `r_base − r_quote` |
| SELLS base | quote | `r_quote − r_base` |

Spread always **reduces** this carry, regardless of side. The bank never gives carry away.

---

### Quick sanity checks while quoting

- If your **forward points are positive** and the client is **buying base on near**, they hold the lower-yielding ccy → negative carry → they pay carry. Add spread → they pay even more.
- If your **forward points are negative** and the client is **selling base on near**, they hold the higher-yielding ccy → positive carry → they earn. Spread eats into that.
- If carry-to-client and the forward-points sign tell different stories about the side, check the side radio — easy to fool yourself.
        """
    )


def render_quote_tab() -> None:
    # Pair lives outside the form so changing the ccys triggers a rerun and the
    # amount-ccy dropdowns pick up the new base/quote (Streamlit forms suppress
    # reruns until submit).
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

    # Side lives outside the form so that changing it triggers a rerun and the
    # side-dependent help text on Forward points refreshes (Streamlit forms
    # suppress reruns until submit).
    near_side = st.radio(
        "Side (on the base ccy near leg)",
        options=["BUY", "SELL"],
        horizontal=True,
        help="What you do on the near (spot) leg. Far leg is automatically the opposite.",
    )
    # Calculator expects the far-leg side. Near leg is always opposite.
    side = "SELL" if near_side == "BUY" else "BUY"

    with st.form("ticket_inputs"):

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
            # Direction of pip changes on the client's annualised carry depends
            # on the near-leg side. Carry = ± (F - S)/S × 360/days, sign chosen
            # so the ccy the client HOLDS over the period yields positive carry.
            # near BUY base  -> holds base  -> carry sign is negative on (F-S),
            #                  so MORE pips (higher F) -> LOWER carry to client.
            # near SELL base -> holds quote -> carry sign is positive on (F-S),
            #                  so MORE pips (higher F) -> HIGHER carry to client.
            if near_side == "BUY":
                pip_tip = (
                    "**Tip (you BUY base on near):** more pips → **lower** carry "
                    "rate to the client (you pay more in CHF/quote-ccy carry). "
                    "Fewer pips → higher carry."
                )
            else:
                pip_tip = (
                    "**Tip (you SELL base on near):** more pips → **higher** carry "
                    "rate to the client (you earn more). "
                    "Fewer pips → lower carry."
                )
            forward_points = st.number_input(
                "Forward points (pips)",
                value=50.0,
                format="%.4f",
                help=(
                    "Sign matters. Positive = base ccy at premium forward.\n\n"
                    + pip_tip
                ),
            )
        with col7:
            spread_pct = st.number_input(
                "Client spread (%)",
                value=0.10,
                min_value=0.0,
                format="%.4f",
                help="Applied to the far leg only, always against the client.",
            )

        st.markdown("**Amounts** — one per leg, each in BASE or QUOTE ccy.")
        c_na, c_nc = st.columns([2, 1])
        with c_na:
            near_amount = st.number_input(
                "Near-leg amount",
                value=1_000_000.0, min_value=0.0, step=100_000.0, format="%.2f",
                key="near_amount",
            )
        with c_nc:
            near_amount_ccy = st.selectbox(
                "Near in",
                options=[pair_obj_form.base, pair_obj_form.quote],
                key="near_amount_ccy",
                help="If QUOTE, the base notional is derived from spot.",
            )

        c_fa, c_fc = st.columns([2, 1])
        with c_fa:
            far_amount = st.number_input(
                "Far-leg amount",
                value=1_000_000.0, min_value=0.0, step=100_000.0, format="%.2f",
                key="far_amount",
            )
        with c_fc:
            far_amount_ccy = st.selectbox(
                "Far in",
                options=[pair_obj_form.base, pair_obj_form.quote],
                key="far_amount_ccy",
                help="If QUOTE, the base notional is derived from the forward mid.",
            )

        submitted = st.form_submit_button("Quote", width="stretch")

    if submitted:
        near_ccy_key = "BASE" if near_amount_ccy == pair_obj_form.base else "QUOTE"
        far_ccy_key = "BASE" if far_amount_ccy == pair_obj_form.base else "QUOTE"
        try:
            t = compute_ticket(
                pair=pair_obj_form,
                side=side,
                near_date=near_date,
                far_date=far_date,
                spot=spot,
                forward_points=forward_points,
                spread_pct=spread_pct,
                near_amount=near_amount,
                near_amount_ccy=near_ccy_key,
                far_amount=far_amount,
                far_amount_ccy=far_ccy_key,
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
        if not t.is_uneven:
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
        c1, c2, c3 = st.columns(3)
        c1.metric("Spot", fmt_rate(t.spot, 6))
        c2.metric("Forward mid", fmt_rate(t.forward_mid, 6))
        c3.metric(
            "Forward client",
            fmt_rate(t.forward_client, 6),
            delta=fmt_rate(t.forward_client - t.forward_mid, 6),
            delta_color="inverse",
        )

        # Forward points: mid (user input echo) vs client (with spread applied).
        fwd_points_client = (t.forward_client - t.spot) * t.pip_factor
        fwd_points_spread = fwd_points_client - t.forward_points
        c4, c5 = st.columns(2)
        c4.metric("Forward points (mid)", fmt_rate(t.forward_points, 4))
        c5.metric(
            "Forward points (client)",
            fmt_rate(fwd_points_client, 4),
            delta=fmt_rate(fwd_points_spread, 4),
            delta_color="inverse",
            help="Forward points with the client spread baked in: "
                 "(F_client − S) × pip_factor. Delta vs mid = the spread in pips.",
        )

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

        # ---- Client P&L on the swap (round-trip) ----
        # Sum of both legs per ccy. For a matched swap the base ccy nets to
        # zero by construction and the P&L lives in the quote ccy; for an
        # uneven swap both can be non-zero. Spread is always on the quote
        # far leg, so the base-ccy delta vs mid is always zero.
        net_base_mid = t.near_leg.base_flow + t.far_leg_mid.base_flow
        net_quote_mid = t.near_leg.quote_flow + t.far_leg_mid.quote_flow
        net_base_client = t.near_leg.base_flow + t.far_leg_client.base_flow
        net_quote_client = t.near_leg.quote_flow + t.far_leg_client.quote_flow

        near_quote_notional = abs(t.near_leg.quote_flow)
        ann_mid = (net_quote_mid / near_quote_notional * 360.0 / t.days
                   if near_quote_notional else 0.0)
        ann_client = (net_quote_client / near_quote_notional * 360.0 / t.days
                      if near_quote_notional else 0.0)

        st.subheader("Client P&L on the swap (round-trip)")
        st.caption(
            f"Sum of both legs per ccy. Ignores anything the client does with "
            f"the {t.base_ccy} between the legs — pure FX round-trip."
        )
        c1, c2 = st.columns(2)
        c1.metric(
            f"Net {t.quote_ccy} at mid",
            fmt_money(net_quote_mid, 2),
            help=f"Far {t.quote_ccy} + Near {t.quote_ccy} at the mid forward. "
                 f"Fair-value round-trip P&L.",
        )
        c1.metric(
            f"Net {t.quote_ccy} at client rate",
            fmt_money(net_quote_client, 2),
            delta=fmt_money(net_quote_client - net_quote_mid, 2),
            delta_color="inverse",
            help=f"What the client actually pockets in {t.quote_ccy}. "
                 f"Delta vs mid = spread cost (= bank revenue with opposite sign).",
        )
        c2.metric(
            f"Annualised on near {t.quote_ccy} notional (mid)",
            fmt_pct(ann_mid),
            help=f"Net {t.quote_ccy} / near {t.quote_ccy} notional × 360/days.",
        )
        c2.metric(
            f"Annualised on near {t.quote_ccy} notional (client)",
            fmt_pct(ann_client),
            delta=fmt_pct(ann_client - ann_mid),
            delta_color="inverse",
        )

        if abs(net_base_mid) > 1e-9:
            st.caption(
                f"Uneven swap — non-zero net in {t.base_ccy}: "
                f"`{fmt_money(net_base_mid, 2)}` (same at mid and client; "
                f"spread is in {t.quote_ccy} only)."
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
            mode_label = "uneven swap" if t.is_uneven else "matched swap"
            st.markdown(
                f"""
    **Pair**: {t.pair}  (base = {t.base_ccy}, quote = {t.quote_ccy}, pip factor = {pip_factor_str}, mode = {mode_label})

    **Market forward mid**: `S + P/pip = {fmt_rate(t.spot, 6)} + {fmt_rate(t.forward_points, 4)} / {pip_factor_str} = {fmt_rate(t.forward_mid, 6)}`

    **Market forward client** (spread {('+ ' if t.side == 'BUY' else '− ')}{t.spread_pct:.4f}%): `F_mid × (1 {('+' if t.side == 'BUY' else '−')} s/100) = {fmt_rate(t.forward_client, 6)}`

    **Rates applied per leg**:
    - Near: `{fmt_rate(t.near_leg.fx_rate, 6)}` (= spot)
    - Far mid: `{fmt_rate(t.far_leg_mid.fx_rate, 6)}` (= forward mid)
    - Far client: `{fmt_rate(t.far_leg_client.fx_rate, 6)}` (= forward client)

    **IR differential** (market swap rate, sign-symmetric):
    `(F_mid − S) / S × 360/days = {fmt_pct(t.market_swap_rate)}` — interpretable as `r_{t.quote_ccy.lower()} − r_{t.base_ccy.lower()}`. This is a market property, not side-dependent.

    **Carry to your side** (shown above) = `±` IR differential, sign chosen so positive means you earn carry on the ccy you hold over the period. Spread cost is always subtracted.

    **Near base notional**: `{fmt_money(t.near_base_notional, 2).lstrip('+')} {t.base_ccy}`
    **Far  base notional**: `{fmt_money(t.far_base_notional, 2).lstrip('+')} {t.base_ccy}` ({mode_label})
                """
            )


tab_quote, tab_cheat = st.tabs(["Quote", "Cheat sheet"])

with tab_quote:
    render_quote_tab()

with tab_cheat:
    render_cheat_sheet()
