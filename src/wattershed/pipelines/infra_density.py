# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Infrastructure Density Modifier — a DESCRIPTIVE layer, not a score input.

Read this before wiring it anywhere.

The three pillars are built from cited, vintage-stamped public measurements.
This layer is built from OpenStreetMap facility tags refreshed twice a month
by an unattended job. Letting it move a pillar score would mean a screening
result could change between two runs because a volunteer added a building
outline — with no reviewer, no changelog, and no way for a reader to tell
which number moved or why. Worse, it would be circular for the siting-equity
study, which asks whether data centres are sited in already-burdened tracts:
feeding data-centre density INTO the burden pillar makes that question answer
itself.

So: this module computes clustering, writes it to its own artifact, and is
imported by nothing in wattershed.scoring. A test enforces that.

What it is legitimately good for: cumulative-impact context. "This tract
already hosts four campuses within 5 km" is exactly the fact a siting review
should surface — as context a human weighs, next to the scores, not inside
them.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger("wattershed.density")

EARTH_R_KM = 6371.0088

# Clustering radius. Matches PROXIMITY_RADIUS_KM / NEIGHBORHOOD_RADIUS_KM used
# elsewhere in the tool, so "within 5 km" means one thing across the codebase.
CLUSTER_RADIUS_KM = 5.0

# Facilities beyond this count in one neighbourhood are capped when scaling, so
# a single extreme cluster (Ashburn) does not flatten the rest of the ramp.
SATURATION_COUNT = 8.0


def haversine_km(lat0: float, lon0: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Great-circle distance from one point to many. Pure, vectorized."""
    lat0_r, lon0_r = np.radians(lat0), np.radians(lon0)
    lat_r, lon_r = np.radians(lats), np.radians(lons)
    a = (
        np.sin((lat_r - lat0_r) / 2) ** 2
        + np.cos(lat0_r) * np.cos(lat_r) * np.sin((lon_r - lon0_r) / 2) ** 2
    )
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def neighbourhood_counts(
    tract_lats: np.ndarray,
    tract_lons: np.ndarray,
    facilities: list[dict],
    radius_km: float = CLUSTER_RADIUS_KM,
) -> np.ndarray:
    """Facilities within `radius_km` of each tract centroid. Pure.

    Loops facilities (order 10^3) over vectorized tract arrays (order 10^5)
    rather than materializing a 10^3 x 10^5 distance matrix — same result,
    a few MB of working memory instead of ~1 GB.
    """
    counts = np.zeros(len(tract_lats), dtype=np.int32)
    for f in facilities:
        lat, lon = f.get("lat"), f.get("lon")
        if lat is None or lon is None:
            continue
        counts += (haversine_km(float(lat), float(lon), tract_lats, tract_lons) <= radius_km)
    return counts


def modifier_from_counts(
    in_tract: np.ndarray,
    nearby: np.ndarray,
    saturation: float = SATURATION_COUNT,
) -> np.ndarray:
    """Map facility counts to a 0-100 clustering index. Pure and monotonic.

    A tract's own facilities weigh double a merely-nearby one: hosting is a
    stronger statement than adjacency. The ramp is sub-linear (sqrt) because
    the first campus in a neighbourhood changes its character far more than
    the eighth does, then saturates.
    """
    weighted = in_tract.astype(np.float64) * 2.0 + np.maximum(nearby - in_tract, 0).astype(np.float64)
    scaled = np.sqrt(np.clip(weighted, 0.0, saturation) / saturation)
    return np.clip(scaled * 100.0, 0.0, 100.0)


def compute(tracts, facilities: list[dict], radius_km: float = CLUSTER_RADIUS_KM) -> list[dict]:
    """Per-tract density records for tracts that actually have facilities near.

    `tracts` is the committed reference frame (85,396 rows: geoid, intptlat,
    intptlon). Only non-zero tracts are returned — emitting 85k mostly-zero
    rows into a git-committed artifact would be pure repository bloat.
    """
    geoids = tracts["geoid"].astype(str).values
    lats = tracts["intptlat"].astype(float).values
    lons = tracts["intptlon"].astype(float).values

    by_tract: dict[str, int] = {}
    for f in facilities:
        g = str(f.get("tract_geoid") or "")
        if g:
            by_tract[g] = by_tract.get(g, 0) + 1
    in_tract = np.array([by_tract.get(g, 0) for g in geoids], dtype=np.int32)

    nearby = neighbourhood_counts(lats, lons, facilities, radius_km)
    idm = modifier_from_counts(in_tract, nearby)

    hit = np.nonzero(nearby > 0)[0]
    log.info(
        "density: %d/%d tracts within %.0f km of a facility (%d host one directly)",
        len(hit), len(geoids), radius_km, int((in_tract > 0).sum()),
    )
    return [
        {
            "geoid": geoids[i],
            "facilities_in_tract": int(in_tract[i]),
            "facilities_within_radius": int(nearby[i]),
            "radius_km": radius_km,
            "density_modifier": round(float(idm[i]), 1),
        }
        for i in hit
    ]


__all__ = [
    "CLUSTER_RADIUS_KM",
    "SATURATION_COUNT",
    "compute",
    "haversine_km",
    "modifier_from_counts",
    "neighbourhood_counts",
]
