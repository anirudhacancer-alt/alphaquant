"""
orchestrator.py
-----------------
Runs the full pipeline end to end. `run_pipeline(...)` is called
identically from CLI or from app.py.

scan_mode:
  "live" -- bhavcopy-derived (or fallback) universe + LIVE bulk quotes.
            Works during market hours; universe size capped when running
            on the free yfinance fallback (see config.MAX_LIVE_SCAN_
            UNIVERSE_SIZE_YFINANCE) since yfinance has no true bulk quote
            endpoint, uncapped (up to a sane ceiling) when Upstox is
            connected (500 instruments/API call).
  "eod"  -- nse_bhavcopy's own most-recent-session scan. ZERO live API
            calls, covers the FULL liquid universe uncapped, works any
            time (including nights/weekends), but only reflects the last
            completed trading session, not the current live price.
"""
from __future__ import annotations
import pandas as pd
import config
import data_utils
import reporting
from agents import (market_scanner, technical_analysis, quant_research,
                     regime_detection, news_macro, risk_manager,
                     decision_agent, monte_carlo, pairs_trading)


def run_pipeline(capital: float = config.DEFAULT_CAPITAL,
                  top_n: int = config.DEFAULT_TOP_N,
                  use_pairs: bool = False,
                  scan_mode: str = "live",
                  progress_callback=None) -> dict:

    def _tick(frac, msg):
        if progress_callback:
            progress_callback(frac, msg)

    _tick(0.02, "Scanning watchlist...")
    if scan_mode == "eod":
        scanned = market_scanner.scan_eod()
    else:
        scanned = market_scanner.scan(progress_callback=lambda f, m: _tick(0.02 + f * 0.18, m))
    shortlisted = market_scanner.shortlist(scanned) if not scanned.empty else []

    _tick(0.22, "Fetching news & macro headlines...")
    headlines = news_macro.fetch_headlines()
    macro = news_macro.macro_summary(headlines)

    decisions = []
    n = max(len(shortlisted), 1)
    for i, symbol in enumerate(shortlisted):
        _tick(0.25 + 0.55 * (i / n), f"Analyzing {symbol}...")
        daily_df = data_utils.fetch_daily(symbol, period="1y")
        intraday_df = data_utils.fetch_intraday(symbol)
        avg_vol = data_utils.avg_daily_volume(symbol)

        ta = technical_analysis.analyze(symbol, daily_df, intraday_df)
        quant = quant_research.research(symbol, daily_df)
        regime = regime_detection.detect_regime(daily_df)
        news_score = news_macro.score_for_symbol(symbol, headlines)

        if not ta.get("valid"):
            decisions.append({"symbol": symbol, "decision": "REJECTED",
                              "reject_reason": ta.get("reason"), "confidence_score": None})
            continue

        risk = risk_manager.evaluate(
            symbol=symbol, last_price=ta["last_price"], atr_val=ta["atr"],
            avg_daily_volume=avg_vol, capital=capital, direction="long",
            quant_win_rate=quant.get("rsi_oversold_bounce", {}).get("win_rate") if quant.get("valid") else None,
            quant_avg_return_pct=quant.get("rsi_oversold_bounce", {}).get("avg_return_pct") if quant.get("valid") else None,
        )

        decision = decision_agent.decide(symbol, ta, quant, regime, news_score, risk)
        decision["daily_df"] = daily_df
        if decision["decision"] == "APPROVED":
            daily_returns = daily_df["Close"].pct_change().dropna()
            mc = monte_carlo.simulate(entry=decision["entry"], stop=decision["stop"],
                                       targets=decision["targets"], daily_returns=daily_returns, direction="long")
            decision["monte_carlo"] = mc
        decisions.append(decision)

    _tick(0.85, "Ranking and building report...")
    decisions_sorted = sorted(decisions, key=lambda d: -(d["confidence_score"] or -1))
    top_decisions = [d for d in decisions_sorted if d["decision"] == "APPROVED"][:top_n] + \
                    [d for d in decisions_sorted if d["decision"] == "REJECTED"]

    report = reporting.build_report(top_decisions, shortlisted)

    pairs_df = pd.DataFrame()
    if use_pairs:
        _tick(0.93, "Scanning pairs trading candidates...")
        pairs_df = pairs_trading.scan_pairs()

    _tick(1.0, "Done.")
    return {"scanned": scanned, "shortlisted": shortlisted, "macro_summary": macro,
            "headlines": headlines, "report": report, "pairs": pairs_df, "capital": capital,
            "scan_mode": scan_mode}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaQuant orchestrator (CLI mode)")
    parser.add_argument("--capital", type=float, default=config.DEFAULT_CAPITAL)
    parser.add_argument("--top", type=int, default=config.DEFAULT_TOP_N)
    parser.add_argument("--pairs", action="store_true")
    parser.add_argument("--scan-mode", choices=["live", "eod"], default="live")
    args = parser.parse_args()

    def _print_progress(frac, msg):
        print(f"[{frac*100:5.1f}%] {msg}")

    result = run_pipeline(capital=args.capital, top_n=args.top, use_pairs=args.pairs,
                           scan_mode=args.scan_mode, progress_callback=_print_progress)
    rep = result["report"]
    print(f"\nScanned {len(result['scanned'])} symbols ({result['scan_mode']} mode)")
    print("\n=== APPROVED ===")
    for d in rep["approved"]:
        print(f"{d['symbol']}: confidence={d['confidence_score']} entry={d['entry']} "
              f"stop={d['stop']} targets={d['targets']}")
    print("\n=== REJECTED ===")
    for d in rep["rejected"]:
        print(f"{d['symbol']}: {d.get('reject_reason')}")
    print(f"\n[NEW] this run: {rep['new_symbols']}")
    if result["pairs"] is not None and not result["pairs"].empty:
        print("\n=== PAIRS ===")
        print(result["pairs"].to_string(index=False))
