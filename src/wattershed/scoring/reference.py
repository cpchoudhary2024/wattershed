"""National tract reference table: the committed artifact that makes
screening keyless, offline-capable, and reproducible.

Built once by `wattershed build-reference` (see pipelines/build_reference.py),
which fetches every national input from primary sources, merges on tract
GEOID, and computes national percentile ranks. The committed parquet ships
with the repo so a fresh clone can screen any U.S. point immediately; anyone
can regenerate it and diff.

Percentile convention: percentile = share of U.S. tracts with a value less
than or equal to this tract's, oriented so HIGHER percentile = MORE concern.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from .. import config

TABLE_PATH = config.PROCESSED_DIR / "tract_indicators.parquet"

POLLUTION_COLS = [
    "pm25",
    "ozone",
    "no2",
    "diesel_pm",
    "rsei_air_toxics",
    "traffic_proximity",
    "npl_proximity",
    "rmp_proximity",
    "tsdf_proximity",
    "tri_count_5km",
]
VULNERABILITY_COLS = [
    "pct_low_income",
    "pct_unemployed",
    "pct_limited_english_hh",
    "pct_no_hs_diploma",
    "pct_adult_asthma",
    "pct_fair_poor_health",
]
PERCENTILED_COLS = POLLUTION_COLS + VULNERABILITY_COLS


class ReferenceUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def table() -> pd.DataFrame:
    if not TABLE_PATH.exists():
        raise ReferenceUnavailable(
            f"Reference table missing at {TABLE_PATH}. Run `wattershed build-reference` "
            "or restore the committed artifact."
        )
    df = pd.read_parquet(TABLE_PATH)
    df["geoid"] = df["geoid"].astype(str).str.zfill(11)
    return df.set_index("geoid", drop=False)


def tract_row(geoid: str) -> pd.Series | None:
    t = table()
    return t.loc[geoid] if geoid in t.index else None


def pct_col(col: str) -> str:
    return f"p_{col}"


def domain_scores(row: pd.Series) -> dict:
    """Pollution (P), vulnerability (V), and combined CBI for one tract."""
    p_vals = [row.get(pct_col(c)) for c in POLLUTION_COLS]
    v_vals = [row.get(pct_col(c)) for c in VULNERABILITY_COLS]
    p_have = [v for v in p_vals if v is not None and not np.isnan(v)]
    v_have = [v for v in v_vals if v is not None and not np.isnan(v)]
    # coverage floors: refuse to synthesize a domain from too few indicators
    P = float(np.mean(p_have)) if len(p_have) >= 5 else None
    V = float(np.mean(v_have)) if len(v_have) >= 4 else None
    cbi = (P * V / 100.0) if (P is not None and V is not None) else None
    cbi_pct = None
    if cbi is not None:
        cbi_pct = float(row.get("p_cbi")) if not np.isnan(row.get("p_cbi", np.nan)) else None
    return {
        "pollution": P,
        "vulnerability": V,
        "cbi": cbi,
        "cbi_percentile": cbi_pct,
        "pollution_n": len(p_have),
        "vulnerability_n": len(v_have),
    }


def neighborhood(lat: float, lon: float, radius_km: float | None = None) -> dict | None:
    """Population-weighted burden summary over tracts whose population-weighted
    centroid falls within the radius. Centroid membership is an approximation
    (documented in LIMITATIONS.md) that avoids shipping national tract
    polygons."""
    radius_km = radius_km or config.NEIGHBORHOOD_RADIUS_KM
    t = table()
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    tlat, tlon = np.radians(t["intptlat"].values), np.radians(t["intptlon"].values)
    a = (
        np.sin((tlat - lat_r) / 2) ** 2
        + np.cos(lat_r) * np.cos(tlat) * np.sin((tlon - lon_r) / 2) ** 2
    )
    dist = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
    # populated tracts only — matches the scoring basis in neighborhood_row(),
    # so the reported tract count never overstates what the score rests on
    sub = t[(dist <= radius_km) & (t["population"].fillna(0) > 0)]
    if sub.empty:
        return None
    w = sub["population"].values.astype(float)

    def wmean(col: str) -> float | None:
        v = sub[col].values.astype(float)
        m = ~np.isnan(v)
        if not m.any():
            return None
        return float(np.average(v[m], weights=w[m]))

    return {
        "radius_km": radius_km,
        "tracts": int(len(sub)),
        "population": int(w.sum()),
        "cbi_percentile": wmean("p_cbi"),
        "pct_low_income": wmean("pct_low_income"),
        "pct_people_of_color": wmean("pct_people_of_color"),
        "pct_adult_asthma": wmean("pct_adult_asthma"),
        "pm25": wmean("pm25"),
    }


def neighborhood_row(lat: float, lon: float, radius_km: float | None = None) -> tuple[pd.Series, dict] | None:
    """Synthetic 'tract-like' row: population-weighted means of every value and
    percentile column over tracts whose centroid lies within the radius.

    Used when a site's containing tract is unpopulated (industrial/special-use
    tracts have no percentile ranks): the burden question is about the people
    AROUND the parcel, so the neighborhood is the honest scoring unit. The
    weighted mean of percentiles is an approximation, not a true national
    percentile — callers must label it as such."""
    radius_km = radius_km or config.NEIGHBORHOOD_RADIUS_KM
    t = table()
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    tlat, tlon = np.radians(t["intptlat"].values), np.radians(t["intptlon"].values)
    a = (
        np.sin((tlat - lat_r) / 2) ** 2
        + np.cos(lat_r) * np.cos(tlat) * np.sin((tlon - lon_r) / 2) ** 2
    )
    dist = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
    sub = t[(dist <= radius_km) & (t["population"].fillna(0) > 0)]
    if sub.empty:
        return None
    w = sub["population"].values.astype(float)
    cols = (
        PERCENTILED_COLS
        + [pct_col(c) for c in PERCENTILED_COLS]
        + ["p_cbi", "pollution_domain", "vulnerability_domain", "cbi", "pct_people_of_color"]
    )
    out = {}
    for c in cols:
        v = sub[c].values.astype(float)
        m = ~np.isnan(v)
        out[c] = float(np.average(v[m], weights=w[m])) if m.any() else np.nan
    out["population"] = float(w.sum())
    meta = {"radius_km": radius_km, "tracts": int(len(sub)), "population": int(w.sum())}
    return pd.Series(out), meta


def build_manifest() -> dict | None:
    import json

    p = config.PROCESSED_DIR / "reference_manifest.json"
    return json.loads(p.read_text()) if p.exists() else None
