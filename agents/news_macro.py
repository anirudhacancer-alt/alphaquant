"""
agents/news_macro.py
-----------------------
VADER sentiment scoring layered on keyword-based impact tagging.

*** TWO FIXES FOUND VIA RIGOROUS STRESS TESTING ***
1. Short-root false positives: word-boundary regex instead of plain
   substring match (was matching "LT" inside "fault", "difficult", etc.)
2. NaN-vs-None: pd.isna() instead of `is not None` (NaN is not None in
   Python, so a single missing sentiment value used to corrupt the whole
   weighted score to NaN).
"""
from __future__ import annotations
import datetime as dt
import re
import feedparser
import pandas as pd
import config

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _analyzer = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = True
except Exception:
    _analyzer = None
    VADER_AVAILABLE = False


def _impact_tag(headline: str) -> str:
    text = headline.lower()
    if any(kw in text for kw in config.NEWS_HIGH_IMPACT_KEYWORDS):
        return "High"
    if any(kw in text for kw in config.NEWS_MEDIUM_IMPACT_KEYWORDS):
        return "Medium"
    return "Low"


def _sentiment(headline: str) -> dict:
    if not VADER_AVAILABLE:
        return {"compound": None, "label": "unknown"}
    scores = _analyzer.polarity_scores(headline)
    compound = scores["compound"]
    label = "positive" if compound >= 0.25 else "negative" if compound <= -0.25 else "neutral"
    return {"compound": round(compound, 3), "label": label}


def fetch_headlines(lookback_hours: int = config.NEWS_LOOKBACK_HOURS) -> pd.DataFrame:
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=lookback_hours)
    rows = []
    for feed_url in config.NEWS_RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries:
                published = getattr(entry, "published_parsed", None)
                if published:
                    published_dt = dt.datetime(*published[:6])
                    if published_dt < cutoff:
                        continue
                else:
                    published_dt = None
                headline = getattr(entry, "title", "")
                sentiment = _sentiment(headline)
                rows.append({"headline": headline, "published": published_dt, "source": feed_url,
                             "impact": _impact_tag(headline), "sentiment_compound": sentiment["compound"],
                             "sentiment_label": sentiment["label"]})
        except Exception as e:
            rows.append({"headline": f"[feed unavailable: {e}]", "published": None, "source": feed_url,
                         "impact": "Low", "sentiment_compound": None, "sentiment_label": "unknown"})
    if not rows:
        return pd.DataFrame(columns=["headline", "published", "source", "impact",
                                      "sentiment_compound", "sentiment_label"])
    return pd.DataFrame(rows)


def headlines_for_symbol(symbol: str, headlines: pd.DataFrame) -> pd.DataFrame:
    root = symbol.replace(".NS", "").replace(".BO", "")
    if headlines.empty:
        return headlines
    escaped_root = re.escape(root)
    pattern = rf"\b{escaped_root}\b"
    mask = headlines["headline"].str.contains(pattern, case=False, na=False, regex=True)
    return headlines[mask]


def macro_summary(headlines: pd.DataFrame) -> dict:
    if headlines.empty:
        return {"headline_count": 0, "avg_sentiment": None, "overall_label": "no data", "high_impact_count": 0}
    valid_sent = headlines["sentiment_compound"].dropna()
    avg = float(valid_sent.mean()) if not valid_sent.empty else None
    label = ("no data" if avg is None else
              "positive" if avg >= 0.15 else "negative" if avg <= -0.15 else "neutral")
    return {"headline_count": int(len(headlines)), "avg_sentiment": round(avg, 3) if avg is not None else None,
            "overall_label": label, "high_impact_count": int((headlines["impact"] == "High").sum())}


def score_for_symbol(symbol: str, headlines: pd.DataFrame) -> dict:
    sub = headlines_for_symbol(symbol, headlines)
    if sub.empty:
        return {"symbol": symbol, "news_score": 50.0, "headline_count": 0, "detail": "no recent headlines"}
    weight_map = {"High": 1.0, "Medium": 0.6, "Low": 0.3}
    weighted_sum, weight_total = 0.0, 0.0
    for _, row in sub.iterrows():
        comp = row["sentiment_compound"]
        if pd.isna(comp):
            comp = 0.0
        w = weight_map.get(row["impact"], 0.3)
        weighted_sum += comp * w
        weight_total += w
    avg_weighted = weighted_sum / weight_total if weight_total else 0.0
    score = round((avg_weighted + 1) / 2 * 100, 1)
    return {"symbol": symbol, "news_score": score, "headline_count": int(len(sub)),
            "detail": f"{len(sub)} matching headlines, weighted-avg sentiment {avg_weighted:.2f}"}
