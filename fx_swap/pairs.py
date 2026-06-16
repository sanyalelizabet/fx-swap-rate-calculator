"""FX pair registry: market-standard quote convention and pip factors.

A pip is the smallest standard increment in which forward points are quoted.
For most pairs that is 1/10'000 of the quote currency (4 decimals).
For JPY-quoted pairs it is 1/100 (2 decimals).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FXPair:
    code: str          # market-standard form, e.g. "EURUSD"
    base: str
    quote: str
    pip_factor: float  # forward points are divided by this to get a quote-ccy amount


def _pip(quote: str) -> float:
    return 100.0 if quote == "JPY" else 10_000.0


def _make(code: str) -> FXPair:
    base, quote = code[:3], code[3:]
    return FXPair(code=code, base=base, quote=quote, pip_factor=_pip(quote))


# G10 majors, in market-standard direction.
_G10 = [
    "EURUSD", "USDJPY", "GBPUSD", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD",
    "EURCHF", "EURGBP", "EURJPY", "EURSEK", "EURNOK",
]

# Common EM, all USD-base by market convention.
_EM = [
    "USDSEK", "USDNOK", "USDPLN", "USDHUF", "USDCZK",
    "USDTRY", "USDZAR", "USDMXN", "USDSGD", "USDHKD",
    "USDCNH", "USDILS",
]

PAIRS: dict[str, FXPair] = {code: _make(code) for code in _G10 + _EM}


def get_pair(code: str) -> FXPair:
    code = code.upper().replace("/", "")
    if code not in PAIRS:
        raise KeyError(f"Unknown pair {code!r}. Known: {sorted(PAIRS)}")
    return PAIRS[code]
