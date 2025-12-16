#!/usr/bin/env python3
"""
Build dataset for GitHub Pages dashboard from your Excel.

Input (same folder by default):
- arlington_va_daily_2015_to_latest_C_interpolated.xlsx

Outputs:
- dashboard_site/data/arlington_daily.csv
- dashboard_site/data/climatology_doy365_mean.csv

Adds:
- Year
- DOY_366 (1..366)
- DOY_365 (1..365, Feb 29 removed and leap days shifted)
- ImputedTempFlag (1 if Notes contains 'Imputado')
"""

from pathlib import Path
import numpy as np
import pandas as pd

INPUT_XLSX = Path("arlington_va_daily_2015_to_latest_C_interpolated.xlsx")
OUT_DIR = Path("dashboard_site") / "data"

def main():
    df = pd.read_excel(INPUT_XLSX, sheet_name=0)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Year"] = df["Date"].dt.year
    df["DOY_366"] = df["Date"].dt.dayofyear

    is_leap = df["Date"].dt.is_leap_year
    is_feb29 = (df["Date"].dt.month == 2) & (df["Date"].dt.day == 29)

    df["DOY_365"] = df["DOY_366"]
    df.loc[is_leap & (df["DOY_366"] > 59), "DOY_365"] = df.loc[is_leap & (df["DOY_366"] > 59), "DOY_366"] - 1
    df.loc[is_feb29, "DOY_365"] = np.nan

    df["ImputedTempFlag"] = df.get("Notes", "").fillna("").astype(str).str.contains("Imputado", case=False).astype(int)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_cols = [
        "Date","Year","DOY_366","DOY_365",
        "Tmin_C","Tmax_C","Tavg_C","PRCP_mm","SNOW_mm","SNWD_mm",
        "ImputedTempFlag"
    ]
    df[out_cols].to_csv(OUT_DIR / "arlington_daily.csv", index=False)

    clim = df.dropna(subset=["DOY_365"]).groupby("DOY_365")[["Tmin_C","Tmax_C","Tavg_C","PRCP_mm"]].mean().reset_index()
    clim.to_csv(OUT_DIR / "climatology_doy365_mean.csv", index=False)

    print("OK. Wrote:")
    print(" -", OUT_DIR / "arlington_daily.csv")
    print(" -", OUT_DIR / "climatology_doy365_mean.csv")

if __name__ == "__main__":
    main()
