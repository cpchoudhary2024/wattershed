"""EPA eGRID2023 (rev.2): subregion emission rates, resource mix, net generation.

eGRID is the standard U.S. grid-accounting dataset used in GHG protocol
location-based reporting. Rates are ANNUAL AVERAGE output emission rates —
a screening-grade proxy, not marginal emissions (see LIMITATIONS.md).
"""

from __future__ import annotations

from functools import lru_cache

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from .base import cached_download, extract_zip

_DATA_URL = "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx"
_GIS_URL = "https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip"

# eGRID resource-mix percentage columns (fraction of net generation).
MIX_COLS = {
    "coal": "SRCLPR",
    "oil": "SROLPR",
    "gas": "SRGSPR",
    "other_fossil": "SROFPR",
    "nuclear": "SRNCPR",
    "hydro": "SRHYPR",
    "biomass": "SRBMPR",
    "wind": "SRWIPR",
    "solar": "SRSOPR",
    "geothermal": "SRGTPR",
    "other": "SROPPR",
}


@lru_cache(maxsize=1)
def _subregions_gdf() -> gpd.GeoDataFrame:
    zp = cached_download(_GIS_URL, "egrid2023_subregions.zip", "egrid_subregions_gis")
    d = extract_zip(zp, "egrid2023_subregions")
    shp = sorted(d.rglob("*.shp"))[0]
    gdf = gpd.read_file(shp)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    code_col = next(
        c for c in gdf.columns
        if c.upper() in ("SUBRGN", "SUBREGION") or c.upper().startswith("SUBRGN")
    )
    gdf = gdf.rename(columns={code_col: "SUBRGN"})
    return gdf[["SUBRGN", "geometry"]]


def subregion_for_point(lat: float, lon: float) -> str | None:
    gdf = _subregions_gdf()
    pt = Point(lon, lat)
    hits = gdf[gdf.contains(pt)]
    if len(hits):
        return str(hits.iloc[0]["SUBRGN"])
    # coastal sites can fall just outside polygon edges; snap to nearest within ~5 km
    dist = gdf.geometry.distance(pt)
    if dist.min() < 0.05:
        return str(gdf.iloc[int(dist.idxmin())]["SUBRGN"])
    return None


@lru_cache(maxsize=1)
def subregion_table() -> pd.DataFrame:
    xl_path = cached_download(_DATA_URL, "egrid2023_data_rev2.xlsx", "egrid2023")
    xls = pd.ExcelFile(xl_path)
    sheet = next(s for s in xls.sheet_names if s.upper().startswith("SRL"))
    df = pd.read_excel(xls, sheet_name=sheet, header=1)
    df = df.rename(columns=lambda c: str(c).strip())
    need = {"SUBRGN": "SUBRGN", "SRNAME": "SRNAME", "SRC2ERTA": "co2e_lb_per_mwh", "SRNGENAN": "net_gen_mwh"}
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise RuntimeError(f"eGRID SRL sheet missing expected columns: {missing}")
    out = df.rename(columns=need)
    mix = pd.DataFrame(
        {f"mix_{label}": pd.to_numeric(df.get(col), errors="coerce") for label, col in MIX_COLS.items()}
    )
    out = pd.concat([out, mix], axis=1).copy()
    out["co2e_lb_per_mwh"] = pd.to_numeric(out["co2e_lb_per_mwh"], errors="coerce")
    out["net_gen_mwh"] = pd.to_numeric(out["net_gen_mwh"], errors="coerce")
    out = out.dropna(subset=["co2e_lb_per_mwh"])
    # national percentile of each subregion's rate (unweighted rank across
    # subregions — documented choice; generation-weighting would hide small
    # dirty regions).
    out["rate_percentile"] = out["co2e_lb_per_mwh"].rank(pct=True) * 100
    return out[["SUBRGN", "SRNAME", "co2e_lb_per_mwh", "net_gen_mwh", "rate_percentile"]
               + [f"mix_{k}" for k in MIX_COLS]]


def subregion_stats(subrgn: str) -> dict | None:
    t = subregion_table()
    row = t[t["SUBRGN"] == subrgn]
    if row.empty:
        return None
    r = row.iloc[0].to_dict()
    mix = {k.removeprefix("mix_"): float(r[k]) for k in r if str(k).startswith("mix_") and pd.notna(r[k])}
    fossil = sum(mix.get(k, 0.0) for k in ("coal", "oil", "gas", "other_fossil"))
    carbon_free = sum(mix.get(k, 0.0) for k in ("nuclear", "hydro", "wind", "solar", "geothermal"))
    return {
        "subrgn": r["SUBRGN"],
        "name": r["SRNAME"],
        "co2e_lb_per_mwh": float(r["co2e_lb_per_mwh"]),
        "net_gen_mwh": float(r["net_gen_mwh"]),
        "rate_percentile": float(r["rate_percentile"]),
        "mix": mix,
        "fossil_share_pct": 100 * fossil,
        "carbon_free_share_pct": 100 * carbon_free,
    }
