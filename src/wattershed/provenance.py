# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Provenance ledger: every number Wattershed reports carries its source.

Design rule: a screening output is only as defensible as its weakest citation,
so sources are registered once here (with provider, vintage, license, and URL)
and every Indicator stores the `source_id` plus the actual retrieval timestamp
of the underlying file/API call. Reports render this as a bibliography; JSON
output embeds it verbatim.

`vintage` is the period the data DESCRIBES; `retrieved` (stored on cached
files and stamped into results) is when WE fetched it. The distinction matters:
e.g. eGRID2023 describes calendar-2023 grid operations but was published in
2025 and fetched in 2026.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# --- Canonical citation constants -------------------------------------------
# Some citations are repeated across the scorer, the CLI freshness table, the
# catalog and the docs. Repeating the literal is how they drift: the NERC
# assessment carried one publication month here and a different one in
# three other files, plus two different horizons. Declaring it once and
# importing it makes that class of drift structurally impossible, and
# test_citation_alignment.py fails the build if a stray literal reappears.
#
# Verified 2026-08-21: the PDF is titled "Long-Term Reliability Assessment,
# January 2026" (released 2026-01-29). The horizon below is the full 10-year
# outlook — the transcribed risk table in data/reference/nerc_ltra.csv carries
# designations through 2035, so the narrower five-year window previously cited
# in the scorer and CLI understated its scope.
NERC_LTRA_EDITION = "NERC 2025 Long-Term Reliability Assessment"
NERC_LTRA_PUBLISHED = "January 2026"
NERC_LTRA_PUBLISHED_ISO = "2026-01"
NERC_LTRA_HORIZON = "2026\u20132035"
NERC_LTRA_URL = "https://www.nerc.com/globalassets/our-work/assessments/nerc_ltra_2025.pdf"
NERC_LTRA_VINTAGE = (
    f"assessment horizon {NERC_LTRA_HORIZON} (published {NERC_LTRA_PUBLISHED})"
)


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    provider: str
    url: str
    vintage: str  # period described by the data
    license: str
    notes: str = ""


# Registry of every upstream source the tool can touch. Additions must include
# vintage and license — CI has a test enforcing non-empty fields.
SOURCES: dict[str, Source] = {
    s.id: s
    for s in [
        Source(
            id="usdm_current",
            name="U.S. Drought Monitor — current weekly map",
            provider="NDMC / USDA / NOAA (Univ. of Nebraska–Lincoln)",
            url="https://droughtmonitor.unl.edu/data/shapefiles_m/USDM_current_M.zip",
            vintage="updated weekly (Thursday release)",
            license=(
                "Public. Courtesy line: 'The U.S. Drought Monitor is jointly produced by the "
                "National Drought Mitigation Center at the University of Nebraska-Lincoln, the "
                "United States Department of Agriculture, and the National Oceanic and "
                "Atmospheric Administration.'"
            ),
        ),
        Source(
            id="usdm_county_history",
            name="U.S. Drought Monitor — county drought-severity time series",
            provider="NDMC data services (usdmdataservices.unl.edu)",
            url="https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent",
            vintage="weekly series, 2000–present",
            license="Public (same courtesy line as USDM).",
        ),
        Source(
            id="aqueduct40",
            name="WRI Aqueduct 4.0 — baseline water stress (bws), annual, sub-basin",
            provider="World Resources Institute",
            url="https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip",
            vintage="baseline period 1979–2019 (published 2023)",
            license="CC BY 4.0 — attribution: 'Kuzma et al. (2023). Aqueduct 4.0, World Resources Institute.'",
        ),
        Source(
            id="usgs_wateruse_2015",
            name="USGS Estimated Use of Water in the U.S. — county-level, 2015",
            provider="U.S. Geological Survey (ScienceBase)",
            url="https://www.sciencebase.gov/catalog/item/5af3311be4b0da30c1b245d8",
            vintage="calendar 2015 (most recent complete county compilation)",
            license="Public domain (USGS). doi:10.5066/F7TB15V5",
            notes="2015 remains the latest full county water-use census; flagged LOW-confidence for change-sensitive counties.",
        ),
        Source(
            id="egrid2023",
            name="EPA eGRID2023 (rev. 2, June 2025) — subregion emission rates, fuel mix, net generation",
            provider="U.S. EPA",
            url="https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx",
            vintage="calendar 2023 operations",
            license="Public domain (U.S. federal work).",
        ),
        Source(
            id="egrid_subregions_gis",
            name="EPA eGRID2023 subregion boundaries (shapefile)",
            provider="U.S. EPA",
            url="https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip",
            vintage="eGRID2023 topology",
            license="Public domain (U.S. federal work).",
        ),
        Source(
            id="census_geocoder",
            name="U.S. Census Bureau geocoder (address & coordinate → tract/county)",
            provider="U.S. Census Bureau",
            url="https://geocoding.geo.census.gov/geocoder/",
            vintage="current TIGER benchmark",
            license="Public domain.",
        ),
        Source(
            id="acs_2023_5yr",
            name="American Community Survey 2019–2023 5-year, tract tables (bulk summary file)",
            provider="U.S. Census Bureau",
            url="https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/",
            vintage="pooled 2019–2023",
            license="Public domain.",
            notes="Tables C17002, B23025, C16002, B15003, B03002, B01003.",
        ),
        Source(
            id="cdc_places_2024",
            name="CDC PLACES 2024 release — census-tract health outcomes",
            provider="CDC (data.cdc.gov, Socrata)",
            url="https://data.cdc.gov/resource/cwsq-ngmh.json",
            vintage="model year 2022 (BRFSS 2022, released 2024)",
            license="Public domain.",
            notes="Measures: CASTHMA (adult asthma), GHLTH (fair/poor self-rated health).",
        ),
        Source(
            id="frs_national",
            name="EPA Facility Registry Service — national geocoded facility file",
            provider="U.S. EPA",
            url="https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip",
            vintage="rolling (snapshot at retrieval date)",
            license="Public domain.",
            notes="Used for TRI / Superfund (SEMS) / RCRA facility proximity.",
        ),
        Source(
            id="envirofacts_tri",
            name="EPA Envirofacts — TRI facility detail (live per-site enrichment)",
            provider="U.S. EPA",
            url="https://data.epa.gov/efservice/",
            vintage="rolling",
            license="Public domain.",
        ),
        Source(
            id="ejscreen_v232_replica",
            name="EPA EJScreen 2.32 tract data (community-restored replica)",
            provider="Public Environmental Data Partners (original: U.S. EPA)",
            url="https://screening-tools.com/epa-ejscreen",
            vintage="EJScreen 2.32 (2024 release; ACS 2018–2022 inputs; AirToxScreen 2020)",
            license="Public domain (U.S. federal work product, community-rehosted).",
            notes=(
                "EPA removed EJScreen from public access in February 2025. Five pollution-burden "
                "fields (PM2.5, ozone, diesel PM, air-toxics cancer risk, traffic proximity) are "
                "taken from the restored final release because their upstream models (AirToxScreen, "
                "FHWA AADT fusion) are impractical to rebuild live. Vintage is frozen and flagged."
            ),
        ),
        Source(
            id="nerc_ltra_2025",
            name=f"{NERC_LTRA_EDITION} — resource-adequacy risk categories",
            provider="North American Electric Reliability Corporation",
            url=NERC_LTRA_URL,
            vintage=NERC_LTRA_VINTAGE,
            license="Publicly released assessment; categorical risk designations transcribed to data/reference/nerc_ltra.csv.",
        ),
        Source(
            id="lbnl_demand_2024",
            name="LBNL 2024 United States Data Center Energy Usage Report (demand-model constants)",
            provider="Lawrence Berkeley National Laboratory (Shehabi et al.)",
            url="https://eta.lbl.gov/publications/2024-lbnl-data-center-energy-usage-report",
            vintage="published Dec 2024",
            license="Public report; constants transcribed with citation.",
            notes="PUE/WUE scenario ranges for the demand model; see demand.py.",
        ),
        Source(
            id="macknick_2012",
            name="Macknick et al. (2012) — operational water consumption by generation technology",
            provider="NREL / Environmental Research Letters 7 045802",
            url="https://iopscience.iop.org/article/10.1088/1748-9326/7/4/045802",
            vintage="literature medians (2012)",
            license="Open-access article; median factors transcribed.",
            notes="Used with eGRID fuel mix to estimate regional indirect (power-plant) water intensity.",
        ),
        Source(
            id="epa_ghg_equiv",
            name="EPA Greenhouse Gas Equivalencies (passenger-vehicle factor)",
            provider="U.S. EPA",
            url="https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator",
            vintage="2024 update",
            license="Public domain.",
        ),
        Source(
            id="census_gazetteer_2024",
            name="Census 2024 national tract gazetteer (population-weighted centroids)",
            provider="U.S. Census Bureau",
            url="https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_tracts_national.zip",
            vintage="2024 TIGER geography",
            license="Public domain.",
        ),
        Source(
            id="osm_datacenters",
            name="OpenStreetMap — data-centre facility tags (telecom=data_center)",
            provider="OpenStreetMap contributors (via Overpass API)",
            url="https://overpass-api.de/api/interpreter",
            vintage="rolling — snapshot at each sync",
            license="ODbL 1.0 — © OpenStreetMap contributors.",
            notes=(
                "Crowd-sourced and NOT exhaustive: coverage varies by region and a campus "
                "is only present once a mapper adds it. Feeds the descriptive infrastructure-"
                "density layer only; never a pillar score."
            ),
        ),
        Source(
            id="google_news_rss",
            name="Google News RSS — data-centre announcement leads",
            provider="Google News (aggregator of third-party publishers)",
            url="https://news.google.com/rss/search",
            vintage="rolling — trailing weeks at each sync",
            license="Headlines and links only; each item links to its publisher.",
            notes=(
                "UNVERIFIED secondary reporting. Lead generation for human review — "
                "explicitly not a measurement and not an input to any score."
            ),
        ),
        Source(
            id="eia_v2_capacity",
            name="EIA v2 — operating generator capacity by balancing authority",
            provider="U.S. Energy Information Administration",
            url="https://api.eia.gov/v2/electricity/operating-generator-capacity/data/",
            vintage="monthly series",
            license="Public domain (U.S. federal work). Requires a free API key.",
            notes=(
                "OPTIONAL and key-gated — the only registered source that is not keyless. "
                "Absent EIA_API_KEY the sync skips it and succeeds. Supply-side capacity "
                "context; NOT the EIA-930 hourly balancing-authority feed."
            ),
        ),
        Source(
            id="curated_sites",
            name="Wattershed hand-curated data-center site registry",
            provider="this repository (manually compiled from cited public reporting)",
            url="data/curated/sites.yaml",
            vintage="per-site citation dates in the registry",
            license="MIT (compilation); each fact cites its public source.",
            notes="NOT exhaustive and NOT authoritative — see per-site provenance blocks.",
        ),
    ]
}


def get_source(source_id: str) -> Source:
    return SOURCES[source_id]


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Ledger:
    """Per-run record of which sources were actually consulted and when."""

    entries: dict[str, str] = field(default_factory=dict)  # source_id -> retrieved iso ts

    def touch(self, source_id: str, retrieved: str | None = None) -> None:
        if source_id not in SOURCES:
            raise KeyError(f"Unregistered source: {source_id}")
        self.entries.setdefault(source_id, retrieved or utc_now_iso())

    def to_records(self) -> list[dict]:
        out = []
        for sid, ts in sorted(self.entries.items()):
            s = SOURCES[sid]
            out.append(
                {
                    "source_id": sid,
                    "name": s.name,
                    "provider": s.provider,
                    "url": s.url,
                    "vintage": s.vintage,
                    "license": s.license,
                    "retrieved": ts,
                    "notes": s.notes,
                }
            )
        return out


def stamp_file(path: Path, source_id: str) -> None:
    """Record retrieval metadata next to a cached file (path + '.meta.json')."""
    meta = {
        "source_id": source_id,
        "url": SOURCES[source_id].url,
        "retrieved": utc_now_iso(),
    }
    Path(str(path) + ".meta.json").write_text(json.dumps(meta, indent=2))


def read_stamp(path: Path) -> dict | None:
    p = Path(str(path) + ".meta.json")
    if p.exists():
        return json.loads(p.read_text())
    return None


def retrieved_at(path: Path) -> str | None:
    meta = read_stamp(path)
    return meta["retrieved"] if meta else None


__all__ = [
    "NERC_LTRA_EDITION",
    "NERC_LTRA_HORIZON",
    "NERC_LTRA_PUBLISHED",
    "NERC_LTRA_PUBLISHED_ISO",
    "NERC_LTRA_URL",
    "NERC_LTRA_VINTAGE",
    "SOURCES",
    "Ledger",
    "Source",
    "get_source",
    "read_stamp",
    "retrieved_at",
    "stamp_file",
    "utc_now_iso",
]
