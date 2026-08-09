"""
agents/quant_research.py
-------------------------
Backtests specific, named patterns against real fetched history, reports
win rate + sample size honestly.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import config
from agents.technical_analysis import rsi

FORWARD_WINDOW_DAYS = 5


def _forward_return(close: pd.Series, i: int, horizon: int) -> float | None:
    if i + horizon >= len(close):
        return None
    return float((close.iloc[i + horizon] / close.iloc[i]) - 1)


def backtest_rsi_oversold_bounce(daily_df: pd.DataFrame) -> dict:
    close = daily_df["Close"]
    r = rsi(close)
    occurrences = []
    for i in range(1, len(r) - 1):
        if r.iloc[i - 1] < config.RSI_OVERSOLD and r.iloc[i] >= config.RSI_OVERSOLD:
            fwd = _forward_return(close, i, FORWARD_WINDOW_DAYS)
            if fwd is not None:
                occurrences.append(fwd)
    return _summarize(occurrences, "RSI oversold bounce")


def backtest_gap_up_continuation(daily_df: pd.DataFrame) -> dict:
    close, openp = daily_df["Close"], daily_df["Open"]
    occurrences = []
    for i in range(1, len(close) - 1):
        prev_close = close.iloc[i - 1]
        gap_pct = (openp.iloc[i] - prev_close) / prev_close * 100
        if gap_pct >= 0.5:
            fwd = _forward_return(close, i, FORWARD_WINDOW_DAYS)
            if fwd is not None:
                occurrences.append(fwd)
    return _summarize(occurrences, "Gap-up continuation")


def _summarize(occurrences: list[float], name: str) -> dict:
    n = len(occurrences)
    if n == 0:
        return {"pattern": name, "sample_size": 0, "win_rate": None,
                "avg_return_pct": None, "note": "No historical occurrences found -- no statistic to report."}
    arr = np.array(occurrences)
    win_rate = float((arr > 0).mean() * 100)
    avg_return = float(arr.mean() * 100)
    confidence_note = ("small sample -- treat with caution" if n < 10 else
                        "reasonable sample" if n < 30 else "solid sample")
    return {"pattern": name, "sample_size": n, "win_rate": round(win_rate, 1),
            "avg_return_pct": round(avg_return, 2), "note": confidence_note}


def research(symbol: str, daily_df: pd.DataFrame) -> dict:
    if daily_df is None or daily_df.empty or len(daily_df) < 40:
        return {"symbol": symbol, "valid": False, "reason": "insufficient history"}
    rsi_result = backtest_rsi_oversold_bounce(daily_df)
    gap_result = backtest_gap_up_continuation(daily_df)

    def _score(res):
        if not res["sample_size"]:
            return 0.0
        confidence = min(res["sample_size"] / 30, 1.0)
        return (res["win_rate"] / 100) * confidence

    quant_score = round(max(_score(rsi_result), _score(gap_result)) * 100, 1)
    return {"symbol": symbol, "valid": True, "rsi_oversold_bounce": rsi_result,
            "gap_up_continuation": gap_result, "quant_score": quant_score}
