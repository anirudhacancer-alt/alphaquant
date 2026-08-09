# Deploying AlphaQuant Web — Zero Local Installs

This guide gets you a **public web app URL** that scans the FULL NSE
market (via NSE's own free bhavcopy archive) with live/EOD scan modes,
plus optional Upstox live data, Google Sheets persistence, and an
installable Android app. Nothing is installed on your own laptop.

## ⚠️ Before you start: rotate any exposed credentials

If you've previously shared a `config.py`, `upstox_token.txt`, or similar
file containing a real Upstox `client_secret` or access token with anyone,
treat that secret as compromised and regenerate it from the
[Upstox Developer Console](https://account.upstox.com/developer/apps)
before deploying. This project's `config.py` never contains real secrets.

## Step 1 — Push this project to GitHub (5 min)

1. Create a repo at [github.com/new](https://github.com/new), e.g.
   `alphaquant-web`.
2. Upload every file/folder from this package, keeping the structure
   as-is (**"Add file" → "Upload files"**, drag the whole unzipped folder
   in, commit).

## Step 2 — Deploy on Streamlit Community Cloud (5 min, free)

1. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub.
2. **"New app"** → pick your repo/branch → Main file path `app.py`.
3. Open **"Advanced settings"** and set **Python version to 3.11 or
   3.12** before clicking Deploy.

   > ⚠️ This is the fix for the `hmmlearn` build error — that error
   > happens under Python 3.14 (too new for hmmlearn's pre-built wheels).
   > This has nothing to do with your database choice. You never need to
   > `pip install` locally at all.
4. Click **Deploy** → you'll get a URL like
   `https://alphaquant-web-yourname.streamlit.app` in 2–3 minutes.

## Step 3 — Point the app at its own URL

1. In your repo, open `config.py`, find:
   ```python
   APP_BASE_URL = "https://your-app-name.streamlit.app"
   ```
   replace with your real URL, **Commit changes**.
2. If building the Android app too, open `mobile_app/lib/main.dart` and
   update the same URL in `const String appUrl = "...";`, commit.

## Step 4 — Connect live Upstox data

1. Register an app in the
   [Upstox Developer Console](https://account.upstox.com/developer/apps)
   → get **Client ID** and **Client Secret**.
2. Set **Redirect URI** to your exact `APP_BASE_URL` from Step 3.
3. In Streamlit Cloud → your app → **Settings → Secrets**, add:
   ```toml
   [upstox]
   client_id = "your-client-id"
   client_secret = "your-client-secret"
   ```
4. Reload — click **"Connect to Upstox"** in the sidebar, log in on
   Upstox's own page, get redirected back with live data active.

   > ⏰ Every access token expires at **3:30 AM IST the next day**,
   > regardless of when issued — no refresh token exists for this flow.
   > The sidebar always shows your exact expiry, and the app automatically
   > falls back to free yfinance whenever Upstox isn't connected.

## Step 5 — Full-market scanning (NSE bhavcopy) — works automatically

The app now scans the **entire liquid NSE market** by default, not a
hand-picked 20-stock list. This requires **no setup on your part** — it
pulls directly from NSE's own free, public daily archive
(`sec_bhavdata_full`), no login/API key needed. Two important things to
understand:

1. **Two scan modes**, both in the sidebar:
   - **🟢 Live** — bhavcopy discovers the liquid universe (typically
     several hundred stocks clearing the Rs.5cr/day liquidity floor), then
     fetches LIVE quotes for all of them. With Upstox connected, this uses
     Upstox's bulk quote API (500 instruments/call — cheap and fast). On
     the free yfinance fallback, the universe is capped to ~60 symbols
     (`config.MAX_LIVE_SCAN_UNIVERSE_SIZE_YFINANCE`) since yfinance has no
     true bulk endpoint and calling it hundreds of times would be slow.
   - **🌙 End-of-day** — uses ONLY cached bhavcopy history, zero live API
     calls, covers the FULL liquid universe **uncapped**, and works any
     time (including nights/weekends) — best for reviewing "what happened
     today" or prepping for the next session.

2. **Bhavcopy is end-of-day data** — NSE doesn't publish free live/intraday
   bulk data (nobody does, freely). This means the *discovery* of which
   stocks are liquid enough to matter, and their historical volume
   baseline, comes from bhavcopy; the actual *live* number during market
   hours still needs Upstox (recommended, for full coverage) or the
   capped yfinance fallback.

3. **Adjusting the liquidity floor**: edit `config.BHAVCOPY_MIN_AVG_DAILY_VALUE_CR`
   (default 5.0, in INR crore/day average traded value) to include more
   or fewer stocks in the universe.

4. If NSE's bhavcopy archive is ever temporarily unreachable, the app
   automatically and silently falls back to the original 20-stock
   `FALLBACK_WATCHLIST` — it never breaks, it just scans less broadly
   until bhavcopy is reachable again.

## Step 6 — Google Sheets persistence (optional)

1. Create a Google Cloud service account (console.cloud.google.com),
   enable **Google Sheets API** + **Google Drive API**, create a service
   account, download its JSON key.
2. Create a Google Sheet named `AlphaQuant Run Log`, share it with the
   service account's `client_email` (from the JSON) as Editor.
3. In Streamlit Cloud secrets, add a `[gcp_service_account]` block using
   every field from the downloaded JSON (keep `private_key`'s `\n`
   characters exactly as-is, in one quoted string).
4. Reload — the Run Log tab shows "📄 PERSISTED" once connected.

If not set up, the app automatically falls back to CSV-only (no errors).

## Step 7 (optional) — Build an installable Android app (APK)

See **APK_GUIDE.md** — GitHub Actions builds a Flutter WebView wrapper
around your deployed URL; download the finished `.apk` from the Actions
tab. No local Flutter/Android Studio needed.

## Free tier limits to be aware of

- Streamlit Cloud apps sleep after a few idle days, waking on next visit.
- Bhavcopy fetches are cached 12h per date — you're not re-downloading
  history on every rerun.
- yfinance occasionally rate-limits heavy anonymous use; keep the live
  scan mode's yfinance-fallback universe capped (default 60) if you're
  not using Upstox.
- Google Sheets API free quota is far more than a single-user app needs.
- GitHub Actions gives 2,000 free build-minutes/month; one APK build
  takes ~3–5 minutes.
