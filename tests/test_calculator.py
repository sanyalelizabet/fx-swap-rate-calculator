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
    assert t.is_matched is True
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_085_000.0)


def test_uneven_swap_separate_notionals():
    # Near 1mio EUR, far 1.5mio EUR.
    t = compute_ticket(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.0,
        amount=1_000_000.0, amount_ccy="BASE",
        far_amount=1_500_000.0, far_amount_ccy="BASE",
    )
    assert t.near_base_notional == pytest.approx(1_000_000.0)
    assert t.far_base_notional == pytest.approx(1_500_000.0)
    assert t.is_matched is False
    assert abs(t.near_leg.base_flow) == pytest.approx(1_000_000.0)
    assert abs(t.far_leg_mid.base_flow) == pytest.approx(1_500_000.0)
    assert abs(t.near_leg.quote_flow) == pytest.approx(1_000_000.0 * 1.0850)
    assert abs(t.far_leg_mid.quote_flow) == pytest.approx(1_500_000.0 * t.forward_mid)


def test_uneven_far_in_quote_ccy_uses_forward_rate():
    # Far amount 1.09mio USD should derive a base notional of 1.09e6 / F_mid.
    t = compute_ticket(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.0,
        amount=1_000_000.0, amount_ccy="BASE",
        far_amount=1_090_000.0, far_amount_ccy="QUOTE",
    )
    expected_far_base = 1_090_000.0 / t.forward_mid
    assert t.far_base_notional == pytest.approx(expected_far_base)
    assert t.is_matched is False


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
