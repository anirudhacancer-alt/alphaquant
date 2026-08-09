# AlphaQuant — Premium Web Edition

A personal, non-professional intraday research tool for the **entire
liquid NSE market** (not a hand-picked watchlist), running as a polished
web app — **no local installs, every execution happens in the browser**
once deployed (see `DEPLOY.md`).

> Not a professional trading system. Not investment advice. A rules-based
> research assistant that surfaces candidates with full transparency on
> *why*, with hard-coded risk management so no single bad call causes
> serious damage.

## 🇮🇳 Full NSE market coverage (NEW)

Previously scanned only 20 hand-picked large-caps. Now scans the **entire
liquid NSE market** via `nse_bhavcopy.py`, which pulls NSE's own free,
public daily archive (`sec_bhavdata_full` — no login/API key needed) to
discover every stock whose real historical trading data clears a
configurable liquidity floor (default Rs.5cr/day average traded value —
typically several hundred stocks).

**Two scan modes** (sidebar toggle):
- **🟢 Live** — bhavcopy discovers the universe, then fetches LIVE quotes
  via Upstox's bulk API (500 instruments/call) when connected, or a capped
  yfinance batch fallback otherwise.
- **🌙 End-of-day** — zero live API calls, covers the full universe
  uncapped, works any time (nights/weekends), reflects the last completed
  session.

**Honest limitation**: bhavcopy is end-of-day data (NSE, like everyone
else, doesn't publish free live bulk data) — it tells you *which* stocks
matter and their normal volume, not today's live number. That part still
needs Upstox (recommended) or a capped free fallback. See `DEPLOY.md`
Step 5 for full detail.

If bhavcopy is ever unreachable, the app automatically falls back to the
original 20-stock `FALLBACK_WATCHLIST` — it never breaks.

## Premium UI

Dark glassmorphic "trading terminal" design (`theme.py` + `charts.py`):
candlestick charts with entry/stop/target overlays, a Monte Carlo fan
chart, radial confidence gauge, 5-axis component radar, sentiment donut,
and a relative-volume bar chart — all sharing one consistent violet→cyan
brand gradient.

## Feature summary

1. **Full-market scanning** (`nse_bhavcopy.py`) — see above.
2. **Decision Agent backtesting harness** (`backtest/backtest_engine.py`)
   — walk-forward validation (Information Coefficient + quartile
   breakdown) of whether the combined score beats any single signal alone.
3. **HMM regime detection** (`agents/regime_detection.py`) — multi-restart
   fitting + a formal BIC gate against a trivial 1-state baseline, so it
   reports honest "unknown" rather than false confidence on data with no
   real regime structure.
4. **VADER news sentiment** (`agents/news_macro.py`) — word-boundary
   symbol matching (fixes short-root false positives like "LT" matching
   "fault"), layered on keyword impact tagging.
5. **Semi-automatic pairs trading** (`agents/pairs_trading.py`) — manual +
   auto-discovered correlated pairs, consistent lookback windows for
   correlation and z-score.
6. **Live Upstox data** (`upstox_auth.py` + `data_utils.py`) — OAuth 2.0
   login, live quotes/candles, bulk quote support (500 instruments/call),
   auto-falls-back to free yfinance. Tokens expire daily at 3:30 AM IST.
7. **Google Sheets run-log persistence** (`gsheets_sync.py`) — survives
   Streamlit Cloud redeploys; NaN-safe JSON serialization so rejected-
   candidate rows (which have missing numeric fields) always sync
   correctly.
8. **Installable Android app** (`mobile_app/` + `APK_GUIDE.md`) — Flutter
   WebView wrapper, built entirely by GitHub Actions.

## Project structure

```
alphaquant_web/
  app.py                    -- Streamlit web app (premium UI, main entry point)
  theme.py / charts.py       -- design system + Plotly chart builders
  orchestrator.py           -- runs the full pipeline end to end (CLI or web)
  config.py                 -- every threshold/list/parameter (no secrets)
  nse_bhavcopy.py             -- NEW: full-market universe discovery via NSE's free archive
  data_utils.py               -- data-fetching seam (yfinance + Upstox, incl. bulk quotes)
  upstox_auth.py              -- Upstox OAuth 2.0 login + token expiry handling
  gsheets_sync.py              -- optional Google Sheets mirror for run-log persistence
  reporting.py                -- run_log.csv handling (append-only, integrity-checked)
  agents/
    market_scanner.py        -- NOW: bhavcopy universe + live/EOD scan modes
    technical_analysis.py    -- RSI, MACD, VWAP, Bollinger, ATR, ADX, support/resistance
    quant_research.py        -- honest pattern backtests (win rate + sample size)
    news_macro.py             -- RSS feeds + VADER sentiment + keyword impact tagging
    risk_manager.py           -- 1% rule, ATR stops, RR>=1.5 floor, Kelly sizing
    regime_detection.py       -- HMM bull/choppy/bear classification (BIC-gated)
    monte_carlo.py            -- GBM path simulation, target-hit probabilities
    pairs_trading.py          -- correlation-based pair discovery + divergence signals
    decision_agent.py         -- combines everything into one transparent score
  backtest/
    backtest_engine.py        -- validates the Decision Agent's weighting formula
  mobile_app/                 -- Flutter WebView Android wrapper (see APK_GUIDE.md)
  .github/workflows/
    build-apk.yml             -- GitHub Actions: builds the APK in the cloud
  DEPLOY.md                   -- step-by-step, zero-install deployment guide
  APK_GUIDE.md                 -- step-by-step, zero-install Android app guide
```

## Local run (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```
Use Python 3.11 or 3.12 locally if you do this (not 3.14 — see DEPLOY.md).

## Honest, ongoing limitations

- Bhavcopy is end-of-day; live full-market scanning still needs Upstox
  (recommended) or a capped yfinance fallback (~60 symbols).
- Quant Research patterns are scoped to whatever history yfinance returns.
- Monte Carlo uses GBM (normal returns, constant volatility).
- News sentiment (VADER) is general-purpose, not finance-domain-tuned.
- No broker execution/auto-trading — by design, this is research-only.
- Upstox access tokens expire daily at 3:30 AM IST — no workaround.
- HMM regime detection honestly reports "unknown" when there's no
  statistically significant evidence of distinct market regimes, rather
  than forcing a confident-sounding but unjustified label.
