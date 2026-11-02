from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd

IST = ZoneInfo("Asia/Kolkata")

SECTORS = [
    "Nifty Bank", "Nifty Financial Services", "Nifty IT", "Nifty Auto",
    "Nifty Pharma", "Nifty Healthcare", "Nifty Metal", "Nifty FMCG",
    "Nifty Media", "Nifty Realty", "Nifty Energy", "Nifty PSU Bank",
    "Nifty Private Bank", "Nifty Consumer Durables",
]

def _t(value):
    return time.fromisoformat(value)

def _between(ts, start, end):
    t = ts.timetz().replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts.time()
    return _t(start) <= t < _t(end)

def _fmt(ts):
    try:
        return ts.strftime("%H:%M")
    except Exception:
        return str(ts)

def _empty_result(row, note="Insufficient candles"):
    return {
        "symbol": row["symbol"], "sector": row["sector"], "signal": "No signal",
        "trigger_time": "", "close": None, "breakout_level": None,
        "range_high": None, "range_low": None, "candle_volume": None,
        "range_avg_volume": None, "range_volume_hike": False,
        "last_two_volume_hike": False, "volume_ratio": None, "note": note,
    }

def evaluate_symbol(row, candles, trading_date):
    """
    candles columns: timestamp, open, high, low, close, volume.
    timestamp must be candle START time in Asia/Kolkata.
    """
    if candles is None or candles.empty:
        return _empty_result(row)
    df = candles.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates("timestamp")
    if df.empty:
        return _empty_result(row)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(IST)
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(IST)

    df = df[df["timestamp"].dt.date == trading_date].copy()
    if df.empty:
        return _empty_result(row, "No candles for selected date")

    # Candle timestamps denote START time; end-time boundaries are exclusive.
    opening = df[(df["timestamp"].dt.time >= time(9, 15)) & (df["timestamp"].dt.time < time(9, 55))]
    sideways = df[(df["timestamp"].dt.time >= time(9, 55)) & (df["timestamp"].dt.time < time(10, 25))]
    if len(opening) < 8:
        return _empty_result(row, f"Opening range incomplete ({len(opening)}/8 candles)")

    hi = float(opening["high"].max())
    lo = float(opening["low"].min())
    avg_open_vol = float(opening["volume"].mean())

    # A candle is considered complete only when its 5-minute end time has passed.
    now = datetime.now(IST)
    df["end_time"] = df["timestamp"] + pd.Timedelta(minutes=5)
    df = df[df["end_time"] <= now] if trading_date == now.date() else df

    # Evaluate T1 only after the full sideways window is available and untouched.
    sideways_complete = (trading_date < now.date()) or now.time() >= time(10, 25)
    sideways_ok = sideways_complete and not sideways.empty and (sideways["high"].max() < hi) and (sideways["low"].min() > lo)

    # T2 early break must happen strictly before 10:25.
    early = df[(df["timestamp"].dt.time >= time(9, 55)) & (df["timestamp"].dt.time < time(10, 25))]
    t2_eligible = (not early.empty) and ((early["high"] > hi).any() or (early["low"] < lo).any())

    candidates = []
    if sideways_ok:
        t1_range_avg = avg_open_vol
        t1 = df[(df["timestamp"].dt.time >= time(10, 30)) & (df["timestamp"].dt.time < time(14, 45))]
        for _, candle in t1.iterrows():
            prior = df[df["timestamp"] < candle["timestamp"]].tail(2)
            if len(prior) < 2:
                continue
            direction = "Bullish" if candle["close"] > hi else ("Bearish" if candle["close"] < lo else None)
            if direction:
                range_hike = candle["volume"] > t1_range_avg
                last2_hike = all(candle["volume"] > v for v in prior["volume"].tolist())
                if range_hike and last2_hike:
                    candidates.append((candle, f"T1 {direction}", hi if direction == "Bullish" else lo, t1_range_avg, range_hike, last2_hike))

    # Extended range only exists after the 10:50-start candle is complete at 10:55.
    if t2_eligible and ((trading_date < now.date()) or now.time() >= time(10, 55)):
        extended = df[(df["timestamp"].dt.time >= time(9, 15)) & (df["timestamp"].dt.time < time(10, 55))]
        if len(extended) >= 20:
            t2_hi = float(extended["high"].max())
            t2_lo = float(extended["low"].min())
            t2_avg_vol = float(extended["volume"].mean())
            t2 = df[(df["timestamp"].dt.time >= time(11, 0)) & (df["timestamp"].dt.time < time(14, 45))]
            for _, candle in t2.iterrows():
                prior = df[df["timestamp"] < candle["timestamp"]].tail(2)
                if len(prior) < 2:
                    continue
                direction = "Bullish" if candle["close"] > t2_hi else ("Bearish" if candle["close"] < t2_lo else None)
                if direction:
                    range_hike = candle["volume"] > t2_avg_vol
                    last2_hike = all(candle["volume"] > v for v in prior["volume"].tolist())
                    if range_hike and last2_hike:
                        candidates.append((candle, f"T2 {direction}", t2_hi if direction == "Bullish" else t2_lo, t2_avg_vol, range_hike, last2_hike))

    # First qualifying signal per stock is returned. The UI can be rerun without duplicating rows.
    if not candidates:
        return {
            "symbol": row["symbol"], "sector": row["sector"], "signal": "No signal",
            "trigger_time": "", "close": float(df.iloc[-1]["close"]),
            "breakout_level": None, "range_high": hi, "range_low": lo,
            "candle_volume": None, "range_avg_volume": avg_open_vol,
            "range_volume_hike": False, "last_two_volume_hike": False,
            "volume_ratio": None,
            "note": "T1 not eligible / T2 not eligible / no confirmed close+volume breakout",
        }

    candle, signal, level, avg_vol, range_hike, last2_hike = sorted(candidates, key=lambda x: x[0]["timestamp"])[0]
    return {
        "symbol": row["symbol"], "sector": row["sector"], "signal": signal,
        "trigger_time": _fmt(candle["timestamp"]), "close": round(float(candle["close"]), 2),
        "breakout_level": round(float(level), 2), "range_high": round(hi, 2),
        "range_low": round(lo, 2), "candle_volume": int(candle["volume"]),
        "range_avg_volume": round(float(avg_vol), 2),
        "range_volume_hike": bool(range_hike), "last_two_volume_hike": bool(last2_hike),
        "volume_ratio": round(float(candle["volume"]) / avg_vol, 2) if avg_vol else None,
        "note": "Confirmed completed-candle signal",
    }
