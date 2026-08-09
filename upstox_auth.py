"""
upstox_auth.py
------------------
Handles Upstox's OAuth 2.0 authorization-code login flow. Access tokens
always expire at 3:30 AM IST the following day, regardless of when
generated (Upstox platform rule).
"""
from __future__ import annotations
import datetime as dt
import urllib.parse
import requests
import streamlit as st

AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
IST_OFFSET = dt.timedelta(hours=5, minutes=30)


def _client_credentials() -> tuple[str, str]:
    try:
        return st.secrets["upstox"]["client_id"], st.secrets["upstox"]["client_secret"]
    except Exception:
        return "", ""


def is_configured() -> bool:
    client_id, client_secret = _client_credentials()
    return bool(client_id and client_secret)


def get_login_url(redirect_uri: str, state: str = "alphaquant") -> str:
    client_id, _ = _client_credentials()
    params = {"response_type": "code", "client_id": client_id,
              "redirect_uri": redirect_uri, "state": state}
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = _client_credentials()
    resp = requests.post(
        TOKEN_URL,
        headers={"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data={"code": code, "client_id": client_id, "client_secret": client_secret,
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _next_3_30am_ist(reference_utc: dt.datetime | None = None) -> dt.datetime:
    now_utc = reference_utc or dt.datetime.utcnow()
    now_ist = now_utc + IST_OFFSET
    expiry_ist = now_ist.replace(hour=3, minute=30, second=0, microsecond=0)
    if now_ist >= expiry_ist:
        expiry_ist += dt.timedelta(days=1)
    return expiry_ist - IST_OFFSET


def store_token(token_response: dict) -> None:
    st.session_state["upstox_access_token"] = token_response.get("access_token")
    st.session_state["upstox_token_expiry_utc"] = _next_3_30am_ist()
    st.session_state["upstox_user_name"] = token_response.get("user_name")
    st.session_state["upstox_user_id"] = token_response.get("user_id")


def clear_token() -> None:
    for k in ("upstox_access_token", "upstox_token_expiry_utc", "upstox_user_name", "upstox_user_id"):
        st.session_state.pop(k, None)


def get_valid_token() -> str | None:
    token = st.session_state.get("upstox_access_token")
    expiry = st.session_state.get("upstox_token_expiry_utc")
    if not token or not expiry:
        return None
    if dt.datetime.utcnow() >= expiry:
        return None
    return token


def connection_status() -> dict:
    token = get_valid_token()
    if token:
        expiry_ist = st.session_state["upstox_token_expiry_utc"] + IST_OFFSET
        return {"connected": True, "expires_at_ist": expiry_ist.strftime("%I:%M %p IST, %d %b"),
                "user_name": st.session_state.get("upstox_user_name")}
    had_token = "upstox_access_token" in st.session_state
    return {"connected": False, "expired": had_token}
