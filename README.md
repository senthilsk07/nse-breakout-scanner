# NSE Multi-Sector Breakout Scanner (T1 / T2)

This is a deployable **starter dashboard** using Streamlit + Upstox V3 candle APIs. It is not a guaranteed-profitable trading system and it does not place orders.

## Important: rotate the exposed token

An access token was pasted into the chat. Revoke it / generate a new token in Upstox, then store the replacement only as a Render environment variable named `UPSTOX_ACCESS_TOKEN`. Never commit it to GitHub or put it in `app.py`.

## What this version includes

- Dashboard with sector selector, date picker, T1/T2 alert table, diagnostics and CSV export.
- 5-minute candle fetch using Upstox V3 endpoints.
- Opening range high/low, T1 sideways check, T2 early break + extended range.
- Closed-candle breakout confirmation.
- Two volume checks displayed separately:
  1. Trigger candle volume > average volume of the relevant range.
  2. Trigger candle volume > each of the previous two completed candles.
- Render deployment config.

## Important limits / accuracy notes

1. **Universe mapping is not bundled as a complete 14-sector constituent database.** Populate `universe.csv` with valid Upstox `instrument_key` values and your sector mapping. Sector membership changes, so maintain this file from a current constituent source.
2. This starter polls the candle REST endpoint once per stock per scan. That can be slow or rate-limited for hundreds of stocks. A production-scale scanner should use Upstox Market Data Feed WebSocket V3, aggregate ticks into 5-minute candles, and persist candles/signals. REST polling is mainly for prototyping and historical lookup. Upstox notes that WebSocket streaming is intended for real-time updates; candle endpoints may have delivery delay.
3. The 10–30 second page refresh does **not** mean the exchange creates a new 5-minute candle every 10 seconds. Signals are only evaluated after the relevant 5-minute candle is complete.
4. Upstox tokens are time-limited. If the token expires, refresh it using the official OAuth flow and update Render.
5. This project implements signal scanning only. No automatic buy/sell orders are sent.

## Strategy timing convention

Candle timestamps are interpreted as the **start** of each 5-minute candle:
- Opening range 09:15–09:55 = candles starting 09:15, 09:20, ..., 09:50 (8 candles), all complete by 09:55.
- Sideways check = candles starting 09:55 through 10:20; all complete by 10:25.
- T1 trigger candles start 10:30 through 14:40 and must close outside the opening range.
- T2 early break = candles starting 09:55 through 10:20.
- T2 extended range 09:15–10:55 = candles starting 09:15 through 10:50 (20 candles), complete by 10:55.
- T2 trigger candles start 11:00 through 14:40 and must close outside the extended range.

This avoids using a candle before its close is known. If your intended candle labeling differs, adjust the time boundaries in `strategy.py`.

## Run locally

1. Install Python 3.11 or later.
2. Extract the zip and open a terminal in the project folder.
3. Create a virtual environment:
   - Windows: `py -m venv .venv` then `.venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
4. Install packages: `pip install -r requirements.txt`
5. Set the token environment variable:
   - Windows PowerShell: `$env:UPSTOX_ACCESS_TOKEN="YOUR_NEW_TOKEN"`
   - macOS/Linux: `export UPSTOX_ACCESS_TOKEN="YOUR_NEW_TOKEN"`
6. Add stock rows to `universe.csv`.
7. Start: `streamlit run app.py`
8. Open the local URL shown in terminal.

## Deploy on Render

1. Rotate the token first.
2. Upload the project to a private GitHub repository.
3. In Render, choose **New + → Web Service**, connect the repository.
4. Build command: `pip install -r requirements.txt`
5. Start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
6. Under **Environment**, add `UPSTOX_ACCESS_TOKEN` with the new token value. Do not add it to source files.
7. Deploy. Check logs for token, instrument-key, or API-limit errors.
8. Test with a small universe first, then expand gradually.

## How to prepare `universe.csv`

CSV columns must be exactly:
`symbol,instrument_key,sector`

Each stock must have the exact Upstox key (usually a key beginning `NSE_EQ|...`) and one of the sector names used in `strategy.py`. Example row format:
`RELIANCE,NSE_EQ|INE002A01018,Nifty Energy`

The example is only to show the CSV format; confirm the current instrument key and sector membership from Upstox/NSE before using it.

## Volume filter interpretation

Because “overall volume hike” can mean different things, this implementation uses:
- `range_volume_hike`: trigger candle volume is strictly greater than average 5-minute candle volume in the relevant range.
- `last_two_volume_hike`: trigger candle volume is strictly greater than the volume in each of the two immediately preceding completed candles.

If you intended a different overall-volume baseline (for example, cumulative session volume instead of average range-candle volume), change the volume baseline explicitly before live use.

## Official references

- Upstox Intraday Candle Data V3: https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/
- Upstox Historical Candle Data V3: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
- Upstox Market Data Feed V3: https://upstox.com/developer/api-documentation/v3/get-market-data-feed/
- Render environment variables: https://render.com/docs/configure-environment-variables
