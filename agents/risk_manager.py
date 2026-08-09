"""
agents/risk_manager.py
------------------------
Position sizing, stop-loss, targets, hard rejects for unsafe setups.
"""
from __future__ import annotations
import config


def _rr_passes(reward_risk: float) -> bool:
    return reward_risk >= (config.MIN_REWARD_RISK - config.RR_TOLERANCE)


def kelly_fraction(win_rate_pct: float | None, avg_win_pct: float | None,
                    avg_loss_pct: float = 1.0) -> float:
    if win_rate_pct is None or avg_win_pct is None or avg_loss_pct <= 0:
        return 0.0
    w = win_rate_pct / 100
    r = avg_win_pct / avg_loss_pct if avg_loss_pct else 0
    if r <= 0:
        return 0.0
    f = w - (1 - w) / r
    return float(max(0.0, min(f, config.KELLY_FRACTION_CAP)))


def evaluate(symbol: str, last_price: float, atr_val: float,
             avg_daily_volume: float, capital: float,
             direction: str = "long", quant_win_rate: float | None = None,
             quant_avg_return_pct: float | None = None) -> dict:
    if avg_daily_volume < config.MIN_AVG_DAILY_VOLUME:
        return {"symbol": symbol, "approved": False,
                "reject_reason": f"Liquidity floor: avg daily volume {avg_daily_volume:,.0f} "
                                  f"< required {config.MIN_AVG_DAILY_VOLUME:,.0f}"}
    if atr_val <= 0:
        return {"symbol": symbol, "approved": False,
                "reject_reason": "ATR is zero/invalid -- cannot size a stop safely."}

    stop_distance = config.STOP_ATR_MULTIPLE * atr_val
    stop_price = last_price - stop_distance if direction == "long" else last_price + stop_distance

    targets = {}
    for label, mult in config.TARGET_ATR_MULTIPLES.items():
        dist = mult * atr_val
        targets[label] = round(last_price + dist if direction == "long" else last_price - dist, 2)

    reward = abs(targets["T2"] - last_price)
    risk = abs(last_price - stop_price)
    reward_risk = reward / risk if risk else 0.0

    if not _rr_passes(reward_risk):
        return {"symbol": symbol, "approved": False,
                "reject_reason": f"Reward:Risk {reward_risk:.2f} < required "
                                  f"{config.MIN_REWARD_RISK} (T2 vs stop)."}

    max_risk_amount = capital * (config.MAX_RISK_PER_TRADE_PCT / 100)
    shares = int(max_risk_amount / risk) if risk else 0
    position_value = round(shares * last_price, 2)
    kelly = kelly_fraction(quant_win_rate, quant_avg_return_pct)
    kelly_capital_suggestion = round(capital * kelly, 2)

    return {"symbol": symbol, "approved": True, "direction": direction,
            "entry": round(last_price, 2), "stop": round(stop_price, 2), "targets": targets,
            "reward_risk": round(reward_risk, 2), "risk_per_share": round(risk, 2),
            "max_risk_amount": round(max_risk_amount, 2), "shares": shares,
            "position_value": position_value, "kelly_fraction": round(kelly, 3),
            "kelly_capital_suggestion": kelly_capital_suggestion}
