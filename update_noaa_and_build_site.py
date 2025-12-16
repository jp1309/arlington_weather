#!/usr/bin/env python3
"""Update NOAA GHCN-Daily data for USW00013743 and build dashboard CSVs including p10/p50/p90 percentiles by DOY_365."""

from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Tuple, Optional, Set
import numpy as np
import pandas as pd
import requests

STATION_ID = "USW00013743"
DLY_URL = f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{STATION_ID}.dly"
START = date(1995, 1, 1)
MISSING = -9999

ELEMENTS: Set[str] = {"TMIN","TMAX","TAVG","PRCP","SNOW","SNWD"}
DIV10 = {"TMIN","TMAX","TAVG","PRCP"}
DIV1 = {"SNOW","SNWD"}

OUT_DIR = Path("data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def parse_dly_line(line: str) -> Tuple[str,int,int,str,Dict[int,int]]:
    station = line[0:11]
    year = int(line[11:15])
    month = int(line[15:17])
    element = line[17:21]
    values: Dict[int,int] = {}
    pos = 21
    for day in range(1,32):
        values[day] = int(line[pos:pos+5])
        pos += 8
    return station, year, month, element, values

def fetch_dly_text() -> str:
    r = requests.get(DLY_URL, timeout=180)
    r.raise_for_status()
    return r.text

def convert_value(element: str, raw: int) -> Optional[float]:
    if raw == MISSING:
        return None
    if element in DIV10:
        return raw/10.0
    if element in DIV1:
        return float(raw)
    return float(raw)

def build_series(text: str) -> Tuple[Dict[date,Dict[str,float]], date]:
    series: Dict[date,Dict[str,float]] = {}
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
        raise RuntimeError("No data found")
    return series, last_date

def ensure_full_range(series: Dict[date,Dict[str,float]], start: date, end: date) -> None:
    d = start
    while d <= end:
        series.setdefault(d, {})
        d += timedelta(days=1)

def interpolate_temps(series: Dict[date,Dict[str,float]], start: date, end: date) -> Dict[date,Set[str]]:
    imputados: Dict[date,Set[str]] = {}
    d = start + timedelta(days=1)
    while d < end:
        prev = series.get(d - timedelta(days=1), {})
        nxt  = series.get(d + timedelta(days=1), {})
        rec  = series.setdefault(d, {})
        for el in ("TMIN","TMAX"):
            if el not in rec and (el in prev) and (el in nxt):
                rec[el] = (prev[el] + nxt[el]) / 2.0
                imputados.setdefault(d, set()).add(el)
        d += timedelta(days=1)
    return imputados

def build_df(series: Dict[date,Dict[str,float]], imputados: Dict[date,Set[str]], start: date, end: date) -> pd.DataFrame:
    rows = []
    d = start
    while d <= end:
        rec = series.get(d, {})
        tmin = rec.get("TMIN")
        tmax = rec.get("TMAX")
        tavg = rec.get("TAVG")
        if tavg is None and (tmin is not None and tmax is not None):
            tavg = (tmin + tmax) / 2.0
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
            "ImputedTempFlag": 1 if d in imputados else 0
        })
        d += timedelta(days=1)
    df = pd.DataFrame(rows)
    is_leap = df["Date"].dt.is_leap_year
    doy366 = df["DOY_366"]
    df["DOY_365"] = doy366.astype(float)
    df.loc[is_leap & (doy366 > 59), "DOY_365"] = doy366[is_leap & (doy366 > 59)] - 1
    df.loc[(df["Date"].dt.month==2) & (df["Date"].dt.day==29), "DOY_365"] = np.nan
    return df

def write_outputs(df: pd.DataFrame) -> None:
    daily = df[["Date","Year","DOY_366","DOY_365","Tmin_C","Tmax_C","Tavg_C","PRCP_mm","SNOW_mm","SNWD_mm","ImputedTempFlag"]].copy()
    daily["Date"] = daily["Date"].dt.strftime("%Y-%m-%d")
    daily.to_csv(OUT_DIR/"arlington_daily.csv", index=False)

    base = df.dropna(subset=["DOY_365"]).copy()
    cols = ["Tmin_C","Tmax_C","Tavg_C","PRCP_mm"]
    def quant(p):
        q = base.groupby("DOY_365")[cols].quantile(p, interpolation="linear").reset_index()
        q.rename(columns={c: f"{c}_p{int(p*100)}" for c in cols}, inplace=True)
        return q
    p10 = quant(0.10)
    p50 = quant(0.50)
    p90 = quant(0.90)
    pct = p10.merge(p50, on="DOY_365").merge(p90, on="DOY_365").sort_values("DOY_365")

    # normalize column names to *_p10/_p50/_p90 for JS
    pct.rename(columns={
        "Tmin_C_p10":"Tmin_C_p10","Tmin_C_p50":"Tmin_C_p50","Tmin_C_p90":"Tmin_C_p90",
        "Tmax_C_p10":"Tmax_C_p10","Tmax_C_p50":"Tmax_C_p50","Tmax_C_p90":"Tmax_C_p90",
        "Tavg_C_p10":"Tavg_C_p10","Tavg_C_p50":"Tavg_C_p50","Tavg_C_p90":"Tavg_C_p90",
        "PRCP_mm_p10":"PRCP_mm_p10","PRCP_mm_p50":"PRCP_mm_p50","PRCP_mm_p90":"PRCP_mm_p90",
    }, inplace=True)

    pct.to_csv(OUT_DIR/"climatology_doy365_percentiles.csv", index=False)

    try:
        daily.to_excel(OUT_DIR/"arlington_daily_latest.xlsx", index=False)
    except Exception:
        pass

def main():
    text = fetch_dly_text()
    series, last_date = build_series(text)
    ensure_full_range(series, START, last_date)
    imputados = interpolate_temps(series, START, last_date)
    df = build_df(series, imputados, START, last_date)
    write_outputs(df)
    print("OK", START, "->", last_date, "rows", len(df))

if __name__ == "__main__":
    main()
