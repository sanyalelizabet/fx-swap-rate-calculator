"""Streamlit quoting ticket for an FX swap.

Inputs: pair (base/quote/pip factor), side, near + far dates, spot,
forward points (pips), client spread (% of spot OR pips), notionals.

Output: 1) Quote (rates), 2) Round-trip P&L, 3) Cashflows, then details.
Calculation lives in fx_swap.calculator; this file is UI only.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from fx_swap import compute_ticket, make_custom_pair

st.set_page_config(page_title="FX Swap Quoting Ticket", layout="wide")

# Streamlit's colored-text marker used everywhere we highlight the client side.
CLIENT_COLOR = "orange"


def fmt_money(x: float, dp: int = 2) -> str:
    """Swiss-style with apostrophe thousands and explicit sign for non-zero."""
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
| **Positive** (F > S) | base ccy at **premium** | base ccy rate **lower** than quote ccy |
| **Negative** (F < S) | base ccy at **discount** | base ccy rate **higher** than quote ccy |

`F = S × (1 + r_quote × t/360) / (1 + r_base × t/360)`

---

### Bank spread direction (always against the client)

Far leg only. Bank quotes a far rate worse for whatever direction the client trades on the far leg.

| Client on near | Client on far | Bank shifts F | Forward points |
|---|---|---|---|
| **SELLS base** | buys base back | **up** | go up |
| **BUYS base** | sells base back | **down** | go down |

---

### Carry to the client

Whichever ccy the client bought on the near leg is what they hold over the period.

| Client near | Holds | Carry |
|---|---|---|
| BUYS base | base | `r_base − r_quote` |
| SELLS base | quote | `r_quote − r_base` |

Spread always reduces this carry.
        """
    )


def _render_inputs() -> dict | None:
    """Sidebar form. Returns inputs dict on submit, else None."""
    st.sidebar.title("Trade")

    with st.sidebar:
        # Pair + pip factor + side stay outside the form so changing them
        # reruns the page and dependent UI updates.
        cb, cq = st.columns(2)
        base = cb.text_input("Base", value="EUR", max_chars=3).upper().strip()
        quote = cq.text_input("Quote", value="USD", max_chars=3).upper().strip()

        try:
            # Validate the codes early.
            _default_pair = make_custom_pair(base, quote)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        # Per-quote-ccy key so switching the quote ccy resets the pip factor
        # back to its market default (10'000 or 100 for JPY).
        pip_factor = st.number_input(
            "Pip factor",
            value=float(_default_pair.pip_factor),
            min_value=1.0,
            step=1.0,
            format="%.0f",
            key=f"pip_factor_{quote}",
            help="Forward points are divided by this to get a quote-ccy rate add-on. "
                 "Defaults to 10'000 (or 100 if quote is JPY). Edit only if your pair "
                 "quotes pips on a non-standard convention.",
        )

        try:
            pair_obj = make_custom_pair(base, quote, pip_factor=pip_factor)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        near_side_label = st.radio(
            "Side (near / far)",
            options=["Buy/Sell", "Sell/Buy"],
            horizontal=True,
            help=(
                f"Buy/Sell = buy {pair_obj.base} on near, sell {pair_obj.base} "
                f"back on far. Sell/Buy = the opposite."
            ),
        )
        # Calculator expects the far-leg side. Near is always opposite.
        side = "SELL" if near_side_label == "Buy/Sell" else "BUY"

        st.divider()

        with st.form("ticket_inputs", border=False):
            today = date.today()
            cd1, cd2 = st.columns(2)
            near_date = cd1.date_input("Near date", value=today + timedelta(days=2))
            far_date = cd2.date_input("Far date", value=today + timedelta(days=92))

            spot = st.number_input(
                "Spot", value=1.0850, format="%.6f", min_value=0.0,
            )
            forward_points = st.number_input(
                "Forward points (pips)",
                value=50.0,
                format="%.4f",
                help="Signed. Positive = base ccy at premium forward.",
            )

            cs1, cs2 = st.columns([2, 1])
            spread_value = cs1.number_input(
                "Spread",
                value=0.1000,
                min_value=0.0,
                format="%.4f",
                help=(
                    "Applied against the client on the far leg.\n\n"
                    "% of spot → spread_rate = spot × (%) / 100\n\n"
                    "Pips → spread_rate = pips / pip_factor"
                ),
            )
            spread_unit = cs2.selectbox(
                "Unit",
                options=["% of spot", "Pips"],
                index=0,
                label_visibility="collapsed",
            )
            if spread_unit == "% of spot":
                spread_rate = spot * spread_value / 100.0
            else:
                spread_rate = spread_value / pair_obj.pip_factor

            st.markdown("**Notionals**")
            cn1, cn2 = st.columns([2, 1])
            near_amount = cn1.number_input(
                "Near leg",
                value=1_000_000.0, min_value=0.0, step=100_000.0, format="%.2f",
                key="near_amount",
            )
            near_amount_ccy = cn2.selectbox(
                "in",
                options=[pair_obj.base, pair_obj.quote],
                key="near_amount_ccy",
            )

            cf1, cf2 = st.columns([2, 1])
            far_amount = cf1.number_input(
                "Far leg",
                value=1_000_000.0, min_value=0.0, step=100_000.0, format="%.2f",
                key="far_amount",
            )
            far_amount_ccy = cf2.selectbox(
                "in",
                options=[pair_obj.base, pair_obj.quote],
                key="far_amount_ccy",
            )

            submitted = st.form_submit_button(
                "Quote", use_container_width=True, type="primary"
            )

        if not submitted:
            return None

        return dict(
            pair_obj=pair_obj,
            side=side,
            near_side_label=near_side_label,
            near_date=near_date,
            far_date=far_date,
            spot=spot,
            forward_points=forward_points,
            spread_rate=spread_rate,
            spread_value=spread_value,
            spread_unit=spread_unit,
            near_amount=near_amount,
            near_amount_ccy="BASE" if near_amount_ccy == pair_obj.base else "QUOTE",
            far_amount=far_amount,
            far_amount_ccy="BASE" if far_amount_ccy == pair_obj.base else "QUOTE",
        )


def _render_results(t, inputs: dict) -> None:
    # --- Compact breadcrumb header ---
    notional_str = (
        f"{fmt_money(t.near_base_notional, 0).lstrip('+')} / "
        f"{fmt_money(t.far_base_notional, 0).lstrip('+')} {t.base_ccy}"
        if t.is_uneven
        else f"{fmt_money(t.near_base_notional, 0).lstrip('+')} {t.base_ccy}"
    )
    st.markdown(
        f"**{t.pair}** &nbsp;·&nbsp; {inputs['near_side_label']} "
        f"&nbsp;·&nbsp; {t.days} days &nbsp;·&nbsp; {notional_str} "
        f"&nbsp;·&nbsp; pip factor {fmt_money(t.pip_factor, 0).lstrip('+')}"
    )

    spread_pips = (t.forward_client - t.forward_mid) * t.pip_factor
    fwd_points_client = (t.forward_client - t.spot) * t.pip_factor

    # ======================================================================
    # 1. QUOTE  — three rates, client highlighted
    # ======================================================================
    st.markdown("### 1. Quote")
    st.markdown(
        f"""
| | Rate | vs spot |
|---|---|---|
| Spot | `{fmt_rate(t.spot, 6)}` | — |
| Forward (mid) | `{fmt_rate(t.forward_mid, 6)}` | `{fmt_rate(t.forward_points, 2)}` pips |
| :{CLIENT_COLOR}[**Forward (client)**] | :{CLIENT_COLOR}[**`{fmt_rate(t.forward_client, 6)}`**] | :{CLIENT_COLOR}[**`{fmt_rate(fwd_points_client, 2)}` pips**] (incl. `{fmt_rate(spread_pips, 2)}` spread) |
"""
    )

    # ======================================================================
    # 2. ROUND-TRIP P&L  — mid vs client, side aware, rate-only annualisation
    # ======================================================================
    net_base_mid = t.near_leg.base_flow + t.far_leg_mid.base_flow
    net_quote_mid = t.near_leg.quote_flow + t.far_leg_mid.quote_flow
    net_quote_client = t.near_leg.quote_flow + t.far_leg_client.quote_flow

    cf_sign = 1.0 if t.side == "BUY" else -1.0
    ann_mid = -cf_sign * (t.forward_mid - t.spot) / t.spot * 360.0 / t.days
    ann_client = -cf_sign * (t.forward_client - t.spot) / t.spot * 360.0 / t.days

    st.markdown("### 2. Round-trip P&L")
    st.markdown(
        f"""
| | Mid (no spread) | :{CLIENT_COLOR}[**Client (with spread)**] | Δ (spread cost) |
|---|---|---|---|
| Net {t.quote_ccy} | `{fmt_money(net_quote_mid, 2)}` | :{CLIENT_COLOR}[**`{fmt_money(net_quote_client, 2)}`**] | `{fmt_money(net_quote_client - net_quote_mid, 2)}` |
| Annualised (rate) | `{fmt_pct(ann_mid)}` | :{CLIENT_COLOR}[**`{fmt_pct(ann_client)}`**] | `{fmt_pct(ann_client - ann_mid)}` |

**Bank revenue**: `{fmt_money(t.spread_cost_quote, 2).lstrip('+')} {t.quote_ccy}` &nbsp;·&nbsp; sign convention: **+ client receives, − client pays**
"""
    )

    if abs(net_base_mid) > 1e-9:
        st.caption(
            f"Uneven swap — non-zero net in {t.base_ccy}: "
            f"`{fmt_money(net_base_mid, 2)}` (same at mid and client; "
            f"spread is in {t.quote_ccy} only)."
        )

    # ======================================================================
    # 3. CASHFLOWS  — table, client row highlighted
    # ======================================================================
    st.markdown("### 3. Cashflows")
    rows = [
        {
            "Leg": "Near (spot)",
            "Value date": t.near_leg.value_date.isoformat(),
            "Rate": fmt_rate(t.near_leg.fx_rate, 6),
            t.base_ccy: fmt_money(t.near_leg.base_flow, 2),
            t.quote_ccy: fmt_money(t.near_leg.quote_flow, 2),
        },
        {
            "Leg": "Far (mid)",
            "Value date": t.far_leg_mid.value_date.isoformat(),
            "Rate": fmt_rate(t.far_leg_mid.fx_rate, 6),
            t.base_ccy: fmt_money(t.far_leg_mid.base_flow, 2),
            t.quote_ccy: fmt_money(t.far_leg_mid.quote_flow, 2),
        },
        {
            "Leg": "Far (client)",
            "Value date": t.far_leg_client.value_date.isoformat(),
            "Rate": fmt_rate(t.far_leg_client.fx_rate, 6),
            t.base_ccy: fmt_money(t.far_leg_client.base_flow, 2),
            t.quote_ccy: fmt_money(t.far_leg_client.quote_flow, 2),
        },
    ]
    df = pd.DataFrame(rows)

    def _highlight_client(row):
        if row["Leg"] == "Far (client)":
            return ["background-color: rgba(255, 165, 0, 0.18); font-weight: 600"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df.style.apply(_highlight_client, axis=1),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("Sign convention: **+ client receives, − client pays**.")

    # ======================================================================
    # Details (collapsed)
    # ======================================================================
    with st.expander("Formulas and details"):
        pip_factor_str = fmt_money(t.pip_factor, 0).lstrip("+")
        mode_label = "uneven swap" if t.is_uneven else "matched swap"
        spread_sign = "+" if t.side == "BUY" else "−"
        st.markdown(
            f"""
**Pair**: {t.pair} &nbsp; (base = {t.base_ccy}, quote = {t.quote_ccy}, pip factor = {pip_factor_str}, mode = {mode_label})

**Spread input**: `{inputs['spread_value']:.4f} {inputs['spread_unit']}` → `spread_rate = {fmt_rate(t.spread_rate, 6)}` ({spread_pips:+.2f} pips)

**F_mid** = `S + P/pip = {fmt_rate(t.spot, 6)} + {fmt_rate(t.forward_points, 4)} / {pip_factor_str} = {fmt_rate(t.forward_mid, 6)}`

**F_client** = `F_mid {spread_sign} spread = {fmt_rate(t.forward_client, 6)}`

**Rates applied**: near = `{fmt_rate(t.near_leg.fx_rate, 6)}`, far mid = `{fmt_rate(t.far_leg_mid.fx_rate, 6)}`, far client = `{fmt_rate(t.far_leg_client.fx_rate, 6)}`

**Implied IR differential** (market property, side-independent): `(F_mid − S) / S × 360/days = {fmt_pct(t.market_swap_rate)}` ≈ `r_{t.quote_ccy.lower()} − r_{t.base_ccy.lower()}`

**Annualised P&L formula** (side-aware, notional-independent): `−sign(side) · (F − S) / S × 360/days`. Spread cost annualised = `−(spread_rate / S) × 360/days`.

**Notionals**: near = `{fmt_money(t.near_base_notional, 2).lstrip('+')} {t.base_ccy}`, far = `{fmt_money(t.far_base_notional, 2).lstrip('+')} {t.base_ccy}`
            """
        )


def render_quote_tab() -> None:
    inputs = _render_inputs()
    if not inputs:
        st.info("Fill in the trade in the left panel and click **Quote**.")
        return

    try:
        t = compute_ticket(
            pair=inputs["pair_obj"],
            side=inputs["side"],
            near_date=inputs["near_date"],
            far_date=inputs["far_date"],
            spot=inputs["spot"],
            forward_points=inputs["forward_points"],
            spread_rate=inputs["spread_rate"],
            near_amount=inputs["near_amount"],
            near_amount_ccy=inputs["near_amount_ccy"],
            far_amount=inputs["far_amount"],
            far_amount_ccy=inputs["far_amount_ccy"],
        )
    except (ValueError, KeyError) as e:
        st.error(str(e))
        return

    _render_results(t, inputs)


st.title("FX Swap Quoting Ticket")
st.caption(
    "ACT/360 · cashflows from the client's perspective · spread always against the client on the far leg"
)

tab_quote, tab_cheat = st.tabs(["Quote", "Cheat sheet"])

with tab_quote:
    render_quote_tab()

with tab_cheat:
    render_cheat_sheet()
