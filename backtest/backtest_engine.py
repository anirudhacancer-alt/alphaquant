"""
backtest/backtest_engine.py
------------------------------
Decision Agent backtesting harness -- validates whether the COMBINED
weighted confidence score beats any single signal alone. Walk-forward,
no lookahead.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import config
import data_utils
from agents import technical_analysis, quant_research, regime_detection, decision_agent

MIN_HISTORY_DAYS = 260


def _score_snapshot(daily_slice: pd.DataFrame) -> dict | None:
    if len(daily_slice) < MIN_HISTORY_DAYS:
        return None
    ta = technical_analysis.analyze("bt", daily_slice, daily_slice)
    if not ta.get("valid"):
        return None
    quant = quant_research.research("bt", daily_slice)
    regime = regime_detection.detect_regime(daily_slice)

    last_price, atr_val = ta["last_price"], ta["atr"]
    if atr_val <= 0:
        return None
    stop = last_price - config.STOP_ATR_MULTIPLE * atr_val
    t2 = last_price + config.TARGET_ATR_MULTIPLES["T2"] * atr_val
    reward_risk = abs(t2 - last_price) / abs(last_price - stop) if last_price != stop else 0

    t_score = decision_agent.technical_score(ta)
    q_score = quant.get("quant_score", 0.0) if quant.get("valid") else 50.0
    r_score = decision_agent.regime_score(regime, direction="long")
    rk_score = decision_agent.risk_quality_score(reward_risk)

    w = config.DECISION_WEIGHTS
    w_sum = w["technical"] + w["quant"] + w["regime"] + w["risk_quality"]
    combined = (t_score * w["technical"] + q_score * w["quant"] +
                r_score * w["regime"] + rk_score * w["risk_quality"]) / w_sum

    return {"technical": t_score, "quant": q_score, "regime": r_score,
            "risk_quality": rk_score, "combined": combined, "reward_risk": reward_risk}


def backtest_symbol(symbol: str, period: str = "2y", horizon_days: int = 5, stride: int = 5) -> pd.DataFrame:
    daily_df = data_utils.fetch_daily(symbol, period=period)
    if daily_df is None or len(daily_df) < MIN_HISTORY_DAYS + horizon_days + 5:
        return pd.DataFrame()
    rows = []
    for t in range(MIN_HISTORY_DAYS, len(daily_df) - horizon_days, stride):
        slice_df = daily_df.iloc[:t + 1]
        snapshot = _score_snapshot(slice_df)
        if snapshot is None:
            continue
        entry_price = daily_df["Close"].iloc[t]
        exit_price = daily_df["Close"].iloc[t + horizon_days]
        fwd_return_pct = float((exit_price / entry_price - 1) * 100)
        rows.append({"symbol": symbol, "date": daily_df.index[t], **snapshot,
                     "forward_return_pct": fwd_return_pct})
    return pd.DataFrame(rows)


def run_backtest(symbols: list[str] | None = None, period: str = "2y",
                  horizon_days: int = 5, stride: int = 5, progress_callback=None) -> dict:
    symbols = symbols or config.WATCHLIST
    all_rows = []
    for i, sym in enumerate(symbols):
        if progress_callback:
            progress_callback((i + 1) / len(symbols), f"Backtesting {sym}...")
        df = backtest_symbol(sym, period=period, horizon_days=horizon_days, stride=stride)
        if not df.empty:
            all_rows.append(df)
    if not all_rows:
        return {"valid": False, "reason": "No usable historical data across symbols."}

    data = pd.concat(all_rows, ignore_index=True)
    score_types = ["combined", "technical", "quant", "regime", "risk_quality"]
    summary = {score_type: _evaluate_score(data, score_type) for score_type in score_types}
    return {"valid": True, "raw_data": data, "summary": summary,
            "n_observations": len(data), "symbols_covered": data["symbol"].nunique(),
            "horizon_days": horizon_days, "period": period}


def _evaluate_score(data: pd.DataFrame, score_col: str) -> dict:
    d = data[[score_col, "forward_return_pct"]].dropna()
    if len(d) < 20:
        return {"valid": False, "reason": "insufficient observations"}

    if d[score_col].nunique() < 2:
        return {"valid": False, "reason": "score has too little variance to bucket"}

    ic, ic_pvalue = spearmanr(d[score_col], d["forward_return_pct"])
    try:
        d = d.copy()
        d["quartile"] = pd.qcut(d[score_col], 4, labels=["Q1 (low)", "Q2", "Q3", "Q4 (high)"], duplicates="drop")
    except ValueError:
        return {"valid": False, "reason": "score has too little variance to bucket"}

    bucket_stats = d.groupby("quartile", observed=True)["forward_return_pct"].agg(
        win_rate_pct=lambda x: float((x > 0).mean() * 100), avg_return_pct="mean", n="count").round(2)

    q4_minus_q1 = None
    if "Q4 (high)" in bucket_stats.index and "Q1 (low)" in bucket_stats.index:
        q4_minus_q1 = round(
            bucket_stats.loc["Q4 (high)", "avg_return_pct"] - bucket_stats.loc["Q1 (low)", "avg_return_pct"], 2)

    return {"valid": True, "information_coefficient": round(float(ic), 3),
            "ic_pvalue": round(float(ic_pvalue), 4), "ic_significant": bool(ic_pvalue < 0.05),
            "quartile_breakdown": bucket_stats.reset_index().to_dict("records"),
            "top_minus_bottom_quartile_spread_pct": q4_minus_q1, "n_observations": len(d)}


def verdict(summary: dict) -> str:
    combined_ic = summary.get("combined", {}).get("information_coefficient")
    if combined_ic is None:
        return "Not enough data to draw a conclusion yet -- widen the backtest period or lower the stride."
    individual_ics = {k: v.get("information_coefficient") for k, v in summary.items()
                       if k != "combined" and v.get("valid") and v.get("information_coefficient") is not None}
    if not individual_ics:
        return "Combined score computed, but individual signals had insufficient data to compare against."
    best_name = max(individual_ics, key=lambda k: individual_ics[k])
    best_ic = individual_ics[best_name]
    if combined_ic > best_ic:
        return (f"The COMBINED Decision Agent score (IC={combined_ic:.3f}) outperformed the best "
                f"single signal ('{best_name}', IC={best_ic:.3f}) -- combining signals is adding real value.")
    else:
        return (f"The combined score (IC={combined_ic:.3f}) did NOT beat the best single signal "
                f"('{best_name}', IC={best_ic:.3f}) over this sample. Consider re-tuning "
                f"config.DECISION_WEIGHTS toward '{best_name}'.")
