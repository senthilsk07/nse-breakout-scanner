import os
import time
from datetime import date
from urllib.parse import quote

import pandas as pd
import requests
from strategy import evaluate_symbol

BASE = "https://api.upstox.com/v3"

def load_universe():
    path = os.getenv("UNIVERSE_CSV", "universe.csv")
    if not os.path.exists(path):
        return pd.DataFrame(), f"Universe file not found: {path}"
    df = pd.read_csv(path, dtype=str, comment="#").fillna("")
    required = {"symbol", "instrument_key", "sector"}
    if not required.issubset(df.columns):
        return pd.DataFrame(), "universe.csv must have columns: symbol,instrument_key,sector"
    df = df[(df["symbol"].str.strip() != "") & (df["instrument_key"].str.strip() != "")]
    df = df.drop_duplicates(subset=["instrument_key"])
    return df, None

def _headers():
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing UPSTOX_ACCESS_TOKEN environment variable. Set it in Render Environment.")
    return {"Accept": "application/json", "Authorization": f"Bearer {token}"}

def fetch_one(instrument_key, selected_date, is_live):
    # V3 supports custom minute intervals. Current-day endpoint for live date;
    # historical endpoint for past date.
    encoded_key = quote(instrument_key, safe="")
    if is_live:
        url = f"{BASE}/historical-candle/intraday/{encoded_key}/minutes/5"
    else:
        d = selected_date.isoformat()
        url = f"{BASE}/historical-candle/{encoded_key}/minutes/5/{d}/{d}"
    response = requests.get(url, headers=_headers(), timeout=15)
    if response.status_code == 429:
        raise RuntimeError("Upstox API rate limit (429). Reduce the universe size or use a WebSocket/queue architecture.")
    response.raise_for_status()
    payload = response.json()
    candles = payload.get("data", {}).get("candles", [])
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    rows = []
    for c in candles:
        rows.append({
            "timestamp": c[0], "open": float(c[1]), "high": float(c[2]),
            "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])
        })
    return pd.DataFrame(rows)

def fetch_candles_for_universe(universe, selected_date, is_live):
    result, notes = {}, []
    headers_ok = True
    for idx, row in universe.reset_index(drop=True).iterrows():
        key = row["instrument_key"]
        try:
            result[key] = fetch_one(key, selected_date, is_live)
        except Exception as exc:
            notes.append(f"{row['symbol']}: {exc}")
        # Gentle pacing; REST polling across a large universe every 10 seconds is not production-safe.
        time.sleep(0.12)
    return result, notes

def scan_all(universe, candle_map, selected_date):
    rows = []
    diagnostics = {"configured_stocks": int(len(universe)), "candles_received": 0, "stocks_with_errors_or_no_data": 0}
    for _, row in universe.iterrows():
        candles = candle_map.get(row["instrument_key"])
        if candles is not None:
            diagnostics["candles_received"] += int(len(candles))
        else:
            diagnostics["stocks_with_errors_or_no_data"] += 1
        rows.append(evaluate_symbol(row, candles, selected_date))
    return pd.DataFrame(rows), diagnostics
