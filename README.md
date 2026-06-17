# FX Swap Quoting Ticket

A Streamlit quoting tool for FX swaps. Designed to be opened on a desk
screen while a client is on the phone: enter spot, forward points, an
amount in either currency, and a spread, and read the full cashflow
ticket back to the client.

## Inputs

- **Currency pair** — G10 + common EM, stored in market-standard direction
  (`EURUSD`, `USDJPY`, `USDCHF`, `USDPLN`, …). The first three letters are
  the base currency.
- **Side** — `BUY` or `SELL` the **base** currency on the far date. Near
  leg is automatically the opposite.
- **Near date** and **far date** — calendar dates of the two legs. The
  swap is matched in base-ccy notional.
- **Spot rate** and **forward points** (in pips, signed). Pip factor is
  100 for JPY-quoted pairs and 10'000 otherwise.
- **Client spread (%)** — applied to the far leg only, always against the
  client (`+` on BUY, `−` on SELL).
- **Amount** in either the base or quote currency. If quote, the base
  notional is derived as `amount / spot` (so the near-leg quote-ccy
  amount equals what you typed).

## Output

A trade ticket showing, **from the client's perspective**:

| Leg | Value date | Rate | base ccy | quote ccy |
|-----|-----------|------|----------|-----------|
| Near (spot) | t_n | S | ± notional | ∓ notional × S |
| Far (mid) | t_f | F_mid | ∓ notional | ± notional × F_mid |
| Far (client) | t_f | F_client | ∓ notional | ± notional × F_client |

Signs: `+` you receive, `−` you pay. The bank's revenue (= client's
spread cost) in quote ccy is shown separately. The implied IR
differential `(F_mid − S)/S × 360/days` is reported in a collapsed
footer for context only.

## Formulas

```
F_mid              = S + P / pip_factor
F_client (BUY)     = F_mid × (1 + s/100)      # client pays more quote ccy
F_client (SELL)    = F_mid × (1 − s/100)      # client receives less quote ccy
days               = (far_date − near_date), calendar (ACT/360)
market swap rate   = (F_mid − S) / S × 360 / days        # informational
spread cost (qccy) = |F_client − F_mid| × base_notional  # bank revenue
```

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
├── app.py                  # Streamlit quoting ticket UI
├── fx_swap/
│   ├── pairs.py            # pair registry, pip factors
│   └── calculator.py       # cashflow logic and ticket builder
├── tests/
│   └── test_calculator.py
├── requirements.txt
└── README.md
```
