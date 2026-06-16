from datetime import date

import pytest

from fx_swap import compute_swap, get_pair


def test_eurusd_3m_mid_rate():
    # EURUSD spot 1.0850, +50 pips over 90 days, no spread.
    r = compute_swap("EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1), 1.0850, 50.0, 0.0)
    assert r.days == 90
    assert r.pip_factor == 10_000
    assert r.forward_mid == pytest.approx(1.0850 + 50 / 10_000)
    expected_rate = (r.forward_mid - 1.0850) / 1.0850 * 360 / 90
    assert r.rate_mid == pytest.approx(expected_rate)
    assert r.forward_client == r.forward_mid  # no spread


def test_usdjpy_pip_factor_is_100():
    pair = get_pair("USDJPY")
    assert pair.pip_factor == 100
    r = compute_swap("USDJPY", "BUY", date(2026, 1, 1), date(2026, 2, 1), 150.00, 30.0, 0.0)
    assert r.forward_mid == pytest.approx(150.00 + 30 / 100)


def test_spread_against_client_buy_raises_far_leg():
    r = compute_swap("EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1), 1.0850, 50.0, 0.10)
    assert r.forward_client > r.forward_mid
    assert r.rate_client > r.rate_mid


def test_spread_against_client_sell_lowers_far_leg():
    r = compute_swap("EURUSD", "SELL", date(2026, 1, 1), date(2026, 4, 1), 1.0850, 50.0, 0.10)
    assert r.forward_client < r.forward_mid
    assert r.rate_client < r.rate_mid


def test_far_must_be_after_near():
    with pytest.raises(ValueError):
        compute_swap("EURUSD", "BUY", date(2026, 4, 1), date(2026, 1, 1), 1.0850, 50.0, 0.0)


def test_notional_cashflows():
    r = compute_swap(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.10, notional_base=1_000_000.0,
    )
    assert r.near_leg_quote == pytest.approx(1_000_000 * 1.0850)
    assert r.far_leg_quote_mid == pytest.approx(1_000_000 * r.forward_mid)
    assert r.far_leg_quote_client == pytest.approx(1_000_000 * r.forward_client)
    # Spread against a BUY client raises the far leg -> client pays more quote ccy.
    assert r.spread_pnl_quote > 0


def test_unknown_pair():
    with pytest.raises(KeyError):
        compute_swap("XYZABC", "BUY", date(2026, 1, 1), date(2026, 4, 1), 1.0, 0.0, 0.0)
