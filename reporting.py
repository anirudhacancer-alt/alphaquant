"""
reporting.py
-------------
Formatted output + run-over-run comparison, backed by data/run_log.csv
(always written, append-only, integrity-checked) and optionally mirrored
to Google Sheets for persistence across redeploys.
"""
from __future__ import annotations
import os
import pandas as pd
import config
import gsheets_sync

RUN_LOG_COLUMNS = ["run_timestamp", "symbol", "status", "confidence_score",
                    "entry", "stop", "target_t1", "target_t2", "target_t3",
                    "reward_risk", "note"]


def _ensure_log_dir():
    os.makedirs(os.path.dirname(config.RUN_LOG_PATH), exist_ok=True)


def append_run(decisions: list[dict], scanned_symbols: list[str]) -> pd.DataFrame:
    _ensure_log_dir()
    run_ts = pd.Timestamp.now()

    rows = []
    decided_symbols = {d["symbol"] for d in decisions}
    for d in decisions:
        targets = d.get("targets") or {}
        rows.append({
            "run_timestamp": run_ts, "symbol": d["symbol"], "status": d["decision"],
            "confidence_score": d.get("confidence_score"), "entry": d.get("entry"), "stop": d.get("stop"),
            "target_t1": targets.get("T1"), "target_t2": targets.get("T2"), "target_t3": targets.get("T3"),
            "reward_risk": None, "note": d.get("reject_reason", ""),
        })
    for sym in scanned_symbols:
        if sym not in decided_symbols:
            rows.append({"run_timestamp": run_ts, "symbol": sym, "status": "NOT_SHORTLISTED",
                         "confidence_score": None, "entry": None, "stop": None,
                         "target_t1": None, "target_t2": None, "target_t3": None,
                         "reward_risk": None, "note": "Did not clear market scanner thresholds"})

    new_rows = pd.DataFrame(rows, columns=RUN_LOG_COLUMNS)

    file_exists = os.path.isfile(config.RUN_LOG_PATH)
    prior_len = 0
    if file_exists:
        prior_len = len(pd.read_csv(config.RUN_LOG_PATH))

    with open(config.RUN_LOG_PATH, "a", newline="") as f:
        new_rows.to_csv(f, header=not file_exists, index=False)
        f.flush()
        os.fsync(f.fileno())

    updated = pd.read_csv(config.RUN_LOG_PATH)
    if len(updated) != prior_len + len(new_rows):
        raise RuntimeError(
            f"run_log.csv append failed integrity check: expected {prior_len + len(new_rows)} "
            f"rows, found {len(updated)}."
        )

    if config.RUN_LOG_BACKEND == "gsheets":
        gsheets_sync.append_rows(new_rows)

    return updated


def read_log() -> pd.DataFrame:
    if config.RUN_LOG_BACKEND == "gsheets" and gsheets_sync.is_configured():
        sheet_df = gsheets_sync.read_all()
        if not sheet_df.empty:
            return sheet_df
    if not os.path.isfile(config.RUN_LOG_PATH):
        return pd.DataFrame(columns=RUN_LOG_COLUMNS)
    return pd.read_csv(config.RUN_LOG_PATH, parse_dates=["run_timestamp"])


def flag_new_vs_previous_run(current_approved: list[str]) -> dict:
    log = read_log()
    if log.empty:
        return {"new": current_approved, "carried_over": [], "previous_run_timestamp": None}
    distinct_runs = sorted(log["run_timestamp"].unique())
    if len(distinct_runs) < 2:
        return {"new": current_approved, "carried_over": [], "previous_run_timestamp": None}
    previous_run_ts = distinct_runs[-2]
    prev_approved = set(
        log[(log["run_timestamp"] == previous_run_ts) & (log["status"] == "APPROVED")]["symbol"]
    )
    new = [s for s in current_approved if s not in prev_approved]
    carried_over = [s for s in current_approved if s in prev_approved]
    return {"new": new, "carried_over": carried_over, "previous_run_timestamp": str(previous_run_ts)}


def build_report(decisions: list[dict], scanned_symbols: list[str]) -> dict:
    approved = [d for d in decisions if d["decision"] == "APPROVED"]
    rejected = [d for d in decisions if d["decision"] == "REJECTED"]
    approved_sorted = sorted(approved, key=lambda d: -(d["confidence_score"] or 0))

    updated_log = append_run(decisions, scanned_symbols)
    flags = flag_new_vs_previous_run([d["symbol"] for d in approved_sorted])

    quick_glance = [{"symbol": d["symbol"], "confidence": d["confidence_score"],
                      "entry": d["entry"], "target_t2": (d.get("targets") or {}).get("T2"),
                      "is_new": d["symbol"] in flags["new"]}
                     for d in approved_sorted]

    return {
        "approved": approved_sorted, "rejected": rejected, "quick_glance": quick_glance,
        "new_symbols": flags["new"], "carried_over_symbols": flags["carried_over"],
        "previous_run_timestamp": flags["previous_run_timestamp"], "run_log": updated_log,
    }
