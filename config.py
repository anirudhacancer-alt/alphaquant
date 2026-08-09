"""
config.py
---------
Single source of truth for every threshold, list, and parameter used across
AlphaQuant. Nothing in the agents should hard-code a number that belongs here.

SECURITY NOTE: this file intentionally contains NO real API keys/secrets.
Upstox credentials and Google service-account keys both live in Streamlit
Cloud's "Secrets" panel only (see DEPLOY.md) -- never paste real credentials
directly into this file, since it's meant to be committed to GitHub.
"""

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------
APP_NAME = "AlphaQuant"
APP_TAGLINE = "AI-Assisted Intraday Research for NSE"

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
USE_UPSTOX = True
USE_KITE = False

# IMPORTANT: after you deploy this app (see DEPLOY.md), update this constant
# to your actual deployed Streamlit URL, then redeploy. This value is used
# as the Upstox OAuth redirect_uri, and it MUST exactly match what you
# register in the Upstox Developer Console.
APP_BASE_URL = "https://your-app-name.streamlit.app"

# ---------------------------------------------------------------------------
# Run log persistence
# ---------------------------------------------------------------------------
RUN_LOG_BACKEND = "gsheets"   # "csv" or "gsheets" -- falls back to csv automatically
GSHEETS_SPREADSHEET_NAME = "AlphaQuant Run Log"
GSHEETS_WORKSHEET_NAME = "run_log"

# ---------------------------------------------------------------------------
# Scan universe -- FULL MARKET via NSE bhavcopy (see nse_bhavcopy.py)
# ---------------------------------------------------------------------------
# "bhavcopy" = genuine full-market coverage: every NSE equity symbol whose
#              real historical trading data clears the liquidity floor
#              below, computed fresh from NSE's own public daily archive.
# "watchlist" = the original hand-picked FALLBACK_WATCHLIST only (useful
#              for fast local testing, or if bhavcopy is ever unreachable).
UNIVERSE_MODE = "bhavcopy"

# Liquidity floor for the bhavcopy-derived universe, in INR CRORE of
# average daily traded VALUE (price x volume) -- a fairer cross-stock
# liquidity measure than raw share volume, since a low-price stock
# trading huge share counts and a high-price stock trading fewer shares
# can represent similar real liquidity. Rs.5 crore/day is a reasonably
# inclusive floor that still excludes genuinely illiquid names.
BHAVCOPY_MIN_AVG_DAILY_VALUE_CR = 5.0
BHAVCOPY_LOOKBACK_DAYS = 20   # trading days used to compute each symbol's average volume/value

# Safety cap on how many symbols get LIVE quote calls during market hours.
# Bhavcopy can discover several hundred liquid stocks -- fetching a LIVE
# quote for all of them is cheap via Upstox's bulk API (500
# instruments/call) but expensive one-by-one via yfinance. This cap only
# applies when Upstox is NOT connected (free yfinance fallback); with
# Upstox connected, the full bhavcopy-derived universe is scanned live,
# uncapped (subject to MAX_LIVE_SCAN_UNIVERSE_SIZE_UPSTOX below as a
# sane outer bound).
MAX_LIVE_SCAN_UNIVERSE_SIZE_YFINANCE = 60
MAX_LIVE_SCAN_UNIVERSE_SIZE_UPSTOX = 1000

# Original hand-picked list -- now used ONLY as an emergency fallback if
# NSE's bhavcopy archive is ever completely unreachable (e.g. temporary
# outage, or UNIVERSE_MODE="watchlist" is explicitly selected for testing).
FALLBACK_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS", "SBIN.NS",
    "AXISBANK.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "MARUTI.NS", "TITAN.NS",
    "SUNPHARMA.NS", "TATAMOTORS.NS", "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS",
]
# Backward-compatible alias -- other modules (pairs_trading discovery,
# backtest defaults, etc.) reference config.WATCHLIST as a general-purpose
# small representative list; keep it pointing at the fallback list so
# those usages remain fast and predictable rather than scanning hundreds
# of symbols for things like the backtest harness's default demo run.
WATCHLIST = FALLBACK_WATCHLIST

# ---------------------------------------------------------------------------
# Market Scanner thresholds
# ---------------------------------------------------------------------------
REL_VOLUME_THRESHOLD = 1.5
PRICE_MOVE_THRESHOLD_PCT = 1.0

# ---------------------------------------------------------------------------
# Technical Analysis
# ---------------------------------------------------------------------------
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BOLLINGER_PERIOD, BOLLINGER_STD = 20, 2
ATR_PERIOD = 14
ADX_PERIOD = 14

# ---------------------------------------------------------------------------
# Risk Manager (non-negotiable, hard-coded)
# ---------------------------------------------------------------------------
MAX_RISK_PER_TRADE_PCT = 1.0
MIN_REWARD_RISK = 1.5
RR_TOLERANCE = 1e-6
MIN_AVG_DAILY_VOLUME = 500_000
TARGET_ATR_MULTIPLES = {"T1": 1.25, "T2": 2.00, "T3": 2.75}
STOP_ATR_MULTIPLE = 1.0

# ---------------------------------------------------------------------------
# Kelly Criterion sizing
# ---------------------------------------------------------------------------
KELLY_FRACTION_CAP = 0.5

# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------
MONTE_CARLO_PATHS = 2000
MONTE_CARLO_HORIZON_DAYS = 8

# ---------------------------------------------------------------------------
# Regime Detection (HMM)
# ---------------------------------------------------------------------------
HMM_N_STATES = 3
HMM_LOOKBACK_DAYS = 252

# ---------------------------------------------------------------------------
# Pairs Trading
# ---------------------------------------------------------------------------
PAIRS_CANDIDATES = [
    ("HDFCBANK.NS", "ICICIBANK.NS"),
    ("TCS.NS", "INFY.NS"),
    ("SUNPHARMA.NS", "TATAMOTORS.NS"),
]
PAIRS_AUTO_DISCOVER = True
PAIRS_MIN_CORRELATION = 0.80
PAIRS_ZSCORE_ENTRY = 2.0
PAIRS_LOOKBACK_DAYS = 90

# ---------------------------------------------------------------------------
# News & Macro
# ---------------------------------------------------------------------------
NEWS_RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.business-standard.com/rss/markets-106.rss",
]
NEWS_LOOKBACK_HOURS = 24
NEWS_HIGH_IMPACT_KEYWORDS = [
    "rbi", "rate cut", "rate hike", "inflation", "gdp", "fii", "dii",
    "war", "sanction", "crude oil", "budget", "sebi", "fed", "recession",
]
NEWS_MEDIUM_IMPACT_KEYWORDS = [
    "earnings", "results", "merger", "acquisition", "guidance", "upgrade",
    "downgrade", "stake sale", "ipo",
]

# ---------------------------------------------------------------------------
# Decision Agent -- weights are config-driven so backtest/backtest_engine.py
# can validate / tune them with real evidence instead of gut feel.
# ---------------------------------------------------------------------------
DECISION_WEIGHTS = {
    "technical": 0.30,
    "quant": 0.25,
    "regime": 0.15,
    "news": 0.10,
    "risk_quality": 0.20,
}

# ---------------------------------------------------------------------------
# Orchestrator defaults
# ---------------------------------------------------------------------------
DEFAULT_CAPITAL = 500_000
DEFAULT_TOP_N = 10

# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------
RUN_LOG_PATH = "data/run_log.csv"
BACKTEST_LOG_PATH = "data/backtest_results.csv"

# ---------------------------------------------------------------------------
# Upstox instrument master
# ---------------------------------------------------------------------------
UPSTOX_NSE_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

# Upstox bulk market-quote endpoints accept at most this many instrument
# keys per single API call (per Upstox's own documented limit) -- used to
# chunk large-universe live-quote requests into as few calls as possible.
UPSTOX_BULK_QUOTE_CHUNK_SIZE = 500
