# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Census-tract boundary proximity for a geocoded point.

Why this exists: every tract-level number Wattershed reports — the whole
community-burden pillar — is a property of the polygon the point landed in.
A marker 40 m from the tract line inherits one tract's demographics while
the population, traffic, and facilities actually surrounding it may sit
mostly in the next tract over. That is a real inferential limit of areal
data (the classic modifiable-areal-unit problem at the boundary), and it is
invisible unless the tool measures it and says so.

Method:
  1. Ask TIGERweb (keyless, CORS-enabled) for every tract polygon intersecting
     a small envelope around the point.
  2. Discard the home tract; what remains are the ADJACENT tracts.
  3. Measure the point-to-polygon distance in an azimuthal-equidistant
     projection centred on the point itself, where radial distance from the
     centre is exact by construction. Degrees are never compared to metres.
  4. The nearest adjacent polygon's distance IS the distance to the shared
     perimeter, because adjacent tracts share their edge.

Coastlines and the national border fall out correctly: a tract edge with no
tract on the other side yields no neighbour, so a shoreline parcel is not
flagged as boundary-adjacent to a demographic unit that does not exist.

Layering: `nearest_adjacent_tract_m` is pure — geometry in, numbers out, no
network, no state, deterministic. Only `fetch_adjacent_tracts` touches the
wire, and it degrades to an empty result rather than raising, so a screening
never fails because a boundary check could not run.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from typing import Any

from ..scoring.normalize import is_number, validate_coordinates

log = logging.getLogger("wattershed.boundary")

TIGERWEB_TRACTS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Tracts_Blocks/MapServer/0/query"
)

# Flag threshold. 150 m is roughly a city block: close enough that the
# neighbouring tract's conditions plausibly describe the parcel's actual
# surroundings, far enough not to fire on ordinary geocoder jitter alone.
DEFAULT_BUFFER_M = 150.0

# Envelope half-width for the polygon query. Comfortably larger than the
# buffer so the nearest neighbour is inside the fetched set even when the
# buffer is raised; small enough that the response stays a few tens of KB.
_QUERY_HALF_WIDTH_M = 1200.0

BOUNDARY_WARNING = (
    "High Boundary Proximity: Surrounding environmental vectors may "
    "influence local risk metrics."
)


def _metres_per_degree(lat: float) -> tuple[float, float]:
    """(m per degree latitude, m per degree longitude) on the WGS-84 ellipsoid
    at this latitude. Used only to size the query envelope."""
    lat_r = math.radians(lat)
    m_lat = 111132.92 - 559.82 * math.cos(2 * lat_r) + 1.175 * math.cos(4 * lat_r)
    m_lon = 111412.84 * math.cos(lat_r) - 93.5 * math.cos(3 * lat_r)
    return m_lat, max(abs(m_lon), 1e-6)


def query_envelope(lat: float, lon: float, half_width_m: float = _QUERY_HALF_WIDTH_M) -> dict:
    """Lat/lon bounding box of `half_width_m` around the point. Pure."""
    m_lat, m_lon = _metres_per_degree(lat)
    dlat, dlon = half_width_m / m_lat, half_width_m / m_lon
    return {
        "xmin": lon - dlon,
        "ymin": max(lat - dlat, -90.0),
        "xmax": lon + dlon,
        "ymax": min(lat + dlat, 90.0),
        "spatialReference": {"wkid": 4326},
    }


def nearest_adjacent_tract_m(
    lat: float,
    lon: float,
    home_geoid: str,
    features: Iterable[Mapping[str, Any]],
) -> dict:
    """Distance in metres from the point to the nearest ADJACENT tract polygon.

    Pure: no network, no globals, no mutation of the inputs. `features` are
    GeoJSON features carrying a GEOID property and a Polygon/MultiPolygon.

    Returns a dict that always has the same keys, so callers never branch on
    shape. `distance_m` is None when the question could not be answered —
    which is reported as an unknown, never as "not near a boundary".
    """
    result: dict[str, Any] = {
        "distance_m": None,
        "nearest_geoid": "",
        "neighbors_considered": 0,
        "note": "",
    }

    ok, reason = validate_coordinates(lat, lon)
    if not ok:
        result["note"] = reason
        return result

    from pyproj import Transformer
    from shapely.geometry import Point, shape
    from shapely.ops import transform as shapely_transform

    # Azimuthal equidistant centred on the point: distance from the origin is
    # exact, which is precisely the measurement being made.
    to_local = Transformer.from_crs(
        "EPSG:4326",
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs",
        always_xy=True,
    )
    origin = Point(0.0, 0.0)

    best_d: float | None = None
    best_geoid = ""
    considered = 0

    for feat in features:
        props = feat.get("properties") or feat.get("attributes") or {}
        geoid = str(props.get("GEOID") or props.get("geoid") or "")
        if not geoid or geoid == str(home_geoid):
            continue
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            poly = shapely_transform(to_local.transform, shape(geom))
        except Exception as e:  # malformed geometry must not abort a screening  # noqa: BLE001 — a malformed geometry must not abort a screening
            log.debug("boundary: skipping %s — %s", geoid, e)
            continue
        if poly.is_empty:
            continue
        considered += 1
        d = float(poly.distance(origin))
        if not is_number(d):
            continue
        if best_d is None or d < best_d:
            best_d, best_geoid = d, geoid

    result["neighbors_considered"] = considered
    if best_d is None:
        # A determinate negative, not an unknown: the envelope searched is far
        # wider than any sane buffer, so nothing inside it means nothing within
        # the buffer either. The point sits well inside its tract, or its
        # nearest edge is a coastline / water body / the edge of tract coverage.
        result["note"] = (
            f"No adjacent tract within {_QUERY_HALF_WIDTH_M:.0f} m of the point — it lies well "
            "inside its tract, or the nearest tract edge is a coastline, water body, or the "
            "edge of tract coverage."
        )
        return result

    result["distance_m"] = round(best_d, 1)
    result["nearest_geoid"] = best_geoid
    return result


def assess(
    lat: float,
    lon: float,
    home_geoid: str,
    features: Iterable[Mapping[str, Any]],
    buffer_m: float = DEFAULT_BUFFER_M,
) -> dict:
    """Pure classification: measurement + the flag derived from it."""
    m = nearest_adjacent_tract_m(lat, lon, home_geoid, features)
    d = m["distance_m"]
    m["buffer_m"] = float(buffer_m)
    m["near_boundary"] = bool(is_number(d) and d <= buffer_m)
    m["warning"] = BOUNDARY_WARNING if m["near_boundary"] else ""
    return m


def fetch_adjacent_tracts(lat: float, lon: float, timeout: int = 20) -> list[dict]:
    """Tract polygons intersecting the query envelope. Returns [] on any
    failure — the caller reports "could not determine", never a false all-clear."""
    import json

    from ..sources.base import SourceUnavailable, fetch_json

    try:
        data = fetch_json(
            TIGERWEB_TRACTS_URL,
            params={
                "geometry": json.dumps(query_envelope(lat, lon)),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "outSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "GEOID",
                "returnGeometry": "true",
                "f": "geojson",
            },
            timeout=timeout,
        )
    except SourceUnavailable as e:
        log.info("boundary: TIGERweb unavailable (%s) — proximity undetermined", e)
        return []
    return list(data.get("features") or [])


def boundary_proximity(
    lat: float, lon: float, home_geoid: str, buffer_m: float = DEFAULT_BUFFER_M
) -> dict:
    """Fetch + assess. The one impure entry point; safe to call unguarded."""
    feats = fetch_adjacent_tracts(lat, lon)
    if not feats:
        return {
            "distance_m": None,
            "nearest_geoid": "",
            "neighbors_considered": 0,
            "buffer_m": float(buffer_m),
            "near_boundary": False,
            "warning": "",
            "note": "Tract boundary geometry unavailable — proximity to the tract line was not checked.",
        }
    out = assess(lat, lon, home_geoid, feats, buffer_m)
    log.info(
        "boundary: %s → nearest adjacent tract %s at %s m (flag=%s)",
        home_geoid, out["nearest_geoid"] or "—", out["distance_m"], out["near_boundary"],
    )
    return out


__all__ = [
    "BOUNDARY_WARNING",
    "DEFAULT_BUFFER_M",
    "assess",
    "boundary_proximity",
    "fetch_adjacent_tracts",
    "nearest_adjacent_tract_m",
    "query_envelope",
]
