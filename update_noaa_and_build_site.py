#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update NOAA GHCN-Daily data (.dly) + rebuild dashboard datasets.

Robustness improvements:
  - Retry + backoff on transient HTTP errors (503, 502, 504, 429, etc.)
  - Fallback to cached local .dly if NOAA is unavailable
  - If neither works, exit 0 (no-op) so the site stays up
  - FIX: convert date column to pandas datetime before filtering vs START_DATE
"""

import os
import sys
import time
import json
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

STATION_ID = os.environ.get("GHCN_STATION_ID", "USW00013743")  # Reagan National (proxy)
START_DATE = dt.date(1995, 1, 1)

TIMEOUT_SECS = 60
PRIMARY_URL = f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{STATION_ID}.dly"
FALLBACK_URL = f"https://www1.ncdc.noaa.gov/pub/data/ghcn/daily/all/{STATION_ID}.dly"

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

RAW_DLY_PATH = RAW_DIR / f"{STATION_ID}.dly"

OUT_DAILY_CSV = DATA_DIR / "arlington_daily.csv"
OUT_CLIM_PCTL = DATA_DIR / "climatology_doy365_percentiles.csv"
OUT_META = DATA_DIR / "meta.json"

VARS = ["TMIN", "TMAX", "PRCP", "SNOW", "SNWD"]


def fetch_with_retries(url: str, retries: int = 6, backoff_base: float = 1.7):
    headers = {
        "User-Agent": "arlington-weather-dashboard/1.0 (GitHub Actions)",
        "Accept": "*/*",
        "Connection": "close",
    }
    last_err = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT_SECS)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                wait = (backoff_base ** i) + (0.15 * i)
                print(f"[WARN] HTTP {r.status_code} from {url}. Retry {i+1}/{retries} in {wait:.1f}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            wait = (backoff_base ** i) + (0.15 * i)
            print(f"[WARN] Request error: {e}. Retry {i+1}/{retries} in {wait:.1f}s")
            time.sleep(wait)

    print(f"[ERROR] Failed to fetch after {retries} retries: {url}")
    if last_err:
        print(f"[ERROR] Last error: {last_err}")
    return None


def fetch_dly_text():
    r = fetch_with_retries(PRIMARY_URL)
    if r is None:
        print("[INFO] Trying fallback NOAA host...")
        r = fetch_with_retries(FALLBACK_URL)
    if r is None:
        return None
    return r.text


def parse_dly_to_df(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        st = line[0:11]
        year = int(line[11:15])
        month = int(line[15:17])
        element = line[17:21]
        if element not in VARS:
            continue

        for d in range(1, 32):
            base = 21 + (d - 1) * 8
            val = int(line[base:base + 5])
            qflag = line[base + 6:base + 7]

            try:
                date = dt.date(year, month, d)
            except ValueError:
                continue

            if val == -9999:
                rows.append((st, date, element, None))
                continue

            if qflag.strip() != "":
                rows.append((st, date, element, None))
            else:
                rows.append((st, date, element, val))

    return pd.DataFrame(rows, columns=["station", "date", "element", "raw"])


def wide_and_convert(df_long: pd.DataFrame) -> pd.DataFrame:
    wide = df_long.pivot_table(
        index=["station", "date"],
        columns="element",
        values="raw",
        aggfunc="first"
    ).reset_index().sort_values("date").reset_index(drop=True)

    def c10(x):
        return x / 10.0 if pd.notna(x) else pd.NA

    out = pd.DataFrame({
        "date": pd.to_datetime(wide["date"], errors="coerce"),  # FIX
        "Tmin_C": wide.get("TMIN").map(c10),
        "Tmax_C": wide.get("TMAX").map(c10),
        "PRCP_mm": wide.get("PRCP").map(c10),
        "SNOW_mm": wide.get("SNOW").map(c10),
        "SNWD_mm": wide.get("SNWD"),
    })

    out["Tavg_C"] = (out["Tmin_C"] + out["Tmax_C"]) / 2.0

    start_ts = pd.Timestamp(START_DATE)  # FIX
    out = out[out["date"] >= start_ts].copy()

    out["Year"] = out["date"].dt.year
    out["month"] = out["date"].dt.month
    out["day"] = out["date"].dt.day
    
    # Add DOY_365 column
    out["DOY_365"] = out["date"].map(to_doy365)
    
    return out


def impute_one_day_gaps(df: pd.DataFrame, cols):
    df = df.sort_values("date").reset_index(drop=True)
    for col in cols:
        s = df[col].astype("Float64")
        for i in range(1, len(df) - 1):
            if pd.isna(s.iloc[i]) and pd.notna(s.iloc[i - 1]) and pd.notna(s.iloc[i + 1]):
                d0 = df.loc[i - 1, "date"]
                d1 = df.loc[i, "date"]
                d2 = df.loc[i + 1, "date"]
                if pd.notna(d0) and pd.notna(d1) and pd.notna(d2):
                    if (d1 - d0).days == 1 and (d2 - d1).days == 1:
                        s.iloc[i] = (s.iloc[i - 1] + s.iloc[i + 1]) / 2.0
        df[col] = s
    df["Tavg_C"] = (df["Tmin_C"] + df["Tmax_C"]) / 2.0
    return df


def to_doy365(ts) -> int:
    date = pd.to_datetime(ts)
    doy = int(date.dayofyear)
    if date.month == 2 and date.day == 29:
        return 59
    if date.is_leap_year and date.month > 2:
        doy -= 1
    return doy


def build_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    metrics = ["Tmin_C", "Tmax_C", "Tavg_C", "PRCP_mm", "SNOW_mm", "SNWD_mm"]
    tmp = df.copy()
    tmp["DOY_365"] = tmp["date"].map(to_doy365)

    rows = []
    for doy, g in tmp.groupby("DOY_365"):
        row = {"DOY_365": int(doy)}
        for m in metrics:
            vals = g[m].dropna().astype(float)
            if len(vals) == 0:
                row[f"{m}_p10"] = pd.NA
                row[f"{m}_p50"] = pd.NA
                row[f"{m}_p90"] = pd.NA
            else:
                row[f"{m}_p10"] = float(vals.quantile(0.10))
                row[f"{m}_p50"] = float(vals.quantile(0.50))
                row[f"{m}_p90"] = float(vals.quantile(0.90))
        rows.append(row)

    return pd.DataFrame(rows).sort_values("DOY_365").reset_index(drop=True)


def write_outputs(df_daily: pd.DataFrame, df_pctl: pd.DataFrame):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df_daily.to_csv(OUT_DAILY_CSV, index=False)
    df_pctl.to_csv(OUT_CLIM_PCTL, index=False)

    meta = {
        "station_id": STATION_ID,
        "start_date": str(START_DATE),
        "last_date": str(df_daily["date"].max().date()) if len(df_daily) else None,
        "generated_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "notes": "If NOAA is temporarily unavailable, workflow will no-op and keep previous datasets."
    }
    OUT_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main():
    print(f"[INFO] Station: {STATION_ID}")
    print(f"[INFO] Fetching: {PRIMARY_URL}")
    text = fetch_dly_text()

    if text is None:
        if RAW_DLY_PATH.exists():
            print(f"[WARN] NOAA unavailable. Using cached .dly: {RAW_DLY_PATH}")
            text = RAW_DLY_PATH.read_text(encoding="utf-8", errors="ignore")
        else:
            print("[WARN] NOAA unavailable and no cached .dly found. No-op (exit 0)." )
            return 0

    RAW_DLY_PATH.write_text(text, encoding="utf-8")

    df_long = parse_dly_to_df(text)
    df_daily = wide_and_convert(df_long)
    df_daily = impute_one_day_gaps(df_daily, ["Tmin_C", "Tmax_C", "PRCP_mm", "SNOW_mm", "SNWD_mm"])

    df_pctl = build_percentiles(df_daily)
    write_outputs(df_daily, df_pctl)

    print(f"[OK] Wrote: {OUT_DAILY_CSV}")
    print(f"[OK] Wrote: {OUT_CLIM_PCTL}")
    print(f"[OK] Wrote: {OUT_META}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
