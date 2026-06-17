from datetime import date

import pytest

from fx_swap import compute_swap, get_pair


def test_eurusd_3m_market_rate():
    # EURUSD spot 1.0850, +50 pips over 90 days, no spread.
    r = compute_swap("EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1), 1.0850, 50.0, 0.0)
    assert r.days == 90
    assert r.pip_factor == 10_000
    assert r.forward_mid == pytest.approx(1.0850 + 50 / 10_000)
    expected_market = (r.forward_mid - 1.0850) / 1.0850 * 360 / 90
    assert r.market_swap_rate == pytest.approx(expected_market)
    # BUY: client carry = +market_swap_rate.
    assert r.rate_mid == pytest.approx(expected_market)
    # No spread -> rate_client == rate_mid, forward_client == forward_mid.
    assert r.spread_cost == pytest.approx(0.0)
    assert r.rate_client == pytest.approx(r.rate_mid)
    assert r.forward_client == r.forward_mid


def test_usdjpy_pip_factor_is_100():
    pair = get_pair("USDJPY")
    assert pair.pip_factor == 100
    r = compute_swap("USDJPY", "BUY", date(2026, 1, 1), date(2026, 2, 1), 150.00, 30.0, 0.0)
    assert r.forward_mid == pytest.approx(150.00 + 30 / 100)


def test_sell_at_forward_discount_gives_positive_carry():
    # USDCHF F<S -> market swap rate is negative -> SELL carry should be positive.
    r = compute_swap("USDCHF", "SELL", date(2026, 3, 5), date(2026, 4, 7), 0.782730, -27.7090, 0.0)
    assert r.market_swap_rate < 0
    assert r.rate_mid > 0
    assert r.rate_mid == pytest.approx(-r.market_swap_rate)


def test_buy_at_forward_discount_gives_negative_carry():
    r = compute_swap("USDCHF", "BUY", date(2026, 3, 5), date(2026, 4, 7), 0.782730, -27.7090, 0.0)
    assert r.market_swap_rate < 0
    assert r.rate_mid < 0
    assert r.rate_mid == pytest.approx(r.market_swap_rate)


def test_spread_always_reduces_client_carry_buy():
    r = compute_swap("USDCHF", "BUY", date(2026, 3, 5), date(2026, 4, 7), 0.782730, -27.7090, 0.10)
    # BUY cashflow: F_client > F_mid (client pays more quote ccy).
    assert r.forward_client > r.forward_mid
    # Carry: client now pays more carry -> rate_client < rate_mid (more negative).
    assert r.spread_cost > 0
    assert r.rate_client == pytest.approx(r.rate_mid - r.spread_cost)
    assert r.rate_client < r.rate_mid


def test_spread_always_reduces_client_carry_sell():
    r = compute_swap("USDCHF", "SELL", date(2026, 3, 5), date(2026, 4, 7), 0.782730, -27.7090, 0.10)
    # SELL cashflow: F_client < F_mid (client receives less quote ccy).
    assert r.forward_client < r.forward_mid
    # Carry: client earns less -> rate_client < rate_mid but both positive.
    assert r.rate_mid > 0
    assert r.rate_client > 0
    assert r.rate_client < r.rate_mid
    assert r.rate_client == pytest.approx(r.rate_mid - r.spread_cost)


def test_notional_cashflows():
    r = compute_swap(
        "EURUSD", "BUY", date(2026, 1, 1), date(2026, 4, 1),
        1.0850, 50.0, 0.10, notional_base=1_000_000.0,
    )
    assert r.near_leg_quote == pytest.approx(1_000_000 * 1.0850)
    assert r.far_leg_quote_mid == pytest.approx(1_000_000 * r.forward_mid)
    assert r.far_leg_quote_client == pytest.approx(1_000_000 * r.forward_client)
    # BUY: client pays more quote ccy -> spread P&L is positive (cost to client).
    assert r.spread_pnl_quote > 0


def test_far_must_be_after_near():
    with pytest.raises(ValueError):
        compute_swap("EURUSD", "BUY", date(2026, 4, 1), date(2026, 1, 1), 1.0850, 50.0, 0.0)


def test_unknown_pair():
    with pytest.raises(KeyError):
        compute_swap("XYZABC", "BUY", date(2026, 1, 1), date(2026, 4, 1), 1.0, 0.0, 0.0)
