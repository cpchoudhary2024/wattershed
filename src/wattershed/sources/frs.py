"""EPA Facility Registry Service — geocoded facility universe.

Used two ways:
- reference build: national per-tract TRI proximity counts (committed table)
- screening time: live list of named TRI facilities within the 5 km radius,
  so a report can say *which* facilities surround the site, not just a count.

TRI linkage (program acronym TRIS) identifies facilities that meet Toxics
Release Inventory reporting thresholds — an imperfect but standard proxy for
sustained industrial pollution sources (see LIMITATIONS.md).
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config
from .base import cached_download, extract_zip

_NATIONAL_URL = "https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip"
TRI_TABLE = config.PROCESSED_DIR / "tri_facilities.csv.gz"

EARTH_R_KM = 6371.0088


def build_tri_facility_table() -> Path:
    """One-time: filter the national FRS file to TRI-linked facilities with
    usable coordinates; write the compact committed table."""
    zp = cached_download(_NATIONAL_URL, "frs_national_single.zip", "frs_national")
    d = extract_zip(zp, "frs_national")
    csv_path = sorted(d.rglob("*.CSV")) + sorted(d.rglob("*.csv"))
    src = csv_path[0]
    keep_rows = []
    with open(src, encoding="latin-1", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pgms = row.get("PGM_SYS_ACRNMS") or ""
            if "TRIS" not in pgms:
                continue
            lat, lon = row.get("LATITUDE83"), row.get("LONGITUDE83")
            if not lat or not lon:
                continue
            keep_rows.append(
                {
                    "registry_id": row.get("REGISTRY_ID"),
                    "name": (row.get("PRIMARY_NAME") or "").title()[:80],
                    "city": (row.get("CITY_NAME") or "").title(),
                    "state": row.get("STATE_CODE"),
                    "lat": float(lat),
                    "lon": float(lon),
                }
            )
    df = pd.DataFrame(keep_rows).dropna(subset=["lat", "lon"])
    df = df[(df.lat.between(-15, 72)) & (df.lon.between(-180, -60) | df.lon.between(140, 180))]
    TRI_TABLE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRI_TABLE, index=False, compression="gzip")
    return TRI_TABLE


@lru_cache(maxsize=1)
def tri_facilities() -> pd.DataFrame | None:
    if not TRI_TABLE.exists():
        return None
    return pd.read_csv(TRI_TABLE, compression="gzip")


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def tri_near(lat: float, lon: float, radius_km: float = config.PROXIMITY_RADIUS_KM) -> dict | None:
    df = tri_facilities()
    if df is None:
        return None
    # cheap bbox prefilter, then exact haversine
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.2, np.cos(np.radians(lat))))
    sub = df[(df.lat.between(lat - dlat, lat + dlat)) & (df.lon.between(lon - dlon, lon + dlon))].copy()
    if sub.empty:
        return {"count": 0, "nearest": [], "radius_km": radius_km}
    sub["dist_km"] = haversine_km(lat, lon, sub.lat.values, sub.lon.values)
    sub = sub[sub.dist_km <= radius_km].sort_values("dist_km")
    return {
        "count": int(len(sub)),
        "radius_km": radius_km,
        "nearest": [
            {"name": r["name"], "city": r["city"], "state": r["state"], "dist_km": round(float(r["dist_km"]), 2)}
            for _, r in sub.head(8).iterrows()
        ],
    }
