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

- **Forward mid** — `F = S + P / pip_factor`
- **Annualised rate (mid)** — `r = (F − S) / S × 360 / days`
- **Forward client** — `F_client = F × (1 ± s/100)` with the sign chosen so
  that the spread disadvantages the client (`+` on BUY, `−` on SELL).
- **Annualised rate (client)** — same formula as above with `F_client`.

The difference between the two annualised rates is the spread cost expressed
as a per-annum rate.

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
