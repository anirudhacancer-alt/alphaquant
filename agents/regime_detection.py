"""
agents/regime_detection.py
----------------------------
HMM market regime classification -- bull / choppy / bear.

*** TWO FIXES FOUND VIA RIGOROUS STRESS TESTING ***

Fix 1 -- multi-restart fitting (solves a real missed-signal bug):
GaussianHMM's EM fitting algorithm is sensitive to random initialization
and prone to poor local optima. Fit multiple times with different seeds,
keep the fit with the highest log-likelihood.

Fix 2 -- BIC gate against a trivial 1-state baseline (solves a false-
confidence bug that fix 1 alone made WORSE): naively picking highest
log-likelihood among restarts can select a degenerate variance-collapse
solution that reports FALSE ~100% confidence on genuinely single-regime
data. A formal BIC comparison against a trivial single-Gaussian baseline
only favors multi-state when there's genuine, non-noise evidence of
multiple regimes.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import config

try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except Exception:
    HMM_AVAILABLE = False

N_FIT_RESTARTS = 8

DEGENERATE_SCALE_RATIO = 1000.0
MIN_STATE_OCCUPANCY_FRAC = 0.02


def _is_degenerate_fit(model, returns: np.ndarray, data_var: float) -> bool:
    n = len(returns)
    states = model.predict(returns)
    covars = model.covars_.flatten()
    for s in range(len(covars)):
        occupancy_frac = np.sum(states == s) / n
        if occupancy_frac < MIN_STATE_OCCUPANCY_FRAC:
            continue
        if covars[s] > data_var * DEGENERATE_SCALE_RATIO or covars[s] < data_var / DEGENERATE_SCALE_RATIO:
            return True
    return False


def _fit_best_of_n_restarts(returns: np.ndarray, n_states: int, n_restarts: int = N_FIT_RESTARTS):
    best_model, best_score, last_error = None, -np.inf, None
    data_var = float(np.var(returns))
    for i in range(n_restarts):
        try:
            candidate = GaussianHMM(n_components=n_states, covariance_type="full",
                                     n_iter=200, random_state=42 + i * 137)
            candidate.fit(returns)
            score = candidate.score(returns)
            if not np.isfinite(score):
                continue
            if _is_degenerate_fit(candidate, returns, data_var):
                continue
            if score > best_score:
                best_score, best_model = score, candidate
        except Exception as e:
            last_error = e
            continue
    if best_model is None:
        raise last_error if last_error is not None else \
            RuntimeError("All HMM fit restarts were numerically degenerate or failed")
    return best_model, best_score


def _one_state_log_likelihood(returns: np.ndarray) -> float:
    x = returns.flatten()
    mu, sigma = float(np.mean(x)), float(np.std(x))
    sigma = max(sigma, 1e-12)
    n = len(x)
    return float(-0.5 * n * np.log(2 * np.pi * sigma ** 2) - np.sum((x - mu) ** 2) / (2 * sigma ** 2))


def _bic(log_lik: float, n_params: int, n_obs: int) -> float:
    return -2 * log_lik + n_params * np.log(n_obs)


def _n_state_hmm_param_count(n_states: int) -> int:
    return n_states + n_states + n_states * (n_states - 1) + (n_states - 1)


def detect_regime(daily_df: pd.DataFrame) -> dict:
    if not HMM_AVAILABLE:
        return {"regime": "unknown", "confidence": None, "reason": "hmmlearn not installed"}
    if daily_df is None or len(daily_df) < config.HMM_LOOKBACK_DAYS // 2:
        return {"regime": "unknown", "confidence": None, "reason": "insufficient history for HMM fit"}

    df = daily_df.tail(config.HMM_LOOKBACK_DAYS)
    returns = df["Close"].pct_change().dropna().values.reshape(-1, 1)
    if len(returns) < 30:
        return {"regime": "unknown", "confidence": None, "reason": "too few return observations"}

    if float(np.std(returns)) < 1e-8:
        return {"regime": "unknown", "confidence": None,
                "reason": "price data has no meaningful variation to detect a regime from"}

    try:
        model, ll_n_state = _fit_best_of_n_restarts(returns, n_states=config.HMM_N_STATES)

        n_obs = len(returns)
        ll_one_state = _one_state_log_likelihood(returns)
        bic_one_state = _bic(ll_one_state, n_params=2, n_obs=n_obs)
        bic_n_state = _bic(ll_n_state, n_params=_n_state_hmm_param_count(config.HMM_N_STATES), n_obs=n_obs)

        if bic_n_state >= bic_one_state:
            return {"regime": "unknown", "confidence": None,
                    "reason": "no statistically significant evidence of distinct market regimes "
                              "in this window (BIC favors a single, undifferentiated regime)"}

        hidden_states = model.predict(returns)
        state_means = model.means_.flatten()
        order = np.argsort(state_means)
        labels = {}
        if config.HMM_N_STATES == 3:
            labels[order[0]], labels[order[1]], labels[order[2]] = "bear", "choppy", "bull"
        else:
            for rank, state_idx in enumerate(order):
                labels[state_idx] = f"regime_{rank}"

        current_state = hidden_states[-1]
        regime = labels[current_state]
        posteriors = model.predict_proba(returns)
        confidence = float(posteriors[-1, current_state])
        return {"regime": regime, "confidence": round(confidence * 100, 1),
                "state_mean_returns": {labels[i]: round(float(state_means[i]) * 100, 3)
                                        for i in range(config.HMM_N_STATES)}}
    except Exception as e:
        return {"regime": "unknown", "confidence": None, "reason": f"HMM fit failed: {e}"}
