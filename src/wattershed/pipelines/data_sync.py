# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Bi-weekly data sync: refresh the facility registry, density layer and news.

Design constraints this file is built around:

* **Partial failure is normal.** Overpass returns 502/504 routinely and EIA is
  optional. Each source is isolated: one failing adapter degrades that layer
  and the run still succeeds. A source that fails NEVER writes an empty
  artifact — mistaking an outage for "zero facilities exist" would silently
  delete the registry on a bad afternoon.
* **Delta-only network use.** Tract assignment is cached per facility, so a
  cycle geocodes only genuinely new sites (typically a handful) instead of
  re-resolving the whole registry.
* **Bounded artifacts.** Everything written here is committed to git twice a
  month. Unbounded appends would bloat history by design, so news is capped
  and the density layer emits only non-zero tracts.
* **Idempotence.** A run with no upstream change produces byte-identical
  files, so the workflow can skip the commit entirely.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .. import config, provenance
from ..sources import eia_capacity, news, osm_facilities
from ..sources.base import SourceUnavailable, fetch_json

log = logging.getLogger("wattershed.sync")

NEWS_DIR = config.DATA_DIR / "news"
STATE_CHUNK_DIR = config.REPO_ROOT / "site" / "data" / "states"

FACILITY_REGISTRY = config.PROCESSED_DIR / "facility_registry.json"
DENSITY_PATH = config.PROCESSED_DIR / "infrastructure_density.json"
EIA_PATH = config.PROCESSED_DIR / "eia_capacity.json"
MAP_LAYER_PATH = config.REPO_ROOT / "site" / "data" / "facilities.json"
NEWS_PATH = NEWS_DIR / "news_announcements.json"
MANIFEST_PATH = config.PROCESSED_DIR / "data_sync_manifest.json"

FCC_AREA_URL = "https://geo.fcc.gov/api/census/area"

# Ceiling on new-facility geocodes per cycle. A first run against an empty
# registry would otherwise fire ~1,600 calls at a free public API; the
# remainder simply resolve on subsequent cycles.
MAX_GEOCODES_PER_RUN = 250


@dataclass
class SourceResult:
    source_id: str
    ok: bool
    count: int = 0
    note: str = ""


@dataclass
class SyncReport:
    results: list[SourceResult] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    boundaries: list[dict] = field(default_factory=list)
    friction: dict = field(default_factory=dict)
    facilities_total: int = 0
    facilities_new: int = 0
    tracts_with_density: int = 0
    news_total: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.written)

    def to_dict(self) -> dict:
        return {
            "synced_at": provenance.utc_now_iso(),
            "sources": [vars(r) for r in self.results],
            "facilities_total": self.facilities_total,
            "facilities_new": self.facilities_new,
            "tracts_with_density": self.tracts_with_density,
            "news_total": self.news_total,
            "files_written": sorted(self.written),
            # Published in the manifest so the exclusion is a committed,
            # citable fact rather than a line in a CI log that scrolls away.
            "structurally_excluded": self.boundaries,
            # Descriptive media signal; modifies no score.
            "community_friction": self.friction,
        }


# --- small I/O helpers ------------------------------------------------------

def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.warning("sync: unreadable %s (%s) — starting from default", path.name, e)
        return default


def _write_json_if_changed(path: Path, payload, report: SyncReport,
                           compact: bool = False) -> bool:
    """Write only on real change, so a quiet cycle produces no commit.

    `compact` drops indentation for the large machine-read artifacts. The
    density layer is ~9,600 records: pretty-printed it is 1.5 MB committed
    twice a month, and nobody reads it by eye — the human-facing views are the
    per-state chunks. Small artifacts stay indented so their diffs stay
    reviewable.
    """
    if compact:
        text = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False) + "\n"
    else:
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text() == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    try:
        rel = str(path.relative_to(config.REPO_ROOT))
    except ValueError:
        rel = str(path)
    report.written.append(rel)
    log.info("sync: wrote %s", rel)
    return True


def facility_key(rec: dict) -> str:
    """Stable identity. OSM ids are stable across fetches; coordinates are the
    fallback for records that arrive without one."""
    return rec.get("osm_id") or f"{rec.get('lat')},{rec.get('lon')}"


# --- spatial reconciliation -------------------------------------------------

def assign_tract(lat: float, lon: float, timeout: int = 25) -> tuple[str, str]:
    """(tract_geoid, county_fips) by point-in-polygon via the FCC Census Area
    API — the same authoritative service the study and the live site use.
    Returns ("","") on failure so the facility is simply retried next cycle."""
    try:
        data = fetch_json(
            FCC_AREA_URL,
            params={"lat": lat, "lon": lon, "censusYear": 2020, "format": "json"},
            timeout=timeout,
        )
    except SourceUnavailable as e:
        log.debug("sync: FCC lookup failed for (%s,%s) — %s", lat, lon, e)
        return "", ""
    res = (data.get("results") or [None])[0] or {}
    block = res.get("block_fips") or ""
    return (block[:11], block[:5]) if len(block) >= 11 else ("", "")


def reconcile_facilities(existing: list[dict], incoming: list[dict],
                         max_geocodes: int = MAX_GEOCODES_PER_RUN) -> tuple[list[dict], int]:
    """Merge incoming facilities into the registry, geocoding only the new or
    still-unresolved ones. Returns (registry, newly_added)."""
    by_key = {facility_key(r): dict(r) for r in existing}
    before = len(by_key)

    for rec in incoming:
        k = facility_key(rec)
        if k in by_key:
            # Refresh mutable tags but keep the cached tract assignment.
            by_key[k].update({
                "name": rec.get("name") or by_key[k].get("name", ""),
                "operator": rec.get("operator") or by_key[k].get("operator", ""),
                "lat": rec.get("lat", by_key[k].get("lat")),
                "lon": rec.get("lon", by_key[k].get("lon")),
            })
        else:
            by_key[k] = dict(rec, tract_geoid="", county_fips="",
                             first_seen=provenance.utc_now_iso())

    pending = [r for r in by_key.values() if not r.get("tract_geoid")]
    for rec in pending[:max_geocodes]:
        geoid, county = assign_tract(rec["lat"], rec["lon"])
        if geoid:
            rec["tract_geoid"], rec["county_fips"] = geoid, county
    if len(pending) > max_geocodes:
        log.info("sync: %d facilities still unresolved; deferred to next cycle",
                 len(pending) - max_geocodes)

    registry = sorted(by_key.values(), key=facility_key)
    return registry, len(by_key) - before


# --- authoritative status overlay -------------------------------------------

# The curated registry carries hand-verified, per-fact-cited statuses. Its
# vocabulary is finer than the map's three buckets, so it is folded down here
# rather than in the UI, keeping one mapping in one place.
_CURATED_STATUS = {
    "operating": "operational",
    "construction": "construction",
    "proposed": "planned",
    "announced": "planned",
    "contested": "planned",   # publicly proposed and disputed — not yet built
    "rejected": "planned",    # kept visible: a refused siting is a real signal
}


def curated_statuses() -> list[dict]:
    """Hand-verified statuses from data/curated/sites.yaml. Returns [] if the
    registry is absent so the sync never hard-depends on it."""
    import yaml

    path = config.CURATED_DIR / "sites.yaml"
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        log.warning("sync: curated registry unreadable — %s", e)
        return []
    out = []
    for site in data.get("sites") or []:
        raw = (site.get("status") or "").strip().lower()
        if not raw or site.get("lat") is None or site.get("lon") is None:
            continue
        out.append({
            "name": site.get("name", ""),
            "lat": float(site["lat"]),
            "lon": float(site["lon"]),
            "status": _CURATED_STATUS.get(raw, "planned"),
            "curated_status": raw,
        })
    return out


def apply_curated_status(registry: list[dict], curated: list[dict],
                         tolerance_deg: float = 0.02) -> int:
    """Overlay hand-verified status onto the nearest crowd-sourced record.

    ~0.02 deg is roughly 2 km — loose enough to match a campus whose OSM
    centroid differs from the curated parcel coordinate, tight enough not to
    capture a neighbouring facility. Curated always wins: it is cited.
    """
    matched = 0
    for c in curated:
        best, best_d = None, tolerance_deg
        for rec in registry:
            lat, lon = rec.get("lat"), rec.get("lon")
            if lat is None or lon is None:
                continue
            d = max(abs(lat - c["lat"]), abs(lon - c["lon"]))
            if d <= best_d:
                best, best_d = rec, d
        if best is not None:
            best["status"] = c["status"]
            best["status_source"] = "curated"
            matched += 1
    return matched


def build_map_layer(facilities: list[dict]) -> dict:
    """Pre-projected national layer for the dashboard map.

    Projection is done here, once, server-side: the SVG already works in
    projected coordinates, so shipping x/y avoids re-implementing an Albers
    projection in the browser and keeps the client render to a single pass.
    """
    from ..dashboard.build import project

    pts, counts = [], {}
    for f in facilities:
        lat, lon = f.get("lat"), f.get("lon")
        if lat is None or lon is None:
            continue
        status = f.get("status") or "operational"
        counts[status] = counts.get(status, 0) + 1
        x, y = project(float(lon), float(lat))
        pts.append({
            "n": f.get("name", ""),
            "s": status[0],                       # o | c | p | d — one char, 1.5k rows
            "a": 1 if f.get("status_source") == "curated" else 0,   # authoritative?
            "x": round(x, 1),
            "y": round(y, 1),
        })
    pts.sort(key=lambda r: (r["y"], r["x"]))
    # Deliberately no wall-clock stamp. Every artifact this pipeline writes is
    # compared byte-for-byte against the committed copy to decide whether to
    # commit; embedding "now" makes every file differ on every run and
    # manufactures a commit each cycle even when no upstream data moved. The
    # run time is recorded once, in data_sync_manifest.json, which is itself
    # only written when something real changed.
    return {
        "counts": counts,
        "assumed_operational": sum(
            1 for f in facilities
            if (f.get("status") == "operational" and f.get("status_source") == "osm-default")
        ),
        "points": pts,
    }


# --- state partitioning -----------------------------------------------------

def partition_by_state(facilities: list[dict], density: list[dict]) -> dict[str, dict]:
    """Split into per-state chunks keyed by 2-digit state FIPS. Pure.

    The site currently ships one 3.4 MB tracts.json; partitioning keeps each
    added layer to a few KB per state so a visitor downloads their state, not
    the nation.
    """
    dens_by_geoid = {d["geoid"]: d for d in density}
    chunks: dict[str, dict] = {}
    for f in facilities:
        geoid = f.get("tract_geoid") or ""
        if len(geoid) < 11:
            continue
        st = geoid[:2]
        c = chunks.setdefault(st, {"state_fips": st, "facilities": [], "density": {}})
        c["facilities"].append({
            "name": f.get("name", ""), "operator": f.get("operator", ""),
            "lat": f.get("lat"), "lon": f.get("lon"), "tract": geoid,
            "status": f.get("status", "operational"),
            "status_source": f.get("status_source", "osm-default"),
        })
        d = dens_by_geoid.get(geoid)
        if d:
            c["density"][geoid] = d["density_modifier"]
    for c in chunks.values():
        c["facilities"].sort(key=lambda r: (r["tract"], r["name"]))
    return chunks


# --- declared ingestion boundaries ------------------------------------------

def log_ingestion_boundaries() -> list[dict]:
    """Announce, every run, which upstream streams are STRUCTURALLY EXCLUDED.

    A silent absence is indistinguishable from an oversight. An external
    researcher reading a Wattershed number needs to know that real-time USGS
    hydrology and EIA-930 hourly balancing-authority data are not merely
    missing this cycle — they are not wired in at all, deliberately, and no
    score depends on them. The declarations live in sources/versioning.py as
    blocks with status `declared_not_ingested`; this reads them rather than
    restating them, so the log can never drift from the catalog.

    Returns the boundary records so callers can render them too.
    """
    from ..sources.versioning import controller

    dvc = controller()
    boundaries = dvc.uningested_declarations()
    if not boundaries:
        return []

    log.warning(
        "ingestion boundaries — %d upstream stream(s) are structurally excluded "
        "and contribute to NO score:", len(boundaries),
    )
    out = []
    for b in boundaries:
        stream = b.role.replace("NOT INGESTED — ", "")
        log.warning("  [excluded] %s", b.block_id)
        log.warning("             stream : %s", stream)
        log.warning("             reason : %s", b.caveat)
        out.append({"block_id": b.block_id, "stream": stream, "reason": b.caveat})

    # The context layers are ingested but equally scoreless; stating both
    # boundaries together is what makes the arithmetic auditable end to end.
    ctx = [b for b in dvc.blocks_for_pillar("context")]
    if ctx:
        log.warning(
            "  [context]  %s — ingested and refreshed, but excluded from every "
            "pillar score by design", ", ".join(b.block_id for b in ctx),
        )
    return out


# --- orchestrator -----------------------------------------------------------

def sync(skip_osm: bool = False, skip_news: bool = False, skip_eia: bool = False) -> SyncReport:
    report = SyncReport()

    # Stated up front, every run: what this pipeline does NOT touch.
    report.boundaries = log_ingestion_boundaries()

    # 1. Facilities (OSM / Overpass)
    registry = _read_json(FACILITY_REGISTRY, [])
    if skip_osm:
        report.results.append(SourceResult("osm_datacenters", True, len(registry), "skipped by flag"))
    else:
        try:
            incoming = osm_facilities.fetch_facilities()
            registry, added = reconcile_facilities(registry, incoming)
            report.facilities_new = added
            matched = apply_curated_status(registry, curated_statuses())
            log.info("sync: %d facilities carry a hand-verified status", matched)
            report.results.append(SourceResult("osm_datacenters", True, len(incoming), ""))
            _write_json_if_changed(FACILITY_REGISTRY, registry, report)
        except SourceUnavailable as e:
            # Keep the existing registry untouched — an outage is not a deletion.
            report.results.append(SourceResult("osm_datacenters", False, 0, str(e)[:200]))
            log.warning("sync: facility layer unchanged this cycle — %s", e)
    report.facilities_total = len(registry)

    # 2. Density (local computation over the committed tract frame)
    if registry:
        try:
            from ..scoring import reference
            density = infra_density_compute(reference.table(), registry)
            report.tracts_with_density = len(density)
            _write_json_if_changed(DENSITY_PATH, density, report, compact=True)
            chunks = partition_by_state(registry, density)
            for st, payload in sorted(chunks.items()):
                _write_json_if_changed(STATE_CHUNK_DIR / f"{st}.json", payload, report)
            _write_json_if_changed(
                STATE_CHUNK_DIR / "index.json",
                {"states": sorted(chunks)},   # no timestamp — see build_map_layer
                report,
            )
            _write_json_if_changed(MAP_LAYER_PATH, build_map_layer(registry), report, compact=True)
        except Exception as e:  # noqa: BLE001 — reference table may be absent
            log.warning("sync: density layer skipped — %s", e)
            report.results.append(SourceResult("infrastructure_density", False, 0, str(e)[:200]))

    # 3. News (announcement leads — never a score input)
    if skip_news:
        report.results.append(SourceResult("google_news_rss", True, 0, "skipped by flag"))
    else:
        incoming_news = news.fetch_announcements()
        if incoming_news:
            merged = news.merge(_read_json(NEWS_PATH, []), incoming_news)
            merged = news.annotate_friction(merged)   # idempotent: recomputed from titles
            report.news_total = len(merged)
            report.friction = news.friction_summary(merged)
            _write_json_if_changed(NEWS_PATH, merged, report)
            log.info("news: %d/%d leads mention community-friction terms %s",
                     report.friction["items_with_friction"], report.friction["items_total"],
                     report.friction["by_term"] or "{}")
            report.results.append(SourceResult("google_news_rss", True, len(incoming_news), ""))
        else:
            report.results.append(SourceResult("google_news_rss", False, 0, "no items returned"))

    # 4. EIA (optional, key-gated)
    if skip_eia or not eia_capacity.available():
        report.results.append(SourceResult(
            "eia_v2_capacity", True, 0,
            "skipped — EIA_API_KEY not set (optional source)" if not skip_eia else "skipped by flag"))
    else:
        try:
            rows = eia_capacity.fetch_capacity()
            _write_json_if_changed(EIA_PATH, rows, report)
            report.results.append(SourceResult("eia_v2_capacity", True, len(rows), ""))
        except (SourceUnavailable, eia_capacity.EIAKeyMissing) as e:
            report.results.append(SourceResult("eia_v2_capacity", False, 0, str(e)[:200]))

    # 5. Manifest last, and only if something else changed — otherwise its
    #    timestamp alone would manufacture a commit every single cycle.
    if report.written:
        MANIFEST_PATH.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
        report.written.append(str(MANIFEST_PATH.relative_to(config.REPO_ROOT)))
    return report


def infra_density_compute(tracts, registry):
    from .infra_density import compute
    return compute(tracts, registry)


__all__ = [
    "FACILITY_REGISTRY",
    "MAP_LAYER_PATH",
    "NEWS_PATH",
    "SourceResult",
    "SyncReport",
    "apply_curated_status",
    "assign_tract",
    "build_map_layer",
    "curated_statuses",
    "partition_by_state",
    "reconcile_facilities",
    "sync",
]
