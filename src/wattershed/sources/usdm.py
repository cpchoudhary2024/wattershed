"""U.S. Drought Monitor.

Two signals with different epistemics, kept separate on purpose:
- current weekly category at the point (transient screening trigger)
- 5-year county drought climatology (structural recurrence), summarized with
  the mean DSCI (Drought Severity and Coverage Index, 0–500), the metric NDMC
  itself publishes for time-aggregation.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from .base import cached_download, extract_zip, fetch_text

_SHAPE_URL = "https://droughtmonitor.unl.edu/data/shapefiles_m/USDM_current_M.zip"
_COUNTY_API = (
    "https://usdmdataservices.unl.edu/api/CountyStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
)

CATEGORY_LABELS = {
    None: "None",
    0: "D0 Abnormally Dry",
    1: "D1 Moderate Drought",
    2: "D2 Severe Drought",
    3: "D3 Extreme Drought",
    4: "D4 Exceptional Drought",
}


def current_drought(lat: float, lon: float) -> dict:
    """Return {'category': int|None, 'map_date': 'YYYY-MM-DD'} for the point."""
    zip_path = cached_download(_SHAPE_URL, "usdm_current.zip", "usdm_current", max_age_days=3)
    shp_dir = extract_zip(zip_path, "usdm_current")
    shps = sorted(shp_dir.glob("USDM_*.shp"))
    if not shps:
        shps = sorted(shp_dir.glob("*.shp"))
    shp = shps[-1]
    m = re.search(r"(\d{8})", shp.name)
    map_date = (
        f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else "unknown"
    )
    gdf = gpd.read_file(shp)
    pt = Point(lon, lat)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    hits = gdf[gdf.contains(pt)]
    # USDM ships one polygon per category; take the worst containing category
    # so the result is correct under either exclusive or cumulative topology.
    category = int(hits["DM"].max()) if len(hits) else None
    return {"category": category, "map_date": map_date}


def county_drought_history(county_fips: str, years: int = 5) -> dict:
    """5-year drought climatology for a county.

    Returns mean DSCI (0–500) and the share of weeks with ≥10% of the county
    in D2+ (severe or worse). The 10% floor ignores boundary slivers.
    """
    end = date.today()
    start = end - timedelta(days=round(years * 365.25))
    txt = fetch_text(
        _COUNTY_API,
        params={
            "aoi": county_fips,
            "startdate": start.strftime("%m/%d/%Y"),
            "enddate": end.strftime("%m/%d/%Y"),
            "statisticsType": "1",
        },
    )
    df = pd.read_csv(io.StringIO(txt))
    if df.empty:
        return {"mean_dsci": None, "pct_weeks_d2plus": None, "weeks": 0}
    for c in ["None", "D0", "D1", "D2", "D3", "D4"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # Categories are exclusive area percentages summing to ~100.
    dsci = 1 * df["D0"] + 2 * df["D1"] + 3 * df["D2"] + 4 * df["D3"] + 5 * df["D4"]
    d2plus_share = (df["D2"] + df["D3"] + df["D4"]) >= 10.0
    return {
        "mean_dsci": float(dsci.mean()),
        "pct_weeks_d2plus": float(100.0 * d2plus_share.mean()),
        "weeks": int(len(df)),
        "window": f"{start.isoformat()} → {end.isoformat()}",
    }
