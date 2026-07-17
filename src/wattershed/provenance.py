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
from datetime import datetime, timezone
from pathlib import Path

from . import config


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
            name="NERC 2025 Long-Term Reliability Assessment — resource-adequacy risk categories",
            provider="North American Electric Reliability Corporation",
            url="https://www.nerc.com/pa/RAPA/ra/Reliability%20Assessments%20DL/NERC_LTRA_2025.pdf",
            vintage="assessment horizon 2026–2035 (published Dec 2025)",
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    "Source",
    "SOURCES",
    "Ledger",
    "get_source",
    "stamp_file",
    "read_stamp",
    "retrieved_at",
    "utc_now_iso",
]
