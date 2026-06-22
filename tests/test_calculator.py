from datetime import date

import pytest

from fx_swap import compute_ticket, get_pair, make_custom_pair


def _ticket(side="BUY", near_amount=1_000_000.0, near_amount_ccy="BASE",
            far_amount=None, far_amount_ccy="BASE",
            spread_rate=0.0, pair="EURUSD", spot=1.0850, points=50.0):
    return compute_ticket(
        pair=pair,
        side=side,
        near_date=date(2026, 1, 1),
        far_date=date(2026, 4, 1),
        spot=spot,
        forward_points=points,
        spread_rate=spread_rate,
        near_amount=near_amount,
        near_amount_ccy=near_amount_ccy,
        far_amount=far_amount,
        far_amount_ccy=far_amount_ccy,
    )


def test_forward_mid_uses_pip_factor():
    t = _ticket()
    assert t.pip_factor == 10_000
    assert t.forward_mid == pytest.approx(1.0850 + 50 / 10_000)


def test_usdjpy_pip_factor_is_100():
    t = _ticket(pair="USDJPY", spot=150.0, points=30.0)
    assert t.pip_factor == 100
    assert t.forward_mid == pytest.approx(150.0 + 30 / 100)


def test_days_count_is_calendar():
    t = _ticket()
    assert t.days == 90


def test_buy_forward_cashflow_signs():
    t = _ticket(side="BUY")
    assert t.near_leg.base_flow < 0
    assert t.near_leg.quote_flow > 0
    assert t.far_leg_mid.base_flow > 0
    assert t.far_leg_mid.quote_flow < 0
    assert abs(t.near_leg.base_flow) == pytest.approx(1_000_000.0)
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_000_000.0 * 1.0850)
    assert abs(t.far_leg_mid.quote_flow) == pytest.approx(1_000_000.0 * t.forward_mid)


def test_sell_forward_cashflow_signs():
    t = _ticket(side="SELL")
    assert t.near_leg.base_flow > 0
    assert t.near_leg.quote_flow < 0
    assert t.far_leg_mid.base_flow < 0
    assert t.far_leg_mid.quote_flow > 0


def test_matched_swap_default():
    # No far_amount -> matched-base swap, far_base = near_base.
    t = _ticket()
    assert t.is_uneven is False
    assert t.near_base_notional == pytest.approx(t.far_base_notional)


def test_near_amount_in_quote_uses_spot():
    # 1'085'000 USD on near, spot 1.0850 -> base = 1'000'000 EUR.
    t = _ticket(near_amount=1_085_000.0, near_amount_ccy="QUOTE")
    assert t.near_base_notional == pytest.approx(1_000_000.0)
    assert t.far_base_notional == pytest.approx(1_000_000.0)
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_085_000.0)


def test_uneven_swap_separate_base_notionals():
    t = _ticket(near_amount=1_000_000.0, far_amount=1_500_000.0)
    assert t.is_uneven is True
    assert t.near_base_notional == pytest.approx(1_000_000.0)
    assert t.far_base_notional == pytest.approx(1_500_000.0)
    assert abs(t.far_leg_mid.quote_flow) == pytest.approx(1_500_000.0 * t.forward_mid)


def test_far_amount_in_quote_uses_forward_client():
    # Far in QUOTE -> base = quote / forward_client (preserves the user-entered
    # quote amount as the actual client cashflow on the far leg).
    t = _ticket(
        near_amount=1_000_000.0,
        far_amount=1_090_000.0, far_amount_ccy="QUOTE",
        spread_rate=0.001,
    )
    assert t.far_base_notional == pytest.approx(1_090_000.0 / t.forward_client)
    # And the client-leg quote cashflow equals what the user typed.
    assert abs(t.far_leg_client.quote_flow) == pytest.approx(1_090_000.0)


def test_buy_spread_pushes_forward_up_and_costs_client_quote():
    t = _ticket(side="BUY", spread_rate=0.001)
    assert t.forward_client == pytest.approx(t.forward_mid + 0.001)
    assert t.far_leg_client.quote_flow < t.far_leg_mid.quote_flow
    assert t.spread_cost_quote == pytest.approx(
        abs(t.far_leg_client.quote_flow - t.far_leg_mid.quote_flow)
    )
    assert t.spread_cost_quote > 0


def test_sell_spread_pushes_forward_down_and_costs_client_quote():
    t = _ticket(side="SELL", spread_rate=0.001)
    assert t.forward_client == pytest.approx(t.forward_mid - 0.001)
    assert t.far_leg_client.quote_flow < t.far_leg_mid.quote_flow
    assert t.spread_cost_quote > 0


def test_zero_spread_keeps_client_and_mid_equal():
    t = _ticket(spread_rate=0.0)
    assert t.forward_client == pytest.approx(t.forward_mid)
    assert t.far_leg_client.quote_flow == pytest.approx(t.far_leg_mid.quote_flow)
    assert t.spread_cost_quote == pytest.approx(0.0)


def test_eurchf_matched_quote_swap():
    # Trader-level test case: matched in CHF (595k each leg), absolute-rate
    # spread of 0.001395 added on top of (spot + pips). Near leg uses spot,
    # far leg uses F_client so the user-entered CHF amount is preserved.
    # side=BUY because the client sells EUR on near, buys EUR back on far.
    t = compute_ticket(
        pair=make_custom_pair("EUR", "CHF"),
        side="BUY",
        near_date=date(2026, 6, 22),
        far_date=date(2026, 9, 20),
        spot=0.93003,
        forward_points=-49.31,           # -49.31 pips = -0.004931 rate (pip_factor=10000)
        spread_rate=0.001395,
        near_amount=595_000.0, near_amount_ccy="QUOTE",
        far_amount=595_000.0, far_amount_ccy="QUOTE",
    )
    assert t.forward_mid == pytest.approx(0.925099, abs=1e-6)
    assert t.forward_client == pytest.approx(0.926494, abs=1e-6)
    # Near leg: -639'764.31 EUR / +595'000 CHF
    assert t.near_leg.base_flow == pytest.approx(-639_764.31, abs=0.01)
    assert t.near_leg.quote_flow == pytest.approx(+595_000.0, abs=0.01)
    # Far leg at client: +642'205.99 EUR / -595'000 CHF
    assert t.far_leg_client.base_flow == pytest.approx(+642_205.99, abs=0.01)
    assert t.far_leg_client.quote_flow == pytest.approx(-595_000.0, abs=0.01)


def test_market_swap_rate_is_ir_differential():
    t = _ticket()
    expected = (t.forward_mid - 1.0850) / 1.0850 * 360 / 90
    assert t.market_swap_rate == pytest.approx(expected)


def test_far_must_be_after_near():
    with pytest.raises(ValueError):
        compute_ticket(
            "EURUSD", "BUY", date(2026, 4, 1), date(2026, 1, 1),
            1.0850, 50.0, 0.0, near_amount=1_000_000.0,
        )


def test_unknown_pair():
    with pytest.raises(KeyError):
        compute_ticket(
            "XYZABC", "BUY", date(2026, 1, 1), date(2026, 4, 1),
            1.0, 0.0, 0.0, near_amount=1.0,
        )


def test_custom_pair_jpy_quote_gets_pip_factor_100():
    pair = make_custom_pair("MYR", "JPY")
    assert pair.pip_factor == 100
    assert pair.code == "MYRJPY"


def test_custom_pair_non_jpy_defaults_to_10000():
    pair = make_custom_pair("EUR", "TRY")
    assert pair.pip_factor == 10_000


def test_custom_pair_used_in_compute_ticket():
    pair = make_custom_pair("EUR", "RON")
    t = compute_ticket(
        pair, "BUY", date(2026, 1, 1), date(2026, 4, 1),
        5.0, 100.0, 0.0, near_amount=1_000_000.0,
    )
    assert t.pair == "EURRON"
    assert t.base_ccy == "EUR"
    assert t.quote_ccy == "RON"
    assert t.forward_mid == pytest.approx(5.0 + 100 / 10_000)


def test_custom_pair_rejects_bad_codes():
    with pytest.raises(ValueError):
        make_custom_pair("EU", "USD")
    with pytest.raises(ValueError):
        make_custom_pair("EUR", "USD2")
    with pytest.raises(ValueError):
        make_custom_pair("USD", "USD")
