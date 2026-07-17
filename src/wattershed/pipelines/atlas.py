"""National Siting Pressure Atlas: every U.S. county scored on the three
pillars, computed entirely from the committed reference artifacts.

This is the tool's original empirical contribution: an open, reproducible,
national map of where data-center siting pressure concentrates — structural
water stress, grid carbon & adequacy strain, and community burden — at
county resolution. No demand escalators apply (no project is assumed); the
county tier is the pure location signal.

Method notes (mirrors the site pipeline; differences are honest coarsenings):
- water: Aqueduct 4.0 BWS category at the county's population-weighted
  centroid, mapped through the same base scores as site screening. Drought
  climatology is omitted at atlas scale (3,100 county API calls) — flagged
  in the atlas legend; site screening always includes it.
- grid: eGRID subregion of the county centroid → rate percentile (60%) +
  NERC LTRA category (40%), same as sites.
- burden: population-weighted mean tract CBI percentile within the county.
"""

from __future__ import annotations


import numpy as np
import pandas as pd

from .. import config
from ..models import PillarScore
from ..scoring import reference
from ..scoring.tiers import assign_tier
from ..scoring.water import BWS_BASE_SCORE
from ..sources import egrid, nerc
from ..sources.base import cached_download, extract_zip

_COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_20m.zip"

ATLAS_PATH = config.PROCESSED_DIR / "county_atlas.csv"


def _county_centroids(tracts: pd.DataFrame) -> pd.DataFrame:
    t = tracts.copy()
    t["county"] = t["geoid"].str[:5]
    w = t["population"].fillna(0).clip(lower=0) + 1e-9

    def agg(g):
        ww = g["population"].fillna(0).clip(lower=0) + 1e-9
        return pd.Series(
            {
                "lat": np.average(g["intptlat"], weights=ww),
                "lon": np.average(g["intptlon"], weights=ww),
                "population": g["population"].fillna(0).sum(),
                "burden": (
                    np.average(
                        g["p_cbi"].fillna(g["p_cbi"].mean()),
                        weights=ww,
                    )
                    if g["p_cbi"].notna().any()
                    else np.nan
                ),
            }
        )

    _ = w  # weights computed per-group above
    return t.groupby("county").apply(agg, include_groups=False).reset_index()


def build_atlas() -> pd.DataFrame:
    import geopandas as gpd

    tracts = reference.table().reset_index(drop=True)
    counties = _county_centroids(tracts)

    pts = gpd.GeoDataFrame(
        counties,
        geometry=gpd.points_from_xy(counties["lon"], counties["lat"]),
        crs=4326,
    )

    # water: BWS category at county centroid
    basins = gpd.read_file(config.PROCESSED_DIR / "aqueduct_bws_us.gpkg")[["bws_cat", "geometry"]]
    j = gpd.sjoin(pts, basins, how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    counties["water"] = [
        BWS_BASE_SCORE.get(int(c)) if pd.notna(c) else None for c in j["bws_cat"]
    ]

    # grid: subregion at centroid -> same 60/40 blend as sites
    sub_gdf = egrid._subregions_gdf()
    j2 = gpd.sjoin(pts, sub_gdf, how="left", predicate="within")
    j2 = j2[~j2.index.duplicated(keep="first")]
    table = egrid.subregion_table().set_index("SUBRGN")
    grid_scores, subrgns = [], []
    for code in j2["SUBRGN"]:
        if pd.isna(code) or code not in table.index:
            grid_scores.append(None)
            subrgns.append(None)
            continue
        carbon = float(table.loc[code, "rate_percentile"])
        risk = nerc.risk_for_subregion(str(code))
        strain = risk["score"] if risk and risk.get("score") is not None else None
        score = 0.6 * carbon + 0.4 * strain if strain is not None else carbon
        grid_scores.append(round(score, 1))
        subrgns.append(str(code))
    counties["grid"] = grid_scores
    counties["subrgn"] = subrgns

    # tier from pure location signal (no demand escalators)
    tiers = []
    for _, r in counties.iterrows():
        t, _reasons = assign_tier(
            PillarScore(pillar="water", score=r["water"], band=""),
            PillarScore(pillar="grid", score=r["grid"], band=""),
            PillarScore(pillar="burden", score=None if pd.isna(r["burden"]) else float(r["burden"]), band=""),
        )
        tiers.append(t.value)
    counties["tier"] = tiers
    counties["burden"] = counties["burden"].round(1)

    out = counties[["county", "lat", "lon", "population", "water", "grid", "burden", "subrgn", "tier"]]
    out.to_csv(ATLAS_PATH, index=False)
    return out


def county_shapes() -> "object":
    """County polygons (cartographic 20m) keyed by FIPS, for the dashboard."""
    import geopandas as gpd

    zp = cached_download(_COUNTY_URL, "cb_2024_us_county_20m.zip", "census_gazetteer_2024")
    d = extract_zip(zp, "cb_counties")
    shp = sorted(d.rglob("*.shp"))[0]
    gdf = gpd.read_file(shp)
    gdf = gdf[~gdf["STATEFP"].isin(["72", "60", "66", "69", "78", "02", "15"])]
    gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
    return gdf


def build_manifest_note() -> dict:
    return {
        "built_from": "committed reference artifacts (tract_indicators.parquet, aqueduct_bws_us.gpkg, eGRID2023, NERC LTRA table)",
        "drought_climatology": "omitted at atlas scale; included in site screening",
        "escalators": "none — pure location signal",
    }


if __name__ == "__main__":
    df = build_atlas()
    print(f"atlas: {len(df)} counties -> {ATLAS_PATH}")
    print(df["tier"].value_counts().to_string())
