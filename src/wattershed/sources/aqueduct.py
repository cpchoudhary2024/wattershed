"""WRI Aqueduct 4.0 — baseline water stress (bws), annual, HydroBASINS level-6.

Baseline water stress = total demand / available renewable supply (1979–2019
baseline). This is the structural-scarcity signal; USDM supplies the
drought-conditions signal. The reference build extracts a U.S. subset from
WRI's 261 MB download into data/processed/aqueduct_bws_us.gpkg so screening
runs offline; a point lookup reads only that extract.

Attribution (CC BY 4.0): Kuzma, S. et al. 2023. "Aqueduct 4.0: Updated
decision-relevant global water risk indicators." World Resources Institute.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from .. import config
from .base import cached_download, extract_zip

ZIP_URL = "https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip"
EXTRACT_PATH = config.PROCESSED_DIR / "aqueduct_bws_us.gpkg"

BWS_LABELS = {
    -1: "Arid & low water use",
    0: "Low (<10%)",
    1: "Low–medium (10–20%)",
    2: "Medium–high (20–40%)",
    3: "High (40–80%)",
    4: "Extremely high (>80%)",
}


def build_us_extract() -> Path:
    """One-time (reference build): download WRI zip, clip baseline-annual layer
    to a U.S. bounding box, keep only bws fields, write compact gpkg."""
    zp = cached_download(ZIP_URL, "aqueduct40.zip", "aqueduct40")
    d = extract_zip(zp, "aqueduct40")
    gdbs = sorted(d.rglob("*.gdb"))
    if not gdbs:
        raise RuntimeError("Aqueduct download contained no GDB")
    import pyogrio

    gdb = gdbs[0]
    layers = [entry[0] for entry in pyogrio.list_layers(gdb)]
    layer = next(n for n in layers if "baseline" in n.lower() and "annual" in n.lower())
    # CONUS + AK + HI + PR bounding boxes
    frames = []
    for bbox in [(-125.5, 24.0, -66.0, 49.8), (-170.5, 51.0, -129.0, 71.6),
                 (-160.9, 18.5, -154.4, 22.5), (-67.6, 17.6, -65.1, 18.6)]:
        g = gpd.read_file(gdb, layer=layer, bbox=bbox,
                          columns=["bws_raw", "bws_score", "bws_cat", "bws_label"])
        frames.append(g)
    import pandas as pd

    us = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True))
    # bbox reads overlap; dedupe strictly on geometry identity
    us = us.loc[~us.geometry.to_wkb().duplicated()].reset_index(drop=True)
    us = us.set_crs(4326, allow_override=True) if us.crs is None else us.to_crs(4326)
    us["geometry"] = us.geometry.simplify(0.002, preserve_topology=True)
    EXTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    us.to_file(EXTRACT_PATH, driver="GPKG")
    return EXTRACT_PATH


@lru_cache(maxsize=1)
def _extract_gdf() -> gpd.GeoDataFrame | None:
    if not EXTRACT_PATH.exists():
        return None
    return gpd.read_file(EXTRACT_PATH)


def bws_for_point(lat: float, lon: float) -> dict | None:
    gdf = _extract_gdf()
    if gdf is None:
        return None
    pt = Point(lon, lat)
    hits = gdf[gdf.contains(pt)]
    if hits.empty:
        # coastal basins: nearest within ~10 km
        dist = gdf.geometry.distance(pt)
        if dist.min() > 0.1:
            return None
        hits = gdf.loc[[int(dist.idxmin())]]
    r = hits.iloc[0]
    cat = int(r["bws_cat"]) if r["bws_cat"] is not None else None
    return {
        "bws_raw": float(r["bws_raw"]) if r["bws_raw"] is not None else None,
        "bws_score": float(r["bws_score"]) if r["bws_score"] is not None else None,
        "bws_cat": cat,
        "bws_label": str(r.get("bws_label") or BWS_LABELS.get(cat, "unknown")),
    }
