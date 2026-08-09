"""
gsheets_sync.py
------------------
Optional Google Sheets mirror for run_log.csv, so history survives
Streamlit Cloud redeploys. Silently no-ops if not configured; never
blocks the pipeline on any API error.

*** NaN/None-IN-JSON-PAYLOAD BUG FIX (found via rigorous stress testing) ***
astype(str).values.tolist() left raw float NaN objects in the payload for
REJECTED-decision rows (which legitimately have None/NaN in numeric
columns). `requests` explicitly calls
complexjson.dumps(json, allow_nan=False), so any NaN anywhere in the
payload raised InvalidJSONError client-side -- meaning any run with a
rejected candidate (i.e. almost every run) could never actually sync.
Fixed by sanitizing NaN/None -> "" before serialization.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
import config

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except Exception:
    GSPREAD_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]


def is_configured() -> bool:
    if not GSPREAD_AVAILABLE:
        return False
    try:
        return "gcp_service_account" in st.secrets
    except Exception:
        return False


@st.cache_resource(show_spinner=False)
def _client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _worksheet():
    gc = _client()
    try:
        sh = gc.open(config.GSHEETS_SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(config.GSHEETS_SPREADSHEET_NAME)
    try:
        ws = sh.worksheet(config.GSHEETS_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=config.GSHEETS_WORKSHEET_NAME, rows=1000, cols=20)
    return ws


def append_rows(df: pd.DataFrame) -> bool:
    if not is_configured() or df.empty:
        return False
    try:
        ws = _worksheet()
        existing = ws.get_all_values()
        sanitized_df = df.where(pd.notna(df), "")
        rows_to_write = sanitized_df.astype(str).values.tolist()
        if not existing:
            ws.append_row(list(df.columns), value_input_option="RAW")
        ws.append_rows(rows_to_write, value_input_option="RAW")
        return True
    except Exception as e:
        st.warning(f"Google Sheets sync skipped this run (will retry next run): {e}")
        return False


def read_all() -> pd.DataFrame:
    if not is_configured():
        return pd.DataFrame()
    try:
        ws = _worksheet()
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        if "run_timestamp" in df.columns:
            df["run_timestamp"] = pd.to_datetime(df["run_timestamp"], errors="coerce")
        return df
    except Exception as e:
        st.warning(f"Could not read Google Sheets history: {e}")
        return pd.DataFrame()


def connection_status() -> dict:
    if not GSPREAD_AVAILABLE:
        return {"connected": False, "reason": "gspread not installed in this environment"}
    if not is_configured():
        return {"connected": False, "reason": "no [gcp_service_account] found in Streamlit secrets"}
    try:
        ws = _worksheet()
        return {"connected": True, "sheet_name": config.GSHEETS_SPREADSHEET_NAME,
                "worksheet": ws.title, "row_count": len(ws.get_all_values())}
    except Exception as e:
        return {"connected": False, "reason": f"connection failed: {e}"}
