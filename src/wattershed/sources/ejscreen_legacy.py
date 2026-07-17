"""EJScreen 2.32 pollution-burden fields (community-restored replica).

EPA withdrew EJScreen from public access in February 2025. Five pollution
indicators whose upstream models are impractical to rebuild live (PM2.5,
ozone, diesel PM, air-toxics cancer risk, traffic proximity) plus three
siting-proximity indicators (NPL, RMP, TSDF) are pulled ONCE, at reference-
build time, from a restored copy of EPA's final 2.32 release, then frozen
into the committed tract table with their original vintages.

Primary access path: community-hosted ArcGIS FeatureServer of the 2.32
dataset (attribute-only paged queries; no geometry). Documented alternative:
the PEDP shapefile mirror on ArcGIS Hub (item 448f514d14204df7b4641e96a3fee52e).
"""

from __future__ import annotations

import pandas as pd

from .base import SourceUnavailable, fetch_json

_SERVICE = (
    "https://services.arcgis.com/lqRTrQp2HrfnJt8U/arcgis/rest/services/"
    "EJSCREEN_Full_with_AS_CNMI_GU_VI/FeatureServer/0/query"
)

FIELDS = {
    "ID": "id",
    "ACSTOTPOP": "population",
    "PM25": "pm25",
    "OZONE": "ozone",
    "NO2": "no2",
    "DSLPM": "diesel_pm",
    "RSEI_AIR": "rsei_air_toxics",
    "PTRAF": "traffic_proximity",
    "PNPL": "npl_proximity",
    "PRMP": "rmp_proximity",
    "PTSDF": "tsdf_proximity",
}


def fetch_all(page: int = 2000, max_pages: int = 200) -> pd.DataFrame:
    """Page the full attribute table (~85k tracts or ~240k block groups —
    detected from ID length and aggregated to tract, population-weighted).
    Result is cached to interim so rebuilds don't re-page the service."""
    from .. import config

    cache = config.INTERIM_DIR / "ejscreen_v232_tract.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    out_fields = ",".join(FIELDS)
    rows: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        data = fetch_json(
            _SERVICE,
            params={
                "where": "1=1",
                "outFields": out_fields,
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": page,
                "orderByFields": "ID",
            },
            timeout=180,
        )
        if "error" in data:
            raise SourceUnavailable(f"EJScreen service error: {data['error']}")
        feats = data.get("features", [])
        rows.extend(f["attributes"] for f in feats)
        if len(feats) < page and not data.get("exceededTransferLimit"):
            break
        offset += len(feats)
    df = pd.DataFrame(rows).rename(columns=FIELDS)
    df["id"] = df["id"].astype(str)
    out = _to_tract(df)
    out.to_parquet(cache, index=False)
    return out


def _to_tract(df: pd.DataFrame) -> pd.DataFrame:
    id_len = df["id"].str.len().mode().iat[0]
    value_cols = [c for c in df.columns if c not in ("id", "population")]
    for c in value_cols + ["population"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if id_len <= 11:
        df["geoid"] = df["id"].str.zfill(11)
        return df[["geoid", "population"] + value_cols]
    # block groups → tract: population-weighted mean (proximity/concentration
    # fields are people-experienced quantities, so population weighting is the
    # faithful rollup)
    df["geoid"] = df["id"].str.zfill(12).str[:11]
    w = df["population"].fillna(0).clip(lower=0)
    df["_w"] = w

    def agg(g: pd.DataFrame) -> pd.Series:
        res = {"population": g["population"].sum()}
        wsum = g["_w"].sum()
        for c in value_cols:
            v = g[c]
            if wsum > 0 and v.notna().any():
                res[c] = (v.fillna(v.mean()) * g["_w"]).sum() / wsum
            else:
                res[c] = v.mean()
        return pd.Series(res)

    return df.groupby("geoid").apply(agg, include_groups=False).reset_index()
