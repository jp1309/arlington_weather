#!/usr/bin/env python3
"""
Daily updater for Arlington VA proxy station (USW00013743).

Change in this version:
- START date moved to 1995-01-01 (≈30 years of daily data).

What it does:
1) Download NOAA GHCN-Daily .dly for the station.
2) Parse daily elements: TMIN, TMAX, TAVG, PRCP, SNOW, SNWD.
3) Build a daily dataset from START to the LAST available date in the .dly.
4) Impute missing TMIN/TMAX for intermediate days as average of previous and next day.
   If missing on the last day, do nothing (leave missing).
5) Compute Tavg:
    - Use TAVG if present.
    - Else compute (Tmin + Tmax)/2 when possible (including after imputation).
6) Write CSVs used by the static dashboard.
   Also writes an Excel snapshot (optional).

Output files (tracked in git):
  - data/arlington_daily.csv
  - data/climatology_doy365_mean.csv
  - data/arlington_daily_latest.xlsx

Run locally:
  python update_noaa_and_build_site.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Tuple, Optional, Set

import numpy as np
import pandas as pd
import requests

STATION_ID = "USW00013743"
STATION_NAME = "WASHINGTON REAGAN NATIONAL AIRPORT, VA US (proxy for Arlington, VA)"
DLY_URL = f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{STATION_ID}.dly"

# >>> MAIN CHANGE <<<
START = date(1995, 1, 1)

MISSING = -9999

ELEMENTS: Set[str] = {"TMIN", "TMAX", "TAVG", "PRCP", "SNOW", "SNWD"}
DIV10 = {"TMIN", "TMAX", "TAVG", "PRCP"}  # tenths of unit
DIV1 = {"SNOW", "SNWD"}                   # mm

# IMPORTANT:
# If your published site is at repo root, keep this as "data".
# If you publish from /dashboard_site, change to Path("dashboard_site")/"data".
OUT_DIR = Path("data")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_dly_line(line: str) -> Tuple[str, int, int, str, Dict[int, int]]:
    station = line[0:11]
    year = int(line[11:15])
    month = int(line[15:17])
    element = line[17:21]
    values: Dict[int, int] = {}
    pos = 21
    for day in range(1, 32):
        values[day] = int(line[pos:pos + 5])
        pos += 8  # 5 value + 3 flags
    return station, year, month, element, values


def fetch_dly_text() -> str:
    r = requests.get(DLY_URL, timeout=180)
    r.raise_for_status()
    return r.text


def convert_value(element: str, raw: int) -> Optional[float]:
    if raw == MISSING:
        return None
    if element in DIV10:
        return raw / 10.0
    if element in DIV1:
        return float(raw)
    return float(raw)


def build_series(text: str) -> Tuple[Dict[date, Dict[str, float]], date]:
    series: Dict[date, Dict[str, float]] = {}
    last_date: Optional[date] = None

    for line in text.splitlines():
        if not line.strip():
            continue
        station, yr, mo, element, vals = parse_dly_line(line)
        if station != STATION_ID or element not in ELEMENTS:
            continue

        for day, raw in vals.items():
            try:
                d = date(yr, mo, day)
            except ValueError:
                continue
            if d < START:
                continue
            v = convert_value(element, raw)
            if v is None:
                continue
            series.setdefault(d, {})[element] = v
            if last_date is None or d > last_date:
                last_date = d

    if last_date is None:
        raise RuntimeError(f"No valid observations found from {START.isoformat()} in the station .dly.")
    return series, last_date


def ensure_full_range(series: Dict[date, Dict[str, float]], start: date, end: date) -> None:
    d = start
    while d <= end:
        series.setdefault(d, {})
        d += timedelta(days=1)


def interpolate_temps(series: Dict[date, Dict[str, float]], start: date, end: date) -> Dict[date, Set[str]]:
    """Impute missing TMIN/TMAX for intermediate days only."""
    imputados: Dict[date, Set[str]] = {}

    # start+1 ... end-1. Never impute on last day.
    d = start + timedelta(days=1)
    while d < end:
        prev_d = d - timedelta(days=1)
        next_d = d + timedelta(days=1)

        rec = series.setdefault(d, {})
        prev = series.get(prev_d, {})
        nxt = series.get(next_d, {})

        for el in ("TMIN", "TMAX"):
            if el not in rec and (el in prev) and (el in nxt):
                rec[el] = (prev[el] + nxt[el]) / 2.0
                imputados.setdefault(d, set()).add(el)

        d += timedelta(days=1)

    return imputados


def build_dataframe(series: Dict[date, Dict[str, float]], imputados: Dict[date, Set[str]], start: date, end: date) -> pd.DataFrame:
    rows = []
    d = start
    while d <= end:
        rec = series.get(d, {})
        tmin = rec.get("TMIN")
        tmax = rec.get("TMAX")
        tavg = rec.get("TAVG")

        imputed_flag = 1 if d in imputados else 0

        notes = []
        if d in imputados:
            notes.append("Imputado: " + ",".join(sorted(imputados[d])) + " (avg prev/next)")

        # prefer official TAVG; else compute if possible
        if tavg is None and (tmin is not None and tmax is not None):
            tavg = (tmin + tmax) / 2.0
            notes.append("TAVG computed as (Tmin+Tmax)/2")

        rows.append({
            "Date": pd.Timestamp(d),
            "Year": d.year,
            "DOY_366": d.timetuple().tm_yday,
            "Tmin_C": tmin,
            "Tmax_C": tmax,
            "Tavg_C": tavg,
            "PRCP_mm": rec.get("PRCP"),
            "SNOW_mm": rec.get("SNOW"),
            "SNWD_mm": rec.get("SNWD"),
            "ImputedTempFlag": imputed_flag,
            "Station_ID": STATION_ID,
            "Station_Name": STATION_NAME,
            "Notes": " | ".join(notes)
        })
        d += timedelta(days=1)

    df = pd.DataFrame(rows)

    # DOY_365: remove Feb 29 and shift days after Feb 28 in leap years by -1
    is_leap = df["Date"].dt.is_leap_year
    doy366 = df["DOY_366"]
    df["DOY_365"] = doy366.astype("float")
    df.loc[is_leap & (doy366 > 59), "DOY_365"] = doy366[is_leap & (doy366 > 59)] - 1
    df.loc[(df["Date"].dt.month == 2) & (df["Date"].dt.day == 29), "DOY_365"] = np.nan

    return df


def write_outputs(df: pd.DataFrame) -> None:
    out_csv = OUT_DIR / "arlington_daily.csv"
    df_out = df[
        ["Date","Year","DOY_366","DOY_365","Tmin_C","Tmax_C","Tavg_C","PRCP_mm","SNOW_mm","SNWD_mm","ImputedTempFlag"]
    ].copy()
    df_out["Date"] = df_out["Date"].dt.strftime("%Y-%m-%d")
    df_out.to_csv(out_csv, index=False)

    clim = df.dropna(subset=["DOY_365"]).groupby("DOY_365")[["Tmin_C","Tmax_C","Tavg_C","PRCP_mm"]].mean().reset_index()
    clim.to_csv(OUT_DIR / "climatology_doy365_mean.csv", index=False)

    try:
        out_xlsx = OUT_DIR / "arlington_daily_latest.xlsx"
        df_out.to_excel(out_xlsx, index=False)
    except Exception as e:
        print("WARN: could not write Excel snapshot:", e)

    print("Wrote:")
    print(" -", out_csv)
    print(" -", OUT_DIR / "climatology_doy365_mean.csv")


def main():
    text = fetch_dly_text()
    series, last_date = build_series(text)
    ensure_full_range(series, START, last_date)
    imputados = interpolate_temps(series, START, last_date)
    df = build_dataframe(series, imputados, START, last_date)

    print("Start:", START.isoformat())
    print("Last date available:", last_date.isoformat())
    print("Rows:", len(df))
    print("Imputed temp days:", int(df["ImputedTempFlag"].sum()))

    write_outputs(df)


if __name__ == "__main__":
    main()
