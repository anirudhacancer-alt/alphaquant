"""
nse_bhavcopy.py
------------------
Downloads NSE's official daily "Securities Bhavcopy with Delivery" file
(sec_bhavdata_full) -- a free, public CSV covering EVERY listed NSE equity
(~2,000 symbols) with OHLC, volume, and delivery data -- and uses several
days of it to build a genuine full-market "liquid universe": every NSE
stock whose average daily traded value clears a configurable liquidity
floor, computed from real historical volume data rather than a hand-picked
list of 20 names.

*** THE HONEST LIMITATION, STATED UP FRONT ***
Bhavcopy is fundamentally END-OF-DAY data. NSE does not publish today's
bhavcopy until AFTER the market closes (~5:30-6:00 PM IST) -- there is no
free live/intraday bulk feed from NSE or anyone else. This means bhavcopy
by itself can answer "which stocks were unusually active TODAY" only
after the close, or "which stocks are historically liquid enough to
matter" using data through yesterday.

For LIVE, during-market-hours scanning of this large universe, this file
only handles the "which several hundred stocks are worth checking, and
what's their normal volume" part. Getting each of those stocks' actual
LIVE quote still requires a live data source -- which is where
data_utils.py's bulk-quote functions come in (Upstox supports up to 500
instruments per API call, making a few-hundred-stock live scan practical;
yfinance is used as a slower, capped fallback when Upstox isn't
connected). See market_scanner.py for how these two pieces combine.

Source: NSE's own public archive, no login/API key required --
https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv
"""
from __future__ import annotations
import datetime as dt
import io
import numpy as np
import pandas as pd
import requests
import streamlit as st
import config

BHAVCOPY_URL_TEMPLATE = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv"

# NSE's archive server blocks requests without a browser-like User-Agent
# (returns 403 to bare `requests` calls with no headers) -- this is a
# public-facing static file server, not an authenticated API, so no
# credentials are needed, just a normal-looking request.
_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/csv,*/*",
}

# Columns as published by NSE's sec_bhavdata_full file (stable format for
# years). We only need a handful of these; parsing is defensive (uses
# .get()-style access via reindex) so a minor NSE column-order change
# doesn't break everything.
_EXPECTED_COLUMNS = [
    "SYMBOL", "SERIES", "DATE1", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE",
    "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "AVG_PRICE", "TTL_TRD_QNTY",
    "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER",
]


def _format_date_for_url(date: dt.date) -> str:
    return date.strftime("%d%m%Y")


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def fetch_bhavcopy_for_date(date: dt.date) -> pd.DataFrame | None:
    """Downloads and parses ONE day's full-market bhavcopy. Returns None
    (not an empty DataFrame) if that date has no published file -- this
    is the EXPECTED, normal case for weekends/exchange holidays, not an
    error, so callers should treat None as "skip this date and try the
    previous one" rather than a failure.

    Cached for 12h: a given past date's bhavcopy never changes once
    published, so there's no reason to re-download it repeatedly within
    a session."""
    date_str = _format_date_for_url(date)
    url = BHAVCOPY_URL_TEMPLATE.format(date_str=date_str)
    try:
        resp = requests.get(url, headers=_REQUEST_HEADERS, timeout=15)
        if resp.status_code != 200 or not resp.content:
            return None
        df = pd.read_csv(io.BytesIO(resp.content))
        df.columns = [c.strip() for c in df.columns]
        # Defensive: only proceed if this actually looks like a bhavcopy
        # file (guards against NSE serving an HTML error/redirect page
        # with a 200 status, which `pd.read_csv` would otherwise choke on
        # unpredictably rather than failing cleanly).
        if "SYMBOL" not in df.columns or "SERIES" not in df.columns:
            return None
        # Equity series only ("EQ") -- excludes SME, bonds, preference
        # shares, etc. that share the same bhavcopy file.
        df = df[df["SERIES"].astype(str).str.strip() == "EQ"].copy()
        if df.empty:
            return None
        df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
        for col in ["CLOSE_PRICE", "TTL_TRD_QNTY", "TURNOVER_LACS"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["bhavcopy_date"] = date
        return df
    except Exception:
        return None


def fetch_bhavcopy_history(lookback_trading_days: int = config.BHAVCOPY_LOOKBACK_DAYS,
                            max_calendar_days_back: int = 45) -> pd.DataFrame:
    """Walks backward from today collecting valid bhavcopy days until
    `lookback_trading_days` distinct trading days are gathered, silently
    skipping weekends/holidays (a missing file for a given date is the
    normal case, not an error -- see fetch_bhavcopy_for_date). Gives up
    after `max_calendar_days_back` calendar days to avoid an unbounded
    loop if NSE's archive is unreachable entirely (e.g. this sandboxed
    environment has no internet access to nseindia.com -- verified during
    testing -- so this function correctly returns an empty DataFrame here,
    and callers fall back to config.FALLBACK_WATCHLIST)."""
    collected = []
    today = dt.datetime.now().date()
    calendar_days_checked = 0
    current_date = today

    while len(collected) < lookback_trading_days and calendar_days_checked < max_calendar_days_back:
        day_df = fetch_bhavcopy_for_date(current_date)
        if day_df is not None:
            collected.append(day_df)
        current_date -= dt.timedelta(days=1)
        calendar_days_checked += 1

    if not collected:
        return pd.DataFrame()
    return pd.concat(collected, ignore_index=True)


def build_liquid_universe(min_avg_daily_value_cr: float = config.BHAVCOPY_MIN_AVG_DAILY_VALUE_CR,
                           lookback_trading_days: int = config.BHAVCOPY_LOOKBACK_DAYS,
                           max_universe_size: int | None = None) -> pd.DataFrame:
    """THE core function: builds a genuine full-market liquid universe
    from real historical NSE data, replacing a hand-picked watchlist.

    For every NSE equity symbol appearing in the last `lookback_trading_days`
    of bhavcopy, computes:
      - avg_daily_volume: mean traded quantity (shares/day)
      - avg_daily_value_cr: mean traded value in INR crore/day (a
        price-independent liquidity measure -- a Rs.50 stock trading 10x
        the volume of a Rs.500 stock may have similar real liquidity, so
        turnover value is a fairer cross-stock comparison than raw share
        volume alone)
      - last_close: most recent close price (for reference/display)

    Filters to symbols clearing `min_avg_daily_value_cr`, sorts by
    liquidity descending, and optionally caps the result to
    `max_universe_size` (used by market_scanner.py to keep live-quote
    fetch counts practical when Upstox's bulk API isn't available).

    Returns an empty DataFrame if bhavcopy couldn't be fetched at all
    (e.g. no internet access, or NSE's archive is temporarily down) --
    callers must handle this by falling back to config.FALLBACK_WATCHLIST.
    """
    history = fetch_bhavcopy_history(lookback_trading_days=lookback_trading_days)
    if history.empty:
        return pd.DataFrame()

    grouped = history.groupby("SYMBOL").agg(
        avg_daily_volume=("TTL_TRD_QNTY", "mean"),
        avg_daily_turnover_lacs=("TURNOVER_LACS", "mean"),
        last_close=("CLOSE_PRICE", "last"),
        trading_days_observed=("bhavcopy_date", "nunique"),
    ).reset_index()

    # TURNOVER_LACS is in INR lakhs (1 lakh = 100,000); convert to crore
    # (1 crore = 100 lakh = 10,000,000) for the more standard liquidity unit.
    grouped["avg_daily_value_cr"] = grouped["avg_daily_turnover_lacs"] / 100.0

    liquid = grouped[grouped["avg_daily_value_cr"] >= min_avg_daily_value_cr].copy()
    liquid = liquid.sort_values("avg_daily_value_cr", ascending=False).reset_index(drop=True)

    if max_universe_size is not None and len(liquid) > max_universe_size:
        liquid = liquid.head(max_universe_size).reset_index(drop=True)

    # Append ".NS" to match the yfinance/rest-of-app symbol convention.
    liquid["yf_symbol"] = liquid["SYMBOL"] + ".NS"
    return liquid[["SYMBOL", "yf_symbol", "avg_daily_volume", "avg_daily_value_cr",
                    "last_close", "trading_days_observed"]]


def latest_bhavcopy_scan(min_avg_daily_value_cr: float = config.BHAVCOPY_MIN_AVG_DAILY_VALUE_CR,
                          lookback_trading_days: int = config.BHAVCOPY_LOOKBACK_DAYS,
                          rel_volume_threshold: float = config.REL_VOLUME_THRESHOLD,
                          price_move_threshold_pct: float = config.PRICE_MOVE_THRESHOLD_PCT) -> pd.DataFrame:
    """*** END-OF-DAY FULL-MARKET SCAN -- needs ZERO live API calls ***
    Since bhavcopy already contains the most recent trading day's actual
    volume and close-vs-previous-close move for EVERY NSE equity, this
    function can flag every single relative-volume/price-move outlier
    across the entire market using cached bhavcopy data alone -- no live
    quotes needed at all. This is strictly more complete than the live
    intraday scan (which is capped by live-API practicalities) and works
    any time, including after market close or on weekends, for reviewing
    "what happened today" or prepping for the next session.

    The most recent bhavcopy date's data serves as "today," and the prior
    `lookback_trading_days` (excluding the most recent day) establishes
    each symbol's normal volume baseline -- exactly mirroring the live
    scanner's relative-volume logic, just entirely from historical files."""
    history = fetch_bhavcopy_history(lookback_trading_days=lookback_trading_days + 1)
    if history.empty:
        return pd.DataFrame()

    dates_sorted = sorted(history["bhavcopy_date"].unique())
    if len(dates_sorted) < 2:
        return pd.DataFrame()

    latest_date = dates_sorted[-1]
    baseline_dates = dates_sorted[:-1]

    latest_day = history[history["bhavcopy_date"] == latest_date].set_index("SYMBOL")
    baseline = history[history["bhavcopy_date"].isin(baseline_dates)]
    baseline_avg_vol = baseline.groupby("SYMBOL")["TTL_TRD_QNTY"].mean()
    baseline_avg_value_cr = baseline.groupby("SYMBOL")["TURNOVER_LACS"].mean() / 100.0

    rows = []
    for symbol, row in latest_day.iterrows():
        avg_vol = baseline_avg_vol.get(symbol, np.nan)
        avg_value_cr = baseline_avg_value_cr.get(symbol, np.nan)
        if pd.isna(avg_value_cr) or avg_value_cr < min_avg_daily_value_cr:
            continue  # apply the same liquidity floor as the live universe

        today_vol = row["TTL_TRD_QNTY"]
        prev_close = row.get("PREV_CLOSE", np.nan)
        close = row["CLOSE_PRICE"]
        pct_move = (close - prev_close) / prev_close * 100 if prev_close and prev_close > 0 else 0.0
        rel_volume = (today_vol / avg_vol) if avg_vol and avg_vol > 0 else 0.0

        qualifies = (rel_volume >= rel_volume_threshold or abs(pct_move) >= price_move_threshold_pct)
        rows.append({
            "symbol": f"{symbol}.NS", "date": latest_date, "close": round(float(close), 2),
            "pct_move": round(float(pct_move), 2), "volume": int(today_vol) if pd.notna(today_vol) else 0,
            "avg_daily_volume": int(avg_vol) if pd.notna(avg_vol) else 0,
            "rel_volume": round(float(rel_volume), 2), "qualifies": qualifies,
            "avg_daily_value_cr": round(float(avg_value_cr), 2),
        })

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows).sort_values("rel_volume", ascending=False).reset_index(drop=True)
    return result
