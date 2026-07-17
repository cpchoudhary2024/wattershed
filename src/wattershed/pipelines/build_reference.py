"""National reference build: assemble the committed tract-indicator table.

Steps (each independently cached; safe to re-run):
  1. Census 2024 gazetteer — tract population-weighted centroids
  2. ACS 2019–2023 bulk summary files — socioeconomic indicators
  3. CDC PLACES 2024 — health indicators
  4. EJScreen 2.32 replica — frozen pollution-burden fields
  5. FRS national — TRI facility table + per-tract 5 km counts
  6. Aqueduct 4.0 — U.S. extract + per-tract BWS category
  7. merge → national percentiles → CBI → parquet + manifest

Output: data/processed/tract_indicators.parquet (+ reference_manifest.json)
"""

from __future__ import annotations

import json
import zipfile
from datetime import date

import numpy as np
import pandas as pd

from .. import config, provenance
from ..sources import acs, aqueduct, ejscreen_legacy, frs, places
from ..sources.base import cached_download
from ..scoring.reference import PERCENTILED_COLS, POLLUTION_COLS, VULNERABILITY_COLS

_GAZ_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
    "2024_Gaz_tracts_national.zip"
)


def _log(msg: str) -> None:
    print(f"[build-reference] {msg}", flush=True)


def load_gazetteer() -> pd.DataFrame:
    p = cached_download(_GAZ_URL, "gaz_tracts_national.zip", "census_gazetteer_2024")
    with zipfile.ZipFile(p) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt"))
        with z.open(name) as f:
            df = pd.read_csv(f, sep="\t", dtype={"GEOID": str})
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(
        columns={"GEOID": "geoid", "INTPTLAT": "intptlat", "INTPTLONG": "intptlon", "ALAND": "aland_m2"}
    )
    df["geoid"] = df["geoid"].str.zfill(11)
    return df[["geoid", "intptlat", "intptlon", "aland_m2"]]


def _ecef(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray:
    """Unit-sphere ECEF coordinates (km) — keeps KDTree distances valid for
    AK/HI/PR, unlike a CONUS-only projection."""
    R = 6371.0088
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    return np.c_[
        R * np.cos(lat) * np.cos(lon),
        R * np.cos(lat) * np.sin(lon),
        R * np.sin(lat),
    ]


def tri_counts_for_tracts(gaz: pd.DataFrame) -> pd.DataFrame:
    """TRI facilities within 5 km of each tract's population-weighted centroid."""
    from scipy.spatial import cKDTree

    tri = frs.tri_facilities()
    if tri is None:
        frs.build_tri_facility_table()
        tri = frs.tri_facilities()
    tree = cKDTree(_ecef(tri["lat"].values, tri["lon"].values))
    pts = _ecef(gaz["intptlat"].values, gaz["intptlon"].values)
    # chord distance for a 5 km arc (identical to 6 decimal places at this scale)
    R = 6371.0088
    chord = 2 * R * np.sin(config.PROXIMITY_RADIUS_KM / (2 * R))
    counts = tree.query_ball_point(pts, r=chord, return_length=True)
    return pd.DataFrame({"geoid": gaz["geoid"].values, "tri_count_5km": counts.astype(float)})


def bws_for_tracts(gaz: pd.DataFrame) -> pd.DataFrame:
    """Aqueduct BWS category at each tract centroid (spatial join)."""
    import geopandas as gpd

    if not aqueduct.EXTRACT_PATH.exists():
        _log("building Aqueduct US extract (261 MB download, one-time)…")
        aqueduct.build_us_extract()
    basins = gpd.read_file(aqueduct.EXTRACT_PATH)[["bws_cat", "bws_label", "geometry"]]
    pts = gpd.GeoDataFrame(
        gaz[["geoid"]],
        geometry=gpd.points_from_xy(gaz["intptlon"], gaz["intptlat"]),
        crs=4326,
    )
    joined = gpd.sjoin(pts, basins, how="left", predicate="within")
    out = joined[["geoid", "bws_cat", "bws_label"]].drop_duplicates("geoid")
    return out


def build(skip_aqueduct: bool = False) -> None:
    started = provenance.utc_now_iso()
    _log("1/7 gazetteer…")
    gaz = load_gazetteer()
    _log(f"    {len(gaz):,} tracts")

    _log("2/7 ACS bulk summary files…")
    demo = acs.build_tract_demographics()
    _log(f"    {len(demo):,} tract rows")

    _log("3/7 CDC PLACES…")
    health = places.build_tract_health()
    _log(f"    {len(health):,} tract rows")

    _log("4/7 EJScreen 2.32 replica (paged feature service)…")
    ej = ejscreen_legacy.fetch_all()
    _log(f"    {len(ej):,} tract rows")

    _log("5/7 FRS → TRI facility table + per-tract counts…")
    frs.build_tri_facility_table()
    tric = tri_counts_for_tracts(gaz)
    _log(f"    {int((tric['tri_count_5km']>0).sum()):,} tracts with ≥1 TRI facility in 5 km")

    if skip_aqueduct:
        bws = pd.DataFrame({"geoid": gaz["geoid"], "bws_cat": np.nan, "bws_label": None})
    else:
        _log("6/7 Aqueduct BWS per tract…")
        bws = bws_for_tracts(gaz)

    _log("7/7 merge + national percentiles…")
    df = gaz.merge(demo, on="geoid", how="left")
    df = df.merge(health, on="geoid", how="left")
    df = df.merge(ej.drop(columns=["population"], errors="ignore"), on="geoid", how="left")
    df = df.merge(tric, on="geoid", how="left")
    df = df.merge(bws, on="geoid", how="left")

    # national percentiles for every scored indicator (higher = more concern).
    # Tracts with zero population are excluded from rank basis but keep values.
    pop = df["population"].fillna(0)
    rank_base = pop > 0
    pct_cols = {}
    for col in PERCENTILED_COLS:
        if col not in df.columns:
            df[col] = np.nan
        s = df.loc[rank_base, col]
        pct = s.rank(pct=True, method="average") * 100
        pct_cols[f"p_{col}"] = pct.reindex(df.index)
    df = pd.concat([df, pd.DataFrame(pct_cols, index=df.index)], axis=1)

    # domain means + multiplicative CBI + its national percentile
    p_poll = df[[f"p_{c}" for c in POLLUTION_COLS]]
    p_vuln = df[[f"p_{c}" for c in VULNERABILITY_COLS]]
    poll_ok = p_poll.notna().sum(axis=1) >= 5
    vuln_ok = p_vuln.notna().sum(axis=1) >= 4
    df["pollution_domain"] = p_poll.mean(axis=1).where(poll_ok)
    df["vulnerability_domain"] = p_vuln.mean(axis=1).where(vuln_ok)
    df["cbi"] = df["pollution_domain"] * df["vulnerability_domain"] / 100.0
    cbi_rank = df.loc[rank_base, "cbi"].rank(pct=True, method="average") * 100
    df["p_cbi"] = cbi_rank.reindex(df.index)

    out = config.PROCESSED_DIR / "tract_indicators.parquet"
    df.to_parquet(out, index=False)
    _log(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB, {len(df):,} rows)")

    manifest = {
        "built_at": provenance.utc_now_iso(),
        "started_at": started,
        "build_date": date.today().isoformat(),
        "rows": int(len(df)),
        "tracts_with_population": int(rank_base.sum()),
        "columns": sorted(df.columns.tolist()),
        "coverage": {
            c: round(100 * float(df.loc[rank_base, c].notna().mean()), 1)
            for c in PERCENTILED_COLS + ["bws_cat"]
        },
        "sources": provenance.Ledger(
            entries={
                sid: provenance.utc_now_iso()
                for sid in [
                    "census_gazetteer_2024", "acs_2023_5yr", "cdc_places_2024",
                    "ejscreen_v232_replica", "frs_national", "aqueduct40",
                ]
            }
        ).to_records(),
    }
    (config.PROCESSED_DIR / "reference_manifest.json").write_text(json.dumps(manifest, indent=2))
    _log("manifest written; done.")


if __name__ == "__main__":
    build()
