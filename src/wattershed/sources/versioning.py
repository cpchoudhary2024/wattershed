"""Centralized version + resolution controller for every ingested index block.

`provenance.SOURCES` answers *who published this and under what licence*.
It deliberately does not answer the two questions a reviewer asks next:

  1. **When was this block published** (as distinct from the period it
     describes, and from when we happened to fetch it)?
  2. **At what spatial resolution does it actually resolve** — because a
     score rendered at a point is only as sharp as its coarsest input, and
     a sub-basin polygon, an eGRID subregion, and a census tract are three
     very different claims about "here".

`DataVersionController` is the single place those are declared. It maps each
index block to its publication timestamp, native spatial unit, refresh
cadence, and ingestion mode, then joins that static declaration against the
*observed* retrieval stamp on disk (`data/cache/*.meta.json`) at call time.

Memory discipline: blocks are frozen dataclasses held in one immutable
module-level mapping — no per-call object graphs, no retained frames. The
only disk read is the small `.meta.json` stamp, memoized behind a bounded
cache keyed on (path, mtime) so a rebuilt cache file invalidates naturally
instead of pinning a stale entry forever.

Ingestion honesty: a block whose `status` is `declared_not_ingested` is
listed so the catalog can state plainly that a registry a reader might
expect is *not* wired in. Such blocks never carry a pillar weight.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import lru_cache
from types import MappingProxyType

from .. import config, provenance

log = logging.getLogger("wattershed.versioning")

# --- vocabularies -----------------------------------------------------------

# How the block enters the tool. Drives what "current" can even mean.
STATIC_SNAPSHOT = "static_snapshot"    # bulk file pinned at reference-build time
API_LIVE = "api_live"                  # queried per screening run
PERIODIC_BULK = "periodic_bulk"        # bulk file refreshed on a cadence
TRANSCRIBED = "transcribed_constant"   # constants hand-copied from a citation

ACTIVE = "active"
DECLARED_NOT_INGESTED = "declared_not_ingested"


@dataclass(frozen=True)
class IndexBlock:
    """One addressable unit of ingested data, versioned and resolution-typed."""

    block_id: str
    source_id: str                 # FK into provenance.SOURCES (validated below)
    pillar: str                    # water | grid | burden | cross-cutting | none
    role: str                      # what it contributes, one line
    ingestion_mode: str
    published: str                 # WHEN THE PUBLISHER RELEASED IT (varying granularity)
    describes: str                 # period the data describes (mirrors Source.vintage)
    spatial_unit: str              # native geometry the value resolves to
    spatial_note: str = ""         # coarsening/aggregation actually applied
    refresh_cadence: str = ""      # how often upstream changes
    cache_file: str = ""           # filename under data/cache, if it lands on disk
    status: str = ACTIVE
    caveat: str = ""               # surfaced verbatim; never silently dropped


def _b(**kw) -> IndexBlock:
    return IndexBlock(**kw)


_BLOCKS: tuple[IndexBlock, ...] = (
    # ---------------- WATER STRESS ----------------
    _b(
        block_id="water.baseline_stress",
        source_id="aqueduct40",
        pillar="water",
        role="Baseline water stress (withdrawals ÷ renewable supply) — structural scarcity",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2023-08",
        describes="baseline period 1979–2019",
        spatial_unit="hydrological sub-basin polygon",
        spatial_note=(
            "Native Aqueduct 4.0 sub-basin geometry; variable area, no raster cell size. "
            "U.S. clip committed as data/processed/aqueduct_bws_us.gpkg."
        ),
        refresh_cadence="major release (4.0 superseded 3.0 after 4 years)",
        cache_file="aqueduct40.zip",
    ),
    _b(
        block_id="water.drought_current",
        source_id="usdm_current",
        pillar="water",
        role="Current drought category at the point — the dynamic water signal",
        ingestion_mode=PERIODIC_BULK,
        published="rolling — weekly Thursday release",
        describes="the week of the release",
        spatial_unit="drought polygon (analyst-delineated)",
        spatial_note="Generalized to roughly county / sub-county scale; not a gridded product.",
        refresh_cadence="weekly (Thursday); cached ≤3 days",
        cache_file="usdm_current.zip",
    ),
    _b(
        block_id="water.drought_climatology",
        source_id="usdm_county_history",
        pillar="water",
        role="5-year county DSCI climatology — distinguishes chronic from episodic drought",
        ingestion_mode=API_LIVE,
        published="rolling — weekly series since 2000",
        describes="weekly series, 2000–present",
        spatial_unit="county",
        refresh_cadence="weekly",
    ),
    _b(
        block_id="water.county_use_denominator",
        source_id="usgs_wateruse_2015",
        pillar="water",
        role="County public-supply withdrawal denominator for modeled demand comparison",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2018",
        describes="calendar 2015",
        spatial_unit="county",
        refresh_cadence="~5-yearly compilation; 2015 remains the latest complete county census",
        cache_file="usco2015v2.0.csv",
        caveat=(
            "Eleven years stale as of screening. Flagged LOW confidence for counties with "
            "material post-2015 demand change; it is a denominator, never a score input."
        ),
    ),
    _b(
        block_id="water.usgs_realtime_hydrology",
        source_id="usgs_wateruse_2015",
        pillar="none",
        role="NOT INGESTED — real-time gauge hydrology (USGS NWIS/Water Services) is not read by this tool",
        ingestion_mode=API_LIVE,
        published="n/a",
        describes="n/a",
        spatial_unit="gauge point",
        status=DECLARED_NOT_INGESTED,
        caveat=(
            "Declared explicitly to prevent a plausible misreading: the water pillar's dynamic "
            "component is USDM weekly drought, not USGS real-time streamflow. Instantaneous "
            "gauge discharge is a poor proxy for siting-horizon supply risk and no NWIS "
            "endpoint is called anywhere in the codebase."
        ),
    ),
    # ---------------- GRID STRAIN & CARBON ----------------
    _b(
        block_id="grid.emissions_factors",
        source_id="egrid2023",
        pillar="grid",
        role="Subregion CO₂e output emission rate, fuel mix, and annual net generation",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2025-06",
        describes="calendar 2023 operations",
        spatial_unit="eGRID subregion",
        spatial_note=(
            "Annual average, location-based accounting — NOT marginal or hourly emissions. "
            "A subregion spans multiple states; the point inherits the whole subregion's rate."
        ),
        refresh_cadence="annual, ~2-year publication lag",
        cache_file="egrid2023_data_rev2.xlsx",
    ),
    _b(
        block_id="grid.subregion_geometry",
        source_id="egrid_subregions_gis",
        pillar="grid",
        role="Point-in-polygon assignment of a site to its eGRID subregion",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2025-01",
        describes="eGRID2023 topology",
        spatial_unit="eGRID subregion polygon",
        refresh_cadence="with each eGRID release",
        cache_file="egrid2023_subregions.zip",
    ),
    _b(
        block_id="grid.resource_adequacy",
        source_id="nerc_ltra_2025",
        pillar="grid",
        role="Forward resource-adequacy risk category for the assessment area",
        ingestion_mode=TRANSCRIBED,
        published=provenance.NERC_LTRA_PUBLISHED_ISO,
        describes=f"assessment horizon {provenance.NERC_LTRA_HORIZON}",
        spatial_unit="NERC assessment area",
        spatial_note=(
            "Coarser than eGRID subregion; joined via a hand-maintained crosswalk "
            "(data/reference/egrid_subregion_map.csv). Imperfect mappings are documented."
        ),
        refresh_cadence="annual (December)",
        caveat=(
            "Categorical risk designations are hand-transcribed from the published PDF and "
            "are checkable against it. Publication date and horizon come from "
            "provenance.NERC_LTRA_* so every surface cites one verified edition."
        ),
    ),
    _b(
        block_id="grid.eia_hourly_ba",
        source_id="egrid2023",
        pillar="none",
        role="NOT INGESTED — EIA-930 hourly balancing-authority operations are not read by this tool",
        ingestion_mode=API_LIVE,
        published="n/a",
        describes="n/a",
        spatial_unit="balancing authority",
        status=DECLARED_NOT_INGESTED,
        caveat=(
            "config.EIA_API_KEY exists as an unused optional hook; no EIA endpoint is called. "
            "The grid pillar is annual-average (eGRID) plus forward-looking categorical (NERC). "
            "Hourly BA data would enable marginal/time-matched emissions — a documented v2 "
            "roadmap item, not a current input. See docs/LIMITATIONS.md."
        ),
    ),
    # ---------------- COMMUNITY BURDEN ----------------
    _b(
        block_id="burden.health_prevalence",
        source_id="cdc_places_2024",
        pillar="burden",
        role="Tract adult-asthma and fair/poor self-rated health prevalence",
        ingestion_mode=API_LIVE,
        published="2024",
        describes="model year 2022 (BRFSS 2022)",
        spatial_unit="census tract",
        spatial_note=(
            "Small-area MODELED estimates, not direct measurement — tract values are "
            "synthesized from BRFSS respondents plus tract covariates."
        ),
        refresh_cadence="annual release",
        cache_file="places_tract_2024.csv",
    ),
    _b(
        block_id="burden.facility_proximity",
        source_id="frs_national",
        pillar="burden",
        role="TRI / Superfund / RCRA facility coordinates → 5 km proximity and per-tract density",
        ingestion_mode=STATIC_SNAPSHOT,
        published="rolling — snapshot at retrieval date",
        describes="rolling facility registry",
        spatial_unit="facility point coordinate",
        spatial_note=(
            "Point locations buffered to 5 km per EJScreen's proximity convention. "
            "This is the facility REGISTRY (FRS), not annual TRI release quantities."
        ),
        refresh_cadence="continuous upstream; re-pulled at reference build",
        cache_file="frs_national_single.zip",
    ),
    _b(
        block_id="burden.tri_facility_detail",
        source_id="envirofacts_tri",
        pillar="burden",
        role="Live per-site TRI facility enrichment (names, programs) for nearby facilities",
        ingestion_mode=API_LIVE,
        published="rolling",
        describes="rolling",
        spatial_unit="facility point coordinate",
        spatial_note="Enrichment only — displayed as context, carries no score weight.",
        refresh_cadence="continuous",
        caveat=(
            "TRI *release* tonnage logs are not ingested. Toxics burden enters the index "
            "through EJScreen's RSEI-modeled air-toxics field, not raw TRI reporting."
        ),
    ),
    _b(
        block_id="burden.socioeconomic",
        source_id="acs_2023_5yr",
        pillar="burden",
        role="Tract low-income, unemployment, limited-English, education, race/ethnicity, population",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2024-12",
        describes="pooled 2019–2023 5-year",
        spatial_unit="census tract",
        spatial_note="5-year pooled estimates carry margins of error that are not propagated into the index.",
        refresh_cadence="annual (December)",
        cache_file="acsdt5y2023-c17002.dat",
    ),
    _b(
        block_id="burden.pollution_indicators",
        source_id="ejscreen_v232_replica",
        pillar="burden",
        role="Nine frozen pollution-burden indicators (PM2.5, ozone, NO₂, diesel PM, air toxics, traffic, NPL/RMP/TSDF proximity)",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2024",
        describes="EJScreen 2.32 (ACS 2018–2022 inputs; AirToxScreen 2020)",
        spatial_unit="census tract (aggregated from block group)",
        spatial_note=(
            "Native geometry is block group; aggregated to tract population-weighted at "
            "reference build. Aggregation smooths within-tract variation."
        ),
        refresh_cadence="FROZEN — EPA withdrew EJScreen in February 2025",
        cache_file="ejscreen_v232_tract.parquet",
        caveat=(
            "Vintage cannot advance. Sourced from the Public Environmental Data Partners "
            "restoration of the final public release; alternates at Harvard Dataverse "
            "doi:10.7910/DVN/RLR5AX and Zenodo doi:10.5281/zenodo.14767363."
        ),
    ),
    # ---------------- CONTEXT LAYERS (refreshed by the bi-weekly sync) ----------------
    # pillar="context" is load-bearing: these are ingested and current, but they
    # feed NO score. Keeping them out of the three pillars is what stops an
    # unattended twice-monthly job from moving a published screening result.
    _b(
        block_id="infra.facility_registry",
        source_id="osm_datacenters",
        pillar="context",
        role="Data-centre facility locations → per-tract clustering (Infrastructure Density Modifier)",
        ingestion_mode=API_LIVE,
        published="rolling — snapshot at each sync",
        describes="OSM database state at fetch time",
        spatial_unit="facility point (node or way centroid)",
        spatial_note=(
            "Assigned to an exact census tract by FCC point-in-polygon, cached per "
            "facility so each cycle geocodes only newly discovered sites."
        ),
        refresh_cadence="bi-weekly (1st and 15th) via .github/workflows/data_sync.yml",
        cache_file="",
        caveat=(
            "Crowd-sourced and not exhaustive. Descriptive context only — deliberately "
            "excluded from all three pillars, and from the siting-equity study, where "
            "feeding data-centre density into the burden pillar would be circular."
        ),
    ),
    _b(
        block_id="infra.announcement_leads",
        source_id="google_news_rss",
        pillar="context",
        role="Announcement / permit / construction headlines for human review",
        ingestion_mode=API_LIVE,
        published="rolling",
        describes="trailing weeks of press coverage",
        spatial_unit="none (headline text, not georeferenced)",
        refresh_cadence="bi-weekly (1st and 15th)",
        caveat=(
            "UNVERIFIED secondary reporting, capped at 400 retained items. Never a "
            "measurement, never a score input; every record carries verified=false."
        ),
    ),
    _b(
        block_id="infra.eia_capacity",
        source_id="eia_v2_capacity",
        pillar="context",
        role="Operating generator capacity by balancing authority — supply-side context",
        ingestion_mode=API_LIVE,
        published="monthly",
        describes="most recent monthly capacity listing",
        spatial_unit="balancing authority / state",
        refresh_cadence="bi-weekly poll of a monthly series",
        caveat=(
            "OPTIONAL and key-gated — the one registered source that is not keyless. "
            "Skipped cleanly when EIA_API_KEY is unset. Supply-side capacity only; the "
            "EIA-930 hourly feed remains uningested (see grid.eia_hourly_ba)."
        ),
    ),

    # ---------------- CROSS-CUTTING ----------------
    _b(
        block_id="geo.tract_assignment",
        source_id="census_geocoder",
        pillar="cross-cutting",
        role="Address / coordinate → census tract and county assignment",
        ingestion_mode=API_LIVE,
        published="rolling — current TIGER benchmark",
        describes="current benchmark",
        spatial_unit="census tract polygon",
        refresh_cadence="benchmark updates",
    ),
    _b(
        block_id="geo.tract_centroids",
        source_id="census_gazetteer_2024",
        pillar="cross-cutting",
        role="Population-weighted tract centroids for the 5 km neighborhood summary",
        ingestion_mode=STATIC_SNAPSHOT,
        published="2024",
        describes="2024 TIGER geography",
        spatial_unit="tract centroid point",
        spatial_note=(
            "Centroid membership, not areal intersection — a large tract counts wholly in "
            "or wholly out of the 5 km buffer."
        ),
        refresh_cadence="annual",
        cache_file="gaz_tracts_national.zip",
    ),
)

# Immutable registry — callers get a read-only view, never a mutable dict.
BLOCKS: MappingProxyType = MappingProxyType({b.block_id: b for b in _BLOCKS})

PILLAR_LABELS = MappingProxyType(
    {
        "water": "Water stress",
        "grid": "Grid strain & carbon",
        "burden": "Community burden",
    }
)


@lru_cache(maxsize=128)
def _stamp_for(cache_file: str, _mtime: float) -> str | None:
    """Read a cached file's retrieval stamp. Keyed on mtime so a refreshed
    download invalidates the entry rather than pinning a stale timestamp."""
    return provenance.retrieved_at(config.CACHE_DIR / cache_file)


class DataVersionController:
    """Single authority on what version of what is loaded, and at what resolution.

    Stateless by construction: every accessor derives from the frozen BLOCKS
    mapping plus an on-demand stamp read, so long-lived processes (the CLI,
    the batch screener, CI) hold no growing state.
    """

    def __init__(self) -> None:
        unknown = {b.source_id for b in BLOCKS.values()} - set(provenance.SOURCES)
        if unknown:
            raise KeyError(f"IndexBlock references unregistered source(s): {sorted(unknown)}")
        log.debug("DataVersionController ready — %d blocks across %d sources",
                  len(BLOCKS), len({b.source_id for b in BLOCKS.values()}))

    # -- lookups -------------------------------------------------------------

    def block(self, block_id: str) -> IndexBlock:
        return BLOCKS[block_id]

    def blocks_for_pillar(self, pillar: str) -> list[IndexBlock]:
        """Active blocks feeding a pillar, plus any explicitly-not-ingested
        registries declared against it. Order is declaration order."""
        return [b for b in BLOCKS.values() if b.pillar == pillar]

    @property
    def active_blocks(self) -> list[IndexBlock]:
        return [b for b in BLOCKS.values() if b.status == ACTIVE]

    # -- resolution ----------------------------------------------------------

    def observed_retrieval(self, block_id: str) -> str | None:
        """Actual fetch timestamp from the on-disk stamp, or None if the block
        is API-live (stamped per run, in the screening ledger) or uncached."""
        b = BLOCKS[block_id]
        if not b.cache_file:
            return None
        p = config.CACHE_DIR / b.cache_file
        if not p.exists():
            return None
        return _stamp_for(b.cache_file, p.stat().st_mtime)

    def resolve(self, block_id: str) -> dict:
        """Static declaration joined to the observed state on disk."""
        b = BLOCKS[block_id]
        src = provenance.SOURCES[b.source_id]
        rec = asdict(b)
        rec.update(
            {
                "source_name": src.name,
                "provider": src.provider,
                "url": src.url,
                "license": src.license,
                "observed_retrieval": self.observed_retrieval(block_id),
            }
        )
        return rec

    def lineage(self, pillar: str) -> list[dict]:
        return [self.resolve(b.block_id) for b in self.blocks_for_pillar(pillar)]

    # -- integrity -----------------------------------------------------------

    def uningested_declarations(self) -> list[IndexBlock]:
        """Registries a reader might reasonably expect that we do NOT read."""
        return [b for b in BLOCKS.values() if b.status == DECLARED_NOT_INGESTED]

    def stale_report(self) -> list[dict]:
        """Blocks whose cached file has no retrieval stamp — a reproducibility
        gap, surfaced rather than hidden."""
        out = []
        for b in self.active_blocks:
            if b.cache_file and self.observed_retrieval(b.block_id) is None:
                out.append({"block_id": b.block_id, "cache_file": b.cache_file})
        return out


@lru_cache(maxsize=1)
def controller() -> DataVersionController:
    """Process-wide singleton. Cheap to construct; cached so callers can ask
    freely without re-validating the registry each time."""
    return DataVersionController()


__all__ = [
    "ACTIVE",
    "BLOCKS",
    "DECLARED_NOT_INGESTED",
    "PILLAR_LABELS",
    "DataVersionController",
    "IndexBlock",
    "controller",
]
