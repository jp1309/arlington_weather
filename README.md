# Arlington Weather Dashboard (GitHub Pages)

Static dashboard built with Plotly.js and a daily GitHub Action that refreshes NOAA data.

## What updates daily
The workflow downloads NOAA GHCN-Daily station **USW00013743** (Reagan National Airport, proxy for Arlington, VA),
rebuilds CSV datasets, and commits the updated files to the repository.

Output datasets (tracked in git):
- `dashboard_site/data/arlington_daily.csv`
- `dashboard_site/data/climatology_doy365_mean.csv`
- `dashboard_site/data/arlington_daily_latest.xlsx` (optional snapshot)

## Local run
```bash
pip install -r requirements.txt
python update_noaa_and_build_site.py
```

## Publish
Enable GitHub Pages:
Settings → Pages → Deploy from branch → `main` → `/dashboard_site`
