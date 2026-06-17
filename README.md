# FX Swap Rate Calculator

A small Streamlit app that converts FX forward points into an annualised swap
rate using the ACT/360 day-count convention, and applies a client spread to
the far leg of the swap.

## Inputs

- **Currency pair** — G10 + common EM, stored in market-standard direction
  (`EURUSD`, `USDJPY`, `USDCHF`, `USDPLN`, …). The first three letters are the
  base currency.
- **Side** — `BUY` or `SELL` the base currency forward.
- **Near date** and **far date** — calendar dates of the two legs of the swap.
- **Spot rate** — the prevailing spot.
- **Forward points** — quoted in pips. The pip factor is 100 for JPY-quoted
  pairs and 10'000 otherwise. Sign matters: a positive number means the base
  currency trades at a premium forward, negative means a discount.
- **Client spread (%)** — applied to the far leg only, always against the
  client.

## Outputs

The displayed annualised rate is the **carry to the client's side of the
swap**, not the sign-symmetric market swap rate. Rationale: a SELL-forward
swap (buy spot, sell forward) leaves the client holding the base ccy over
the period, so their carry is `r_base − r_quote`. A BUY-forward swap
leaves the client holding the quote ccy, so their carry is `r_quote −
r_base`. The sign therefore flips with side:

```
market swap rate   m       = (F_mid − S) / S × 360 / days     # objective, = r_quote − r_base
client carry (mid) r_mid   = +m for BUY, −m for SELL
```

The spread is applied to the far leg only:

```
F_client_BUY  = F_mid × (1 + s/100)   # client pays more quote ccy
F_client_SELL = F_mid × (1 − s/100)   # client receives less quote ccy
```

The spread cost as an annualised rate is taken as an absolute value and is
**always subtracted** from the client's carry, regardless of side (a bank
spread can never improve the client's carry):

```
spread_cost = |F_client − F_mid| / S × 360 / days     # >= 0
r_client    = r_mid − spread_cost
```

Example — USDCHF, S=0.78273, P=−27.71 pips, 33 days, SELL, spread 0.10%:

- market swap rate `m` = −3.86% (USD trades at forward discount because
  USD rates are higher than CHF)
- client carry mid `r_mid` = +3.86% (client is long USD over the period,
  earning the rate differential)
- spread cost = 1.09% per annum
- client carry post-spread = +3.86% − 1.09% = **+2.77%**

The cashflow panel shows the actual CHF amounts on near and far legs at
mid and at the client rate — those are computed from the F_client formulas
above and reflect the true economic outcome (client receives 779.96 CHF
less than mid on a 1mio USD ticket in the example).

## Why ACT/360?

ACT/360 is the standard money-market day count for the major currencies
involved in FX swap pricing (USD, EUR, GBP — though GBP money markets
traditionally use ACT/365, FX swap quoting on cable still uses ACT/360 by
convention).

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Tests

```bash
pytest
```

## Project layout

```
fx-swap-rate-calculator/
├── app.py                  # Streamlit UI
├── fx_swap/
│   ├── pairs.py            # pair registry, pip factors
│   └── calculator.py       # core math
├── tests/
│   └── test_calculator.py
├── requirements.txt
└── README.md
```
