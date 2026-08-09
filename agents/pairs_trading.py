"""
agents/pairs_trading.py
--------------------------
Correlation-based pair discovery + z-score divergence signals.

*** TWO FIXES FOUND VIA RIGOROUS STRESS TESTING ***
1. NaN-truthiness: `if spread.std() else 0.0` doesn't safely catch a NaN
   std (bool(nan) is True in Python) -- fixed with explicit np.isfinite check.
2. Lookback-window consistency: correlation used to be computed over the
   full history while z-score used only the recent lookback window --
   fixed so both describe the same period.
"""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
import config
import data_utils


def _build_return_matrix(symbols: list[str], lookback: int = config.PAIRS_LOOKBACK_DAYS) -> pd.DataFrame:
    series = {}
    for sym in symbols:
        df = data_utils.fetch_daily(sym, period="6mo")
        if df is None or df.empty:
            continue
        series[sym] = df["Close"].tail(lookback).pct_change().dropna()
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).dropna(how="any")


def discover_pairs(symbols: list[str] | None = None) -> list[tuple[str, str, float]]:
    symbols = symbols or config.WATCHLIST
    ret_matrix = _build_return_matrix(symbols)
    if ret_matrix.empty or ret_matrix.shape[1] < 2:
        return []
    corr = ret_matrix.corr()
    discovered = []
    for a, b in itertools.combinations(ret_matrix.columns, 2):
        c = corr.loc[a, b]
        if c >= config.PAIRS_MIN_CORRELATION:
            discovered.append((a, b, round(float(c), 3)))
    return sorted(discovered, key=lambda x: -x[2])


def _zscore_spread(price_a: pd.Series, price_b: pd.Series, lookback: int) -> float:
    spread = np.log(price_a) - np.log(price_b)
    spread = spread.tail(lookback)
    std = spread.std()
    if not np.isfinite(std) or std == 0:
        return 0.0
    return float((spread.iloc[-1] - spread.mean()) / std)


def evaluate_pair(sym_a: str, sym_b: str) -> dict:
    df_a = data_utils.fetch_daily(sym_a, period="6mo")
    df_b = data_utils.fetch_daily(sym_b, period="6mo")
    if df_a is None or df_b is None or df_a.empty or df_b.empty:
        return {"pair": f"{sym_a}/{sym_b}", "valid": False, "reason": "missing price history"}

    joined = pd.DataFrame({"a": df_a["Close"], "b": df_b["Close"]}).dropna()
    if len(joined) < 30:
        return {"pair": f"{sym_a}/{sym_b}", "valid": False, "reason": "insufficient overlapping history"}

    z = _zscore_spread(joined["a"], joined["b"], config.PAIRS_LOOKBACK_DAYS)
    signal = None
    if z >= config.PAIRS_ZSCORE_ENTRY:
        signal = f"Spread stretched high -- consider short {sym_a} / long {sym_b}"
    elif z <= -config.PAIRS_ZSCORE_ENTRY:
        signal = f"Spread stretched low -- consider long {sym_a} / short {sym_b}"

    recent = joined.tail(config.PAIRS_LOOKBACK_DAYS)
    correlation = float(recent["a"].pct_change().corr(recent["b"].pct_change()))
    return {"pair": f"{sym_a}/{sym_b}", "valid": True, "correlation": round(correlation, 3),
            "zscore": round(z, 2), "signal": signal}


def scan_pairs() -> pd.DataFrame:
    pairs_to_check = list(config.PAIRS_CANDIDATES)
    source_flag = {p: "manual" for p in pairs_to_check}

    if config.PAIRS_AUTO_DISCOVER:
        for a, b, corr in discover_pairs():
            key = (a, b)
            if key not in source_flag and (b, a) not in source_flag:
                pairs_to_check.append(key)
                source_flag[key] = f"auto (corr={corr})"

    rows = []
    for a, b in pairs_to_check:
        result = evaluate_pair(a, b)
        result["source"] = source_flag.get((a, b), "auto")
        rows.append(result)
    return pd.DataFrame(rows)
