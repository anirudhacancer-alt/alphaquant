"""
agents/market_scanner.py
-------------------------
Shortlists candidates for deeper analysis. Now covers the FULL NSE market
(not a hand-picked 20-stock list) by combining two pieces:

  1. nse_bhavcopy.py discovers WHICH stocks are worth scanning -- every
     NSE equity clearing a real liquidity floor, computed from actual
     historical trading data via NSE's own free daily bhavcopy archive
     (typically several hundred symbols, not 20).
  2. data_utils.fetch_live_quotes_bulk() fetches LIVE quotes for that
     whole universe efficiently -- via Upstox's bulk API (500
     instruments/call) when connected, or a batched yfinance fallback
     (capped smaller, since yfinance has no true bulk endpoint) otherwise.

*** HONEST LIMITATION, STATED PLAINLY ***
Bhavcopy is END-OF-DAY data (see nse_bhavcopy.py's docstring) -- it tells
us WHICH stocks are liquid and what their NORMAL volume looks like, but
not today's live number. That still requires a live data source. Two
scan modes are exposed for this reason:
  - "live": uses the bhavcopy-derived universe + live bulk quotes (works
    during market hours; universe size is capped when running on the
    free yfinance fallback -- see config.MAX_LIVE_SCAN_UNIVERSE_SIZE_*).
  - "eod": uses nse_bhavcopy.latest_bhavcopy_scan() directly -- ZERO live
    API calls, genuinely covers the entire liquid universe uncapped, but
    only reflects the most recently completed trading session (works any
    time, including nights/weekends, for "what happened today" or
    next-session prep).
"""
from __future__ import annotations
import pandas as pd
import config
import data_utils
import nse_bhavcopy
import upstox_auth


def get_scan_universe(max_size: int | None = None) -> tuple[list[str], str]:
    """Returns (symbol_list, source_description). Tries the bhavcopy-
    derived liquid universe first; falls back to the hand-picked
    FALLBACK_WATCHLIST if bhavcopy is unreachable (e.g. no internet
    access to NSE, or NSE's archive is temporarily down) so the app never
    breaks even when full-market discovery isn't available."""
    if config.UNIVERSE_MODE == "bhavcopy":
        universe_df = nse_bhavcopy.build_liquid_universe(max_universe_size=max_size)
        if not universe_df.empty:
            return universe_df["yf_symbol"].tolist(), \
                f"NSE bhavcopy ({len(universe_df)} liquid stocks, {config.BHAVCOPY_LOOKBACK_DAYS}d avg value >= Rs.{config.BHAVCOPY_MIN_AVG_DAILY_VALUE_CR}cr)"

    # Fallback: bhavcopy unreachable, or UNIVERSE_MODE explicitly "watchlist"
    return list(config.FALLBACK_WATCHLIST), "fallback watchlist (bhavcopy unavailable)"


def scan(progress_callback=None) -> pd.DataFrame:
    """LIVE scan: bhavcopy-derived universe (or fallback) + live bulk
    quotes. This is what runs during market hours from the main
    'Run Full Pipeline' button."""
    upstox_connected = config.USE_UPSTOX and upstox_auth.get_valid_token() is not None
    max_size = (config.MAX_LIVE_SCAN_UNIVERSE_SIZE_UPSTOX if upstox_connected
                else config.MAX_LIVE_SCAN_UNIVERSE_SIZE_YFINANCE)

    symbols, source_desc = get_scan_universe(max_size=max_size)

    if progress_callback:
        progress_callback(0.05, f"Universe: {source_desc}")

    quotes = data_utils.fetch_live_quotes_bulk(symbols, progress_callback=progress_callback)

    rows = []
    for symbol in symbols:
        quote = quotes.get(symbol)
        if quote is None:
            continue
        avg_vol = data_utils.avg_daily_volume(symbol)
        rel_volume = (quote["volume"] / avg_vol) if avg_vol else 0.0
        pct_move = quote["pct_move"]
        qualifies = (rel_volume >= config.REL_VOLUME_THRESHOLD or
                     abs(pct_move) >= config.PRICE_MOVE_THRESHOLD_PCT)
        rows.append({"symbol": symbol, "price": round(quote["price"], 2), "pct_move": round(pct_move, 2),
                     "volume": int(quote["volume"]) if quote["volume"] == quote["volume"] else 0,
                     "avg_daily_volume": int(avg_vol), "rel_volume": round(rel_volume, 2),
                     "qualifies": qualifies, "data_source": quote["source"]})

    if not rows:
        return pd.DataFrame(columns=["symbol", "price", "pct_move", "volume", "avg_daily_volume",
                                      "rel_volume", "qualifies", "data_source"])
    return pd.DataFrame(rows).sort_values("rel_volume", ascending=False).reset_index(drop=True)


def scan_eod() -> pd.DataFrame:
    """END-OF-DAY scan: uses ONLY nse_bhavcopy's cached historical data --
    zero live API calls, covers the FULL liquid universe uncapped, and
    works any time (including nights/weekends). Reflects the most
    recently completed trading session, not the live/current price."""
    result = nse_bhavcopy.latest_bhavcopy_scan()
    if result.empty:
        return pd.DataFrame(columns=["symbol", "date", "close", "pct_move", "volume",
                                      "avg_daily_volume", "rel_volume", "qualifies", "avg_daily_value_cr"])
    return result


def shortlist(scanned: pd.DataFrame) -> list[str]:
    return scanned.loc[scanned["qualifies"], "symbol"].tolist()
