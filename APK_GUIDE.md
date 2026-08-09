# Building the AlphaQuant Android App (.apk) — Zero Local Installs

Get an app icon on your phone's home screen, built entirely by GitHub's
servers via GitHub Actions. Nothing to install on your PC or phone except
the final APK.

## What this actually is

A thin **WebView wrapper** (`mobile_app/lib/main.dart`) around your
deployed Streamlit app — not a separate re-implementation. All the real
work (including the full-market bhavcopy scanning) still runs on
Streamlit Cloud's servers.

## Step 1 — Point the wrapper at your deployed app

Open `mobile_app/lib/main.dart`, update:
```dart
const String appUrl = "https://your-app-name.streamlit.app";
```

## Step 2 — Push to GitHub

Already done if you followed DEPLOY.md.

## Step 3 — Let GitHub Actions build the APK

1. Repo → **Actions** tab → "Build AlphaQuant APK" should run automatically
   (or click it, then "Run workflow" to trigger manually).
2. Wait ~3–5 minutes.
3. Open the completed run → **Artifacts** → download
   `alphaquant-app-release` (contains `app-release.apk`).

## Step 4 — Install on your Android phone

1. Transfer the `.apk` to your phone, tap it.
2. Allow "install from unknown sources" when prompted (normal, not unsafe).
3. Open **AlphaQuant** from your app drawer.

## Updating later

Backend/UI changes to the Streamlit app go live automatically next time
you open the APK. Only rebuild the APK for changes inside `mobile_app/`
itself (icon, splash screen).
