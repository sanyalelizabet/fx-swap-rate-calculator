from datetime import date

import pytest

from fx_swap import compute_ticket, get_pair, make_custom_pair


def _ticket(side="BUY", amount=1_000_000.0, amount_ccy="BASE", spread_pct=0.0,
            pair="EURUSD", spot=1.0850, points=50.0):
    return compute_ticket(
        pair=pair,
        side=side,
        near_date=date(2026, 1, 1),
        far_date=date(2026, 4, 1),
        spot=spot,
        forward_points=points,
        spread_pct=spread_pct,
        amount=amount,
        amount_ccy=amount_ccy,
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
    # BUY forward = SELL spot + BUY forward.
    # Near: pay base (-), receive quote (+). Far: receive base (+), pay quote (-).
    t = _ticket(side="BUY", amount=1_000_000.0)
    assert t.near_leg.base_flow < 0
    assert t.near_leg.quote_flow > 0
    assert t.far_leg_mid.base_flow > 0
    assert t.far_leg_mid.quote_flow < 0
    # Magnitudes match notional.
    assert abs(t.near_leg.base_flow) == pytest.approx(1_000_000.0)
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_000_000.0 * 1.0850)
    assert abs(t.far_leg_mid.quote_flow) == pytest.approx(1_000_000.0 * t.forward_mid)


def test_sell_forward_cashflow_signs():
    # SELL forward = BUY spot + SELL forward.
    # Near: receive base (+), pay quote (-). Far: pay base (-), receive quote (+).
    t = _ticket(side="SELL")
    assert t.near_leg.base_flow > 0
    assert t.near_leg.quote_flow < 0
    assert t.far_leg_mid.base_flow < 0
    assert t.far_leg_mid.quote_flow > 0


def test_amount_in_quote_ccy_derives_base():
    # 1'085'000 USD in EURUSD spot 1.0850 -> base notional = 1'000'000 EUR.
    t = _ticket(amount=1_085_000.0, amount_ccy="QUOTE")
    assert t.near_base_notional == pytest.approx(1_000_000.0)
    assert t.far_base_notional == pytest.approx(1_000_000.0)
    assert t.is_free is False
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_085_000.0)


def test_free_mode_uses_entered_amounts_directly():
    # All four cashflow magnitudes entered; rates may differ from spot/forward.
    t = compute_ticket(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.0,
        near_base_amount=1_000_000.0,
        near_quote_amount=1_083_000.0,   # implies near rate 1.0830, off spot
        far_base_amount=1_200_000.0,
        far_quote_amount=1_310_000.0,    # implies far rate ~1.0917
    )
    assert t.is_free is True
    assert abs(t.near_leg.base_flow) == pytest.approx(1_000_000.0)
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_083_000.0)
    assert abs(t.far_leg_mid.base_flow) == pytest.approx(1_200_000.0)
    assert abs(t.far_leg_mid.quote_flow) == pytest.approx(1_310_000.0)
    assert t.near_leg.fx_rate == pytest.approx(1.083)
    assert t.far_leg_mid.fx_rate == pytest.approx(1_310_000.0 / 1_200_000.0)


def test_free_mode_swap_rate_uses_implied_rates():
    t = compute_ticket(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.0,
        near_base_amount=1_000_000.0, near_quote_amount=1_083_000.0,
        far_base_amount=1_000_000.0, far_quote_amount=1_090_000.0,
    )
    expected = (1.090 - 1.083) / 1.083 * 360 / 90
    assert t.market_swap_rate == pytest.approx(expected)


def test_free_mode_spread_applies_to_far_quote_buy():
    t = compute_ticket(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.10,
        near_base_amount=1_000_000.0, near_quote_amount=1_083_000.0,
        far_base_amount=1_000_000.0, far_quote_amount=1_090_000.0,
    )
    # BUY: client pays more quote on far -> magnitude grows by (1 + s/100).
    assert abs(t.far_leg_client.quote_flow) == pytest.approx(1_090_000.0 * 1.001)
    assert t.spread_cost_quote == pytest.approx(1_090_000.0 * 0.001)


def test_free_mode_rejects_partial_specification():
    with pytest.raises(ValueError):
        compute_ticket(
            "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
            1.0850, 50.0, 0.0,
            near_base_amount=1_000_000.0,
            # missing the other three
        )


def test_free_mode_rejects_mixing_with_matched_amount():
    with pytest.raises(ValueError):
        compute_ticket(
            "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
            1.0850, 50.0, 0.0,
            amount=1_000_000.0,
            near_base_amount=1_000_000.0, near_quote_amount=1_083_000.0,
            far_base_amount=1_000_000.0, far_quote_amount=1_090_000.0,
        )


def test_matched_mode_requires_amount():
    with pytest.raises(ValueError):
        compute_ticket(
            "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
            1.0850, 50.0, 0.0,
        )


def test_buy_spread_makes_client_pay_more_quote():
    t = _ticket(side="BUY", spread_pct=0.10)
    # Client far-leg quote flow is negative; "more pay" = more negative.
    assert t.far_leg_client.quote_flow < t.far_leg_mid.quote_flow
    # Bank revenue equals the magnitude of the difference, positive.
    assert t.spread_cost_quote == pytest.approx(
        abs(t.far_leg_client.quote_flow - t.far_leg_mid.quote_flow)
    )
    assert t.spread_cost_quote > 0


def test_sell_spread_makes_client_receive_less_quote():
    t = _ticket(side="SELL", spread_pct=0.10)
    # Client far-leg quote flow is positive; "less receive" = less positive.
    assert t.far_leg_client.quote_flow < t.far_leg_mid.quote_flow
    assert t.spread_cost_quote > 0


def test_zero_spread_keeps_client_and_mid_equal():
    t = _ticket(spread_pct=0.0)
    assert t.forward_client == pytest.approx(t.forward_mid)
    assert t.far_leg_client.quote_flow == pytest.approx(t.far_leg_mid.quote_flow)
    assert t.spread_cost_quote == pytest.approx(0.0)


def test_market_swap_rate_is_ir_differential():
    t = _ticket()
    expected = (t.forward_mid - 1.0850) / 1.0850 * 360 / 90
    assert t.market_swap_rate == pytest.approx(expected)


def test_far_must_be_after_near():
    with pytest.raises(ValueError):
        compute_ticket(
            "EURUSD", "BUY", date(2026, 4, 1), date(2026, 1, 1),
            1.0850, 50.0, 0.0, 1_000_000.0, "BASE",
        )


def test_unknown_pair():
    with pytest.raises(KeyError):
        compute_ticket(
            "XYZABC", "BUY", date(2026, 1, 1), date(2026, 4, 1),
            1.0, 0.0, 0.0, 1.0, "BASE",
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
        5.0, 100.0, 0.0, 1_000_000.0, "BASE",
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
