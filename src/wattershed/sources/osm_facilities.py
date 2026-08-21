"""OpenStreetMap / Overpass adapter — data-centre facility discovery.

This is the source that actually produced the repository's 1,569-site census
(data/study/datacenters_osm.csv), so it is a proven layer rather than a
speculative one. It is also the only keyless, machine-queryable national
source of data-centre *locations* that exists: HIFLD was discontinued in
August 2025, and the community mirrors of it are served through vendor
platforms rather than plain HTTP.

Operational reality: public Overpass instances are frequently saturated and
return 429/502/504. Every mirror in MIRRORS was returning an error during
development. The adapter therefore rotates mirrors and — critically — treats
total failure as "no new data this cycle" rather than "zero facilities
exist". An automated job that mistakes an outage for an empty result would
quietly delete the registry.
"""

from __future__ import annotations

import logging

from .base import SourceUnavailable, _session

log = logging.getLogger("wattershed.osm")

# Tried in order. de is canonical; the others are long-running community
# mirrors that stay up when it is congested.
MIRRORS: tuple[str, ...] = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# CONUS + a margin. Alaska/Hawaii/PR are screened by the tool but carry
# effectively no OSM-tagged data centres; excluding them keeps the query
# inside Overpass's timeout budget.
BBOX = (24.0, -125.5, 50.0, -66.0)

# telecom=data_center is the current tag; man_made=data_center is the
# deprecated form still present on older objects. Both are collected.
QUERY_TMPL = """[out:json][timeout:{timeout}];
(
  node["telecom"="data_center"]({s},{w},{n},{e});
  way["telecom"="data_center"]({s},{w},{n},{e});
  node["man_made"="data_center"]({s},{w},{n},{e});
  way["man_made"="data_center"]({s},{w},{n},{e});
);
out center tags;"""


def build_query(bbox: tuple[float, float, float, float] = BBOX, timeout: int = 170) -> str:
    """Pure: bbox in, Overpass QL out."""
    s, w, n, e = bbox
    return QUERY_TMPL.format(s=s, w=w, n=n, e=e, timeout=timeout)


# Operational status buckets exposed to the map filter.
STATUS_OPERATIONAL = "operational"
STATUS_CONSTRUCTION = "construction"
STATUS_PLANNED = "planned"
STATUS_DISUSED = "disused"


def status_from_tags(tags: dict) -> tuple[str, str]:
    """(status, how_it_was_determined) from OSM lifecycle tagging. Pure.

    OSM convention is that a feature is mapped once it exists on the ground,
    and lifecycle prefixes (`proposed:`, `construction:`, `disused:`) mark
    anything else. So an untagged data centre is conventionally an existing
    one — but "the building exists" is not the same claim as "the data centre
    is in service", so that case is reported as an ASSUMPTION with its own
    provenance string rather than as an observation. The UI discloses it.
    """
    t = {k.lower(): (v or "").lower() for k, v in (tags or {}).items()}
    keys = set(t)

    if any(k.startswith(("disused:", "abandoned:", "razed:", "demolished:")) for k in keys) \
            or t.get("disused") == "yes" or t.get("abandoned") == "yes":
        return STATUS_DISUSED, "osm-lifecycle"
    if any(k.startswith("proposed:") for k in keys) or t.get("proposed") == "yes" \
            or t.get("building") == "proposed" or t.get("planned") == "yes":
        return STATUS_PLANNED, "osm-lifecycle"
    if any(k.startswith("construction:") for k in keys) or t.get("building") == "construction" \
            or (t.get("construction") and t.get("construction") != "no") \
            or t.get("landuse") == "construction":
        return STATUS_CONSTRUCTION, "osm-lifecycle"
    return STATUS_OPERATIONAL, "osm-default"


def parse_elements(payload: dict) -> list[dict]:
    """Pure: Overpass JSON in, normalized facility records out.

    Ways carry a `center` rather than lat/lon; nodes carry lat/lon directly.
    Anything without usable coordinates is dropped rather than defaulted.
    """
    out = []
    for el in (payload or {}).get("elements", []) or []:
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            centre = el.get("center") or {}
            lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        tags = el.get("tags") or {}
        status, status_source = status_from_tags(tags)
        out.append(
            {
                "osm_id": f"{el.get('type','?')}/{el.get('id','?')}",
                "name": (tags.get("name") or "").strip(),
                "operator": (tags.get("operator") or "").strip(),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "status": status,
                "status_source": status_source,
                "source": "osm",
            }
        )
    return out


def fetch_facilities(timeout: int = 180) -> list[dict]:
    """Query mirrors in order; raise only if every mirror fails."""
    query = build_query()
    last = ""
    for url in MIRRORS:
        try:
            r = _session.post(url, data={"data": query}, timeout=timeout)
            r.raise_for_status()
            recs = parse_elements(r.json())
            log.info("osm: %d facilities from %s", len(recs), url)
            return recs
        except Exception as e:  # noqa: BLE001 — any mirror failure falls through
            last = f"{url}: {e}"
            log.warning("osm: mirror unavailable — %s", last)
    raise SourceUnavailable(f"all Overpass mirrors failed (last: {last})")


__all__ = [
    "BBOX",
    "MIRRORS",
    "STATUS_CONSTRUCTION",
    "STATUS_DISUSED",
    "STATUS_OPERATIONAL",
    "STATUS_PLANNED",
    "build_query",
    "fetch_facilities",
    "parse_elements",
    "status_from_tags",
]
