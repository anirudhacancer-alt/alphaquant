"""
agents/decision_agent.py
---------------------------
Combines everything into one transparent confidence score with full
reasoning + assumptions. Weights live in config.DECISION_WEIGHTS.
"""
from __future__ import annotations
import config


def technical_score(ta: dict) -> float:
    if not ta.get("valid"):
        return 50.0
    score = 50.0
    rsi_val = ta["rsi"]
    if rsi_val <= config.RSI_OVERSOLD:
        score += 15
    elif rsi_val >= config.RSI_OVERBOUGHT:
        score -= 15
    score += 10 if ta["macd_hist"] > 0 else -10
    score += 10 if ta["last_price"] > ta["vwap"] else -10
    if ta["adx"] >= 25:
        score += 5
    return float(max(0, min(100, score)))


def regime_score(regime: dict, direction: str = "long") -> float:
    r = regime.get("regime", "unknown")
    if r == "unknown":
        return 50.0
    confidence = (regime.get("confidence") or 50) / 100
    if (r == "bull" and direction == "long") or (r == "bear" and direction == "short"):
        base = 75
    elif r == "choppy":
        base = 50
    else:
        base = 25
    return float(base * confidence + 50 * (1 - confidence))


def risk_quality_score(reward_risk: float) -> float:
    if reward_risk < config.MIN_REWARD_RISK:
        return 0.0
    scaled = 50 + (reward_risk - config.MIN_REWARD_RISK) / (4.0 - config.MIN_REWARD_RISK) * 50
    return float(max(0, min(100, scaled)))


def decide(symbol: str, ta: dict, quant: dict, regime: dict, news: dict,
           risk: dict, weights: dict | None = None) -> dict:
    w = weights or config.DECISION_WEIGHTS
    if not risk.get("approved"):
        return {"symbol": symbol, "decision": "REJECTED",
                "reject_reason": risk.get("reject_reason"), "confidence_score": None}

    t_score = technical_score(ta)
    q_score = quant.get("quant_score", 0.0) if quant.get("valid") else 50.0
    r_score = regime_score(regime, direction=risk.get("direction", "long"))
    n_score = news.get("news_score", 50.0)
    rk_score = risk_quality_score(risk.get("reward_risk", 0))

    components = {"technical": t_score, "quant": q_score, "regime": r_score,
                  "news": n_score, "risk_quality": rk_score}
    confidence = round(sum(components[k] * w.get(k, 0) for k in components), 1)

    reasoning = [
        f"Technical score {t_score:.0f}/100 (weight {w['technical']:.0%}): " + ", ".join(ta.get("signals", [])[:3]),
        f"Quant score {q_score:.0f}/100 (weight {w['quant']:.0%}): best pattern win-rate adjusted for sample size",
        f"Regime score {r_score:.0f}/100 (weight {w['regime']:.0%}): HMM regime = {regime.get('regime', 'unknown')}",
        f"News score {n_score:.0f}/100 (weight {w['news']:.0%}): {news.get('detail', 'no data')}",
        f"Risk quality {rk_score:.0f}/100 (weight {w['risk_quality']:.0%}): reward:risk = {risk.get('reward_risk')}",
    ]

    return {"symbol": symbol, "decision": "APPROVED", "confidence_score": confidence,
            "components": components, "reasoning": reasoning,
            "entry": risk.get("entry"), "stop": risk.get("stop"), "targets": risk.get("targets"),
            "shares": risk.get("shares"), "position_value": risk.get("position_value"),
            "assumptions": [
                "Technical signals use intraday data when available, daily otherwise (flagged).",
                "Quant win-rate is only as reliable as its sample size.",
                "Regime detection (HMM) assumes 3 discrete market states; real regimes are fuzzier.",
                "News sentiment (VADER) is general-purpose, not finance-domain-tuned.",
                "This is NOT a prediction of certainty -- it is a weighted, transparent research signal.",
            ]}
