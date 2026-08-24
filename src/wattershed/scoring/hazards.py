# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Spatial fatal-flaw screening: flood, wetland, and seismic conflicts.

These are SITE-CONSTRAINT flags, not pillar scores, and they are kept out of
the three pillars on purpose. Water stress, grid strain and community burden
are cumulative-pressure measures; a floodplain intersection is a binary
engineering and permitting constraint on a parcel. Averaging a constraint into
a pressure index would make both harder to read, and would let a site with no
environmental pressure but a wetland on it score as "Low".

Sources (all keyless, all authoritative for their domain):
  * FEMA National Flood Hazard Layer — Special Flood Hazard Area (the
    regulatory 1%-annual-chance floodplain). SFHA_TF is FEMA's own boolean.
  * USFWS National Wetlands Inventory — mapped wetland polygons. NWI is a
    remote-sensing INVENTORY, explicitly not a jurisdictional determination:
    only the Corps can decide whether a feature is a water of the United
    States. That distinction is carried on every flag this module raises.
  * USGS ASCE 7-16 design maps — S_DS / PGA seismic design parameters.

Layering: `classify()` is pure — measurements in, flags out, no network. Only
`screen()` touches the wire, and it degrades to "unscreened" rather than
"clear" when a service is unavailable. An unreachable FEMA service must never
read as "not in a floodplain".
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from ..sources.base import SourceUnavailable, fetch_json
from .normalize import is_number, validate_coordinates

log = logging.getLogger("wattershed.hazards")

FEMA_NFHL_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)
NWI_URL = (
    "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/"
    "Wetlands/MapServer/0/query"
)
USGS_DESIGN_URL = "https://earthquake.usgs.gov/ws/designmaps/asce7-16.json"

# ASCE 7 short-period design acceleration. 0.50 g is the conventional break
# between moderate and high seismic design demand; at or above it, structural
# and non-structural bracing of racks, piping and generators becomes a real
# cost and schedule item rather than a detail.
SDS_ELEVATED = 0.33
SDS_HIGH = 0.50

SEVERITY_ORDER = {"none": 0, "advisory": 1, "elevated": 2, "high": 3, "unscreened": -1}


@dataclass(frozen=True)
class HazardFlag:
    """One screened constraint. `severity` is ordinal, never numeric weight."""

    hazard: str            # flood | wetland | seismic
    severity: str          # none | advisory | elevated | high | unscreened
    headline: str          # one clause, no adjectives
    detail: str = ""
    source_id: str = ""
    value: float | None = None

    @property
    def triggered(self) -> bool:
        return self.severity in ("advisory", "elevated", "high")


@dataclass
class HazardScreen:
    flags: list[HazardFlag] = field(default_factory=list)

    @property
    def triggered(self) -> list[HazardFlag]:
        return [f for f in self.flags if f.triggered]

    @property
    def unscreened(self) -> list[HazardFlag]:
        return [f for f in self.flags if f.severity == "unscreened"]

    @property
    def worst(self) -> str:
        return max((f.severity for f in self.flags), key=lambda s: SEVERITY_ORDER[s],
                   default="none")

    def to_dict(self) -> dict:
        return {
            "worst_severity": self.worst,
            "triggered": [asdict(f) for f in self.triggered],
            "unscreened": [f.hazard for f in self.unscreened],
            "flags": [asdict(f) for f in self.flags],
        }


# --- pure classification -----------------------------------------------------

def classify_flood(zones: list[dict] | None) -> HazardFlag:
    """FEMA NFHL zone records → flag. Pure.

    SFHA_TF == 'T' is FEMA's own determination that the point lies in the
    regulatory 1%-annual-chance floodplain, which drives NFIP requirements and
    local floodplain-development ordinances.
    """
    if zones is None:
        return HazardFlag("flood", "unscreened", "FEMA NFHL not reached; floodplain status unknown.",
                          source_id="fema_nfhl")
    if not zones:
        return HazardFlag("flood", "advisory",
                          "No NFHL coverage at this point.",
                          "The National Flood Hazard Layer is not mapped everywhere. Absence of a "
                          "polygon is not evidence of absence of flood risk.",
                          source_id="fema_nfhl")
    in_sfha = [z for z in zones if str(z.get("SFHA_TF", "")).upper() == "T"]
    if in_sfha:
        zone = str(in_sfha[0].get("FLD_ZONE", "")).strip() or "unspecified"
        subty = str(in_sfha[0].get("ZONE_SUBTY", "") or "").strip()
        return HazardFlag(
            "flood", "high",
            f"Within FEMA Special Flood Hazard Area (Zone {zone}).",
            "Regulatory 1%-annual-chance floodplain. Triggers NFIP requirements and local "
            "floodplain-development review; finished-floor elevation, generator and "
            "switchgear siting are affected."
            + (f" Subtype: {subty}." if subty else ""),
            source_id="fema_nfhl",
        )
    zone = str(zones[0].get("FLD_ZONE", "")).strip() or "unspecified"
    if zone.upper().startswith("X") and "0.2" in str(zones[0].get("ZONE_SUBTY", "") or ""):
        return HazardFlag("flood", "advisory", f"Zone {zone} — 0.2%-annual-chance (500-year) flood area.",
                          "Outside the regulatory SFHA; commonly still a lender and insurer question.",
                          source_id="fema_nfhl")
    return HazardFlag("flood", "none", f"Outside the Special Flood Hazard Area (Zone {zone}).",
                      source_id="fema_nfhl")


def classify_wetland(features: list[dict] | None) -> HazardFlag:
    """USFWS NWI records → flag. Pure."""
    if features is None:
        return HazardFlag("wetland", "unscreened", "USFWS NWI not reached; wetland status unknown.",
                          source_id="usfws_nwi")
    if not features:
        return HazardFlag("wetland", "none", "No NWI wetland polygon at this point.",
                          "NWI is an inventory, not a jurisdictional determination; only a Corps "
                          "delineation settles Clean Water Act jurisdiction.",
                          source_id="usfws_nwi")
    kinds = sorted({str(f.get("WETLAND_TYPE", "") or "").strip() for f in features if f.get("WETLAND_TYPE")})
    acres = [float(f["ACRES"]) for f in features if is_number(f.get("ACRES"))]
    return HazardFlag(
        "wetland", "elevated",
        "Mapped NWI wetland intersects this point"
        + (f" ({', '.join(kinds)})." if kinds else "."),
        "Indicates a possible Clean Water Act §404 permitting pathway and warrants an "
        "aquatic-resource delineation. NWI is a remote-sensing inventory and is NOT a "
        "jurisdictional determination — only the U.S. Army Corps of Engineers can make one."
        + (f" Mapped extent: {max(acres):.1f} acres." if acres else ""),
        source_id="usfws_nwi",
        value=max(acres) if acres else None,
    )


def classify_seismic(sds: float | None) -> HazardFlag:
    """ASCE 7-16 S_DS → flag. Pure."""
    if not is_number(sds):
        return HazardFlag("seismic", "unscreened", "USGS design maps not reached; S_DS unknown.",
                          source_id="usgs_designmaps")
    sds = float(sds)
    if sds >= SDS_HIGH:
        sev, head = "high", f"High seismic design demand (S_DS = {sds:.2f} g)."
    elif sds >= SDS_ELEVATED:
        sev, head = "elevated", f"Moderate seismic design demand (S_DS = {sds:.2f} g)."
    else:
        return HazardFlag("seismic", "none", f"Low seismic design demand (S_DS = {sds:.2f} g).",
                          source_id="usgs_designmaps", value=sds)
    return HazardFlag(
        "seismic", sev, head,
        "ASCE 7-16 short-period design acceleration. Drives seismic bracing of racks, "
        "containment, piping and generator sets, and the anchorage detailing that "
        "governs equipment procurement lead time.",
        source_id="usgs_designmaps", value=sds,
    )


def classify(flood_zones, wetland_features, sds) -> HazardScreen:
    """Assemble the screen from raw measurements. Pure — the unit under test."""
    return HazardScreen(flags=[
        classify_flood(flood_zones),
        classify_wetland(wetland_features),
        classify_seismic(sds),
    ])


# --- I/O ---------------------------------------------------------------------

def _arcgis_point_query(url: str, lat: float, lon: float, out_fields: str,
                        timeout: int = 30) -> list[dict] | None:
    """Attributes of features intersecting the point, or None if unreachable."""
    import json as _json

    try:
        data = fetch_json(url, params={
            "geometry": _json.dumps({"x": lon, "y": lat}),
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
        }, timeout=timeout)
    except SourceUnavailable as e:
        log.info("hazards: %s unreachable — %s", url.split("/")[2], e)
        return None
    if isinstance(data, dict) and data.get("error"):
        log.info("hazards: %s returned an error — %s", url.split("/")[2], data["error"])
        return None
    return [f.get("attributes", {}) for f in (data.get("features") or [])]


def fetch_flood(lat: float, lon: float) -> list[dict] | None:
    return _arcgis_point_query(FEMA_NFHL_URL, lat, lon, "FLD_ZONE,ZONE_SUBTY,SFHA_TF")


def fetch_wetland(lat: float, lon: float) -> list[dict] | None:
    rows = _arcgis_point_query(NWI_URL, lat, lon, "Wetlands.WETLAND_TYPE,Wetlands.ACRES")
    if rows is None:
        return None
    # The service returns dotted, table-qualified keys; normalize them.
    return [{k.split(".")[-1]: v for k, v in r.items()} for r in rows]


def fetch_sds(lat: float, lon: float, timeout: int = 30) -> float | None:
    try:
        data = fetch_json(USGS_DESIGN_URL, params={
            "latitude": lat, "longitude": lon,
            "riskCategory": "III",   # ASCE 7 category for facilities whose failure
            "siteClass": "D",        # carries substantial economic consequence
            "title": "wattershed-screening",
        }, timeout=timeout)
    except SourceUnavailable as e:
        log.info("hazards: USGS design maps unreachable — %s", e)
        return None
    sds = ((data or {}).get("response") or {}).get("data", {}).get("sds")
    return float(sds) if is_number(sds) else None


def screen(lat: float, lon: float) -> HazardScreen:
    """Fetch + classify. Safe to call unguarded; never raises."""
    ok, reason = validate_coordinates(lat, lon)
    if not ok:
        log.info("hazards: %s", reason)
        return HazardScreen(flags=[
            HazardFlag(h, "unscreened", reason) for h in ("flood", "wetland", "seismic")
        ])
    out = classify(fetch_flood(lat, lon), fetch_wetland(lat, lon), fetch_sds(lat, lon))
    log.info("hazards: worst=%s triggered=%s unscreened=%s",
             out.worst, [f.hazard for f in out.triggered], [f.hazard for f in out.unscreened])
    return out


__all__ = [
    "SDS_ELEVATED",
    "SDS_HIGH",
    "HazardFlag",
    "HazardScreen",
    "classify",
    "classify_flood",
    "classify_seismic",
    "classify_wetland",
    "screen",
]
