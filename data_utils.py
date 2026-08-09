"""
data_utils.py
-------------
Single shared data-fetching seam. Priority per session: Upstox (if
connected) -> yfinance (free fallback) -> clearly-flagged synthetic data
(only if both real sources fail).

*** BULK QUOTE FUNCTIONS (added for full-market bhavcopy-driven scanning) ***
Scanning a genuine full-market liquid universe (potentially several
hundred symbols, via nse_bhavcopy.py) one-symbol-at-a-time would be slow
and rate-limit-prone. `fetch_live_quotes_bulk()` fetches many symbols per
API call: via Upstox's bulk quote endpoint (up to 500 instruments/call,
per Upstox's own documented limit) when connected, or via yfinance's
multi-ticker download (batched, since very large single yfinance requests
can themselves become unreliable) as the free-tier fallback.
"""
from __future__ import annotations
import gzip
import json
import numpy as np
import pandas as pd
import requests
import streamlit as st
import config
import upstox_auth

try:
    import yfinance as yf
except ImportError:
    yf = None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def _upstox_instrument_map() -> dict:
    try:
        resp = requests.get(config.UPSTOX_NSE_INSTRUMENTS_URL, timeout=20)
        resp.raise_for_status()
        raw = gzip.decompress(resp.content)
        records = json.loads(raw)
        return {r["trading_symbol"]: r["instrument_key"]
                for r in records if r.get("instrument_type") == "EQ"}
    except Exception:
        return {}


def _to_upstox_key(symbol: str) -> str | None:
    root = symbol.replace(".NS", "").replace(".BO", "")
    return _upstox_instrument_map().get(root)


def _upstox_headers(token: str) -> dict:
    return {"Accept": "application/json", "Authorization": f"Bearer {token}"}


@st.cache_data(ttl=60 * 5, show_spinner=False)
def fetch_daily(symbol: str, period: str = "1y") -> pd.DataFrame:
    if yf is None:
        return _synthetic_ohlcv(symbol, days=280)
    try:
        df = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return _synthetic_ohlcv(symbol, days=280)
        return _flatten_columns(df)
    except Exception:
        return _synthetic_ohlcv(symbol, days=280)


@st.cache_data(ttl=60 * 2, show_spinner=False)
def fetch_intraday(symbol: str, interval: str = "30m", period: str = "5d") -> pd.DataFrame:
    if config.USE_UPSTOX:
        token = upstox_auth.get_valid_token()
        if token:
            try:
                df = _upstox_intraday(symbol, interval, token)
                if df is not None and not df.empty:
                    df.attrs["is_daily_fallback"] = False
                    df.attrs["source"] = "upstox_live"
                    return df
            except Exception:
                pass

    if yf is None:
        return _synthetic_ohlcv(symbol, days=5, intraday=True)
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df is None or df.empty:
            daily = fetch_daily(symbol, period="5d")
            daily.attrs["is_daily_fallback"] = True
            return daily
        df = _flatten_columns(df)
        df.attrs["is_daily_fallback"] = False
        df.attrs["source"] = "yfinance"
        return df
    except Exception:
        daily = fetch_daily(symbol, period="5d")
        daily.attrs["is_daily_fallback"] = True
        return daily


@st.cache_data(ttl=30, show_spinner=False)
def fetch_live_quote(symbol: str) -> dict:
    """Single-symbol live quote. Kept for callers that only need one
    symbol (e.g. re-checking a specific candidate); for scanning many
    symbols, use fetch_live_quotes_bulk() instead -- far fewer API calls."""
    if config.USE_UPSTOX:
        token = upstox_auth.get_valid_token()
        if token:
            try:
                return _upstox_quote(symbol, token)
            except Exception:
                pass

    if yf is None:
        return _synthetic_quote(symbol)
    try:
        t = yf.Ticker(symbol)
        fast = t.fast_info
        price = float(fast.get("lastPrice") or fast.get("last_price") or np.nan)
        volume = float(fast.get("lastVolume") or fast.get("last_volume") or np.nan)
        prev_close = float(fast.get("previousClose") or fast.get("previous_close") or np.nan)
        if np.isnan(price):
            raise ValueError("no live price")
        return {"symbol": symbol, "price": price, "volume": volume, "prev_close": prev_close,
                "pct_move": (price - prev_close) / prev_close * 100 if prev_close else 0.0,
                "source": "yfinance_live", "timestamp": pd.Timestamp.utcnow()}
    except Exception:
        return _synthetic_quote(symbol)


def fetch_live_quotes_bulk(symbols: list[str], progress_callback=None) -> dict[str, dict]:
    """Fetches live quotes for MANY symbols efficiently:
      - Upstox connected: batches instrument_keys into groups of
        config.UPSTOX_BULK_QUOTE_CHUNK_SIZE (500) and calls the bulk
        /market-quote/quotes endpoint once per batch -- e.g. 400 symbols
        needs just 1 API call, not 400.
      - Upstox not connected: falls back to yfinance's multi-ticker
        download, itself batched into smaller groups (yfinance's own
        multi-ticker requests can become unreliable at very large sizes),
        which is still dramatically fewer round-trips than one call per
        symbol.
      - Any symbol that fails to resolve/fetch in its batch falls back to
        a per-symbol synthetic quote (clearly flagged), so one bad symbol
        never breaks the whole batch.

    Returns {symbol: quote_dict} using the same quote_dict shape as
    fetch_live_quote()."""
    if config.USE_UPSTOX:
        token = upstox_auth.get_valid_token()
        if token:
            try:
                return _upstox_bulk_quotes(symbols, token, progress_callback)
            except Exception:
                pass  # fall through to yfinance batch below

    return _yfinance_bulk_quotes(symbols, progress_callback)


def avg_daily_volume(symbol: str, lookback: int = 20) -> float:
    df = fetch_daily(symbol, period="3mo")
    if df.empty or "Volume" not in df.columns:
        return 0.0
    return float(df["Volume"].tail(lookback).mean())


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


def _synthetic_ohlcv(symbol: str, days: int = 280, intraday: bool = False) -> pd.DataFrame:
    seed = abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)
    freq = "30min" if intraday else "B"
    periods = days * 13 if intraday else days
    idx = pd.date_range(end=pd.Timestamp.today(), periods=periods, freq=freq)
    ret = rng.normal(0.0003, 0.012, size=periods)
    price = 1000 * np.exp(np.cumsum(ret))
    high = price * (1 + rng.uniform(0, 0.008, periods))
    low = price * (1 - rng.uniform(0, 0.008, periods))
    openp = np.roll(price, 1)
    openp[0] = price[0]
    vol = rng.uniform(3e5, 3e6, periods)
    df = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": price, "Volume": vol}, index=idx)
    df.attrs["synthetic"] = True
    return df


def _synthetic_quote(symbol: str) -> dict:
    df = _synthetic_ohlcv(symbol, days=5)
    last, prev = df["Close"].iloc[-1], df["Close"].iloc[-2]
    return {"symbol": symbol, "price": float(last), "volume": float(df["Volume"].iloc[-1]),
            "prev_close": float(prev), "pct_move": float((last - prev) / prev * 100),
            "source": "synthetic_fallback", "timestamp": pd.Timestamp.utcnow()}


def _upstox_quote(symbol: str, token: str) -> dict:
    instrument_key = _to_upstox_key(symbol)
    if not instrument_key:
        raise ValueError(f"No Upstox instrument_key found for {symbol}")
    resp = requests.get("https://api.upstox.com/v2/market-quote/quotes",
                         headers=_upstox_headers(token), params={"instrument_key": instrument_key}, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    if not data:
        raise ValueError("Empty Upstox quote response")
    quote = next(iter(data.values()))
    last_price = float(quote["last_price"])
    prev_close = float(quote.get("ohlc", {}).get("close") or last_price)
    volume = float(quote.get("volume", 0))
    return {"symbol": symbol, "price": last_price, "volume": volume, "prev_close": prev_close,
            "pct_move": (last_price - prev_close) / prev_close * 100 if prev_close else 0.0,
            "source": "upstox_live", "timestamp": pd.Timestamp.utcnow()}


def _upstox_intraday(symbol: str, interval: str, token: str) -> pd.DataFrame:
    instrument_key = _to_upstox_key(symbol)
    if not instrument_key:
        raise ValueError(f"No Upstox instrument_key found for {symbol}")
    upstox_interval = "30minute" if "30" in interval else "1minute"
    url = f"https://api.upstox.com/v2/historical-candle/intraday/{instrument_key}/{upstox_interval}"
    resp = requests.get(url, headers=_upstox_headers(token), timeout=10)
    resp.raise_for_status()
    candles = resp.json().get("data", {}).get("candles", [])
    if not candles:
        raise ValueError("No intraday candles returned by Upstox")
    rows = list(reversed(candles))
    df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume", "OI"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df


def _upstox_bulk_quotes(symbols: list[str], token: str, progress_callback=None) -> dict[str, dict]:
    """Resolves each symbol to its Upstox instrument_key, chunks into
    groups of config.UPSTOX_BULK_QUOTE_CHUNK_SIZE (500, Upstox's own
    documented per-call limit for /market-quote/quotes), and issues one
    HTTP call per chunk instead of one per symbol -- e.g. a 400-symbol
    universe needs exactly 1 API call, not 400."""
    key_to_symbol = {}
    for sym in symbols:
        key = _to_upstox_key(sym)
        if key:
            key_to_symbol[key] = sym

    results: dict[str, dict] = {}
    keys = list(key_to_symbol.keys())
    chunk_size = config.UPSTOX_BULK_QUOTE_CHUNK_SIZE
    n_chunks = max(1, (len(keys) + chunk_size - 1) // chunk_size)

    for i in range(0, len(keys), chunk_size):
        chunk = keys[i:i + chunk_size]
        if progress_callback:
            progress_callback(min(1.0, (i / chunk_size + 1) / n_chunks),
                              f"Fetching live quotes ({i + len(chunk)}/{len(keys)} symbols)...")
        try:
            resp = requests.get(
                "https://api.upstox.com/v2/market-quote/quotes",
                headers=_upstox_headers(token),
                params={"instrument_key": ",".join(chunk)},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            # Upstox keys the response by a normalized "EXCHANGE:SYMBOL"
            # string, not the instrument_key we sent -- match back via the
            # instrument_token field each entry carries, which DOES echo
            # the original instrument_key.
            for _, quote in data.items():
                returned_key = quote.get("instrument_token")
                sym = key_to_symbol.get(returned_key)
                if not sym:
                    continue
                last_price = float(quote["last_price"])
                prev_close = float(quote.get("ohlc", {}).get("close") or last_price)
                volume = float(quote.get("volume", 0))
                results[sym] = {
                    "symbol": sym, "price": last_price, "volume": volume, "prev_close": prev_close,
                    "pct_move": (last_price - prev_close) / prev_close * 100 if prev_close else 0.0,
                    "source": "upstox_live_bulk", "timestamp": pd.Timestamp.utcnow(),
                }
        except Exception:
            continue  # this chunk failed -- affected symbols get a synthetic fallback below

    # Any symbol that didn't resolve to an instrument_key, or whose chunk
    # call failed, or wasn't present in the response, gets a per-symbol
    # synthetic fallback so the caller always gets a full result set.
    for sym in symbols:
        if sym not in results:
            results[sym] = _synthetic_quote(sym)
    return results


def _yfinance_bulk_quotes(symbols: list[str], progress_callback=None,
                           batch_size: int = 40) -> dict[str, dict]:
    """Free-tier fallback: yfinance's multi-ticker download in batches.
    Notably slower and less "live" than Upstox's bulk API (yfinance has no
    true bulk LTP endpoint -- this downloads a short recent price history
    per batch and reads the last two rows), which is exactly why
    config.MAX_LIVE_SCAN_UNIVERSE_SIZE_YFINANCE caps how many symbols this
    path is asked to cover in one scan."""
    results: dict[str, dict] = {}
    if yf is None:
        return {sym: _synthetic_quote(sym) for sym in symbols}

    n_batches = max(1, (len(symbols) + batch_size - 1) // batch_size)
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        if progress_callback:
            progress_callback(min(1.0, (i / batch_size + 1) / n_batches),
                              f"Fetching live quotes ({i + len(batch)}/{len(symbols)} symbols, yfinance)...")
        try:
            data = yf.download(batch, period="5d", interval="1d", group_by="ticker",
                                progress=False, auto_adjust=True, threads=True)
            for sym in batch:
                try:
                    sym_df = data[sym] if len(batch) > 1 else data
                    sym_df = sym_df.dropna()
                    if len(sym_df) < 2:
                        results[sym] = _synthetic_quote(sym)
                        continue
                    last_close = float(sym_df["Close"].iloc[-1])
                    prev_close = float(sym_df["Close"].iloc[-2])
                    volume = float(sym_df["Volume"].iloc[-1])
                    results[sym] = {
                        "symbol": sym, "price": last_close, "volume": volume, "prev_close": prev_close,
                        "pct_move": (last_close - prev_close) / prev_close * 100 if prev_close else 0.0,
                        "source": "yfinance_batch", "timestamp": pd.Timestamp.utcnow(),
                    }
                except Exception:
                    results[sym] = _synthetic_quote(sym)
        except Exception:
            for sym in batch:
                results[sym] = _synthetic_quote(sym)
    return results
