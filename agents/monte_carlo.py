"""
agents/monte_carlo.py
-----------------------
GBM price-path simulation. Reports the probability of hitting each target
vs. the stop within the horizon.

*** STOP-DIRECTION BUG FIX (found via rigorous stress testing) ***
The old code applied the SAME comparison direction to both the stop-loss
and the profit targets. For a long position, the stop sits BELOW entry --
it needs "price <= stop", the OPPOSITE comparison from targets ("price >=
target"). The old code checked "price >= stop" for longs, trivially
satisfied almost immediately -- producing a bogus ~100% "stop hit" rate on
every real approved candidate. Fixed by using an explicit is_upside flag
per level, with stop and targets always on opposite sides.
"""
from __future__ import annotations
import numpy as np
import config


def simulate(entry: float, stop: float, targets: dict, daily_returns,
             direction: str = "long", n_paths: int = config.MONTE_CARLO_PATHS,
             horizon: int = config.MONTE_CARLO_HORIZON_DAYS, seed: int | None = None) -> dict:
    returns = np.asarray(daily_returns)
    returns = returns[~np.isnan(returns)]
    if len(returns) < 20:
        return {"valid": False, "reason": "insufficient return history for simulation"}

    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    if sigma == 0:
        return {"valid": False, "reason": "zero volatility -- cannot simulate"}

    rng = np.random.default_rng(seed)
    shocks = rng.normal((mu - 0.5 * sigma ** 2), sigma, size=(n_paths, horizon))
    log_paths = np.cumsum(shocks, axis=1)
    price_paths = entry * np.exp(log_paths)
    is_long = direction == "long"

    def _hit_prob(level, is_upside):
        if is_upside:
            hit_step = np.argmax(price_paths >= level, axis=1)
            hit_mask = (price_paths >= level).any(axis=1)
        else:
            hit_step = np.argmax(price_paths <= level, axis=1)
            hit_mask = (price_paths <= level).any(axis=1)
        hit_step = np.where(hit_mask, hit_step, horizon)
        return hit_mask, hit_step

    stop_hit, stop_step = _hit_prob(stop, is_upside=not is_long)

    target_hits = {}
    for label, level in targets.items():
        hit_mask, hit_step = _hit_prob(level, is_upside=is_long)
        hits_first = hit_mask & (~stop_hit | (hit_step < stop_step))
        target_hits[label] = {"hit_probability_pct": round(float(hit_mask.mean() * 100), 1),
                               "hits_before_stop_pct": round(float(hits_first.mean() * 100), 1)}

    return {"valid": True, "n_paths": n_paths, "horizon_days": horizon,
            "mu_daily": round(mu * 100, 3), "sigma_daily": round(sigma * 100, 3),
            "stop_hit_probability_pct": round(float(stop_hit.mean() * 100), 1),
            "targets": target_hits, "price_paths_sample": price_paths[:60].tolist()}
