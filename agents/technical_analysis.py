"""
agents/technical_analysis.py
-----------------------------
RSI, MACD, VWAP, Bollinger Bands, ATR, ADX, support/resistance -- computed
from scratch. ATR/ADX always on daily bars; RSI/MACD/VWAP use intraday
when available.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import config


def rsi(close: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """Wilder's RSI. Correctly handles the avg_loss==0 edge case (a pure
    uptrend with zero down-days in the lookback): RS -> infinity, which
    means RSI should be 100 (maximum overbought), NOT a neutral 50. This
    was a real bug -- fillna(50.0) was blindly catching both the genuine
    'not enough warm-up data yet' NaN case AND this legitimate 'RS is
    infinite' case, silently hiding strong-momentum overbought signals.
    Symmetrically, avg_gain==0 with avg_loss>0 (pure downtrend) -> RSI=0.
    Only the true warm-up-period NaNs (before min_periods bars exist)
    fall back to a neutral 50, since there's genuinely no signal yet."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))

    pure_uptrend = (avg_loss == 0) & (avg_gain > 0)
    out = out.mask(pure_uptrend, 100.0)
    no_movement = (avg_loss == 0) & (avg_gain == 0)
    out = out.mask(no_movement, 50.0)

    return out.fillna(50.0)


def macd(close: pd.Series, fast=config.MACD_FAST, slow=config.MACD_SLOW,
         signal=config.MACD_SIGNAL) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_vol = df["Volume"].cumsum().replace(0, np.nan)
    cum_tp_vol = (typical * df["Volume"]).cumsum()
    return (cum_tp_vol / cum_vol).bfill()


def bollinger_bands(close: pd.Series, period=config.BOLLINGER_PERIOD,
                     num_std=config.BOLLINGER_STD) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower, "pct_b": pct_b})


def atr(daily_df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.Series:
    high, low, close = daily_df["High"], daily_df["Low"], daily_df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(daily_df: pd.DataFrame, period: int = config.ADX_PERIOD) -> pd.Series:
    high, low, close = daily_df["High"], daily_df["Low"], daily_df["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_smooth = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=daily_df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False).mean() / atr_smooth.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=daily_df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False).mean() / atr_smooth.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().fillna(0.0)


def support_resistance(daily_df: pd.DataFrame, window: int = 10) -> dict:
    highs = daily_df["High"].rolling(window, center=True).max()
    lows = daily_df["Low"].rolling(window, center=True).min()
    pivot_highs = daily_df["High"][daily_df["High"] == highs].dropna()
    pivot_lows = daily_df["Low"][daily_df["Low"] == lows].dropna()
    resistance = float(pivot_highs.tail(3).mean()) if not pivot_highs.empty else float(daily_df["High"].max())
    support = float(pivot_lows.tail(3).mean()) if not pivot_lows.empty else float(daily_df["Low"].min())
    return {"support": support, "resistance": resistance}


def analyze(symbol: str, daily_df: pd.DataFrame, intraday_df: pd.DataFrame) -> dict:
    if daily_df is None or daily_df.empty or len(daily_df) < config.ATR_PERIOD + 2:
        return {"symbol": symbol, "valid": False, "reason": "insufficient daily history"}

    fast_df = intraday_df if (intraday_df is not None and not intraday_df.empty) else daily_df
    is_daily_fallback = bool(fast_df.attrs.get("is_daily_fallback", fast_df is daily_df))

    close_fast = fast_df["Close"]
    rsi_val = float(rsi(close_fast).iloc[-1])
    macd_df = macd(close_fast)
    macd_val = float(macd_df["macd"].iloc[-1])
    macd_signal = float(macd_df["signal"].iloc[-1])
    macd_hist = float(macd_df["hist"].iloc[-1])
    bb = bollinger_bands(close_fast)
    pct_b = float(bb["pct_b"].iloc[-1]) if not np.isnan(bb["pct_b"].iloc[-1]) else 0.5
    vwap_val = float(vwap(fast_df).iloc[-1])

    atr_series = atr(daily_df)
    atr_val = float(atr_series.iloc[-1])
    adx_val = float(adx(daily_df).iloc[-1])
    sr = support_resistance(daily_df)
    last_price = float(close_fast.iloc[-1])

    signals = []
    if rsi_val <= config.RSI_OVERSOLD:
        signals.append("RSI oversold")
    if rsi_val >= config.RSI_OVERBOUGHT:
        signals.append("RSI overbought")
    if macd_hist > 0 and macd_val > macd_signal:
        signals.append("MACD bullish crossover")
    elif macd_hist < 0 and macd_val < macd_signal:
        signals.append("MACD bearish crossover")
    signals.append("Price above VWAP" if last_price > vwap_val else "Price below VWAP")
    if adx_val >= 25:
        signals.append(f"Strong trend (ADX {adx_val:.0f})")

    return {"symbol": symbol, "valid": True, "last_price": last_price, "rsi": round(rsi_val, 2),
            "macd": round(macd_val, 4), "macd_signal": round(macd_signal, 4), "macd_hist": round(macd_hist, 4),
            "vwap": round(vwap_val, 2), "bollinger_pct_b": round(pct_b, 3),
            "atr": round(atr_val, 2), "adx": round(adx_val, 2),
            "support": round(sr["support"], 2), "resistance": round(sr["resistance"], 2),
            "signals": signals, "intraday_data_used": not is_daily_fallback}
