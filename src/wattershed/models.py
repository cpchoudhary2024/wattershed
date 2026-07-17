"""Typed result models. These define the JSON contract of a screening run."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    HIGH = "high"        # current-vintage data at appropriate resolution
    MEDIUM = "medium"    # usable but dated, modeled, or resolution-mismatched
    LOW = "low"          # meaningful caveats; treat as indicative only


class Tier(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    ELEVATED = "Elevated"
    HIGH = "High"


class CoolingTech(str, Enum):
    EVAPORATIVE = "evaporative"   # open/closed-circuit cooling towers
    HYBRID = "hybrid"             # water-side economizer + trim evaporative
    AIR = "air"                   # dry coolers / air-side economization
    UNKNOWN = "unknown"


class Indicator(BaseModel):
    """One measured/derived quantity with its full defensibility trail."""

    id: str
    label: str
    value: Optional[float] = None
    display: str = ""                 # human-readable value w/ unit
    unit: str = ""
    percentile: Optional[float] = None  # national percentile, higher = more concerning
    source_id: str
    vintage: str = ""
    retrieved: str = ""
    confidence: Confidence = Confidence.HIGH
    note: str = ""                    # caveat surfaced verbatim in reports
    missing: bool = False             # data gap — rendered as such, never imputed


class PillarScore(BaseModel):
    pillar: str                       # "water" | "grid" | "burden"
    score: Optional[float] = None     # 0–100, higher = more concerning; None if insufficient data
    band: str = ""                    # qualitative band for the score
    indicators: list[Indicator] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)   # plain-language "why this score"
    data_gaps: list[str] = Field(default_factory=list)
    components: dict[str, float] = Field(default_factory=dict)  # sub-score decomposition


class DemandScenario(BaseModel):
    cooling: str
    pue: float
    wue_l_per_kwh_it: float
    facility_energy_mwh_yr: float
    water_mgal_yr: Optional[float] = None
    water_mgd: Optional[float] = None
    pct_county_public_supply: Optional[float] = None
    co2e_tonnes_yr: Optional[float] = None


class DemandModel(BaseModel):
    """Modeled resource demand for a hypothetical/announced load. All modeled,
    clearly labeled — never presented as measured facility data."""

    it_mw: float
    utilization: float
    it_energy_mwh_yr: float
    scenarios: list[DemandScenario]
    indirect_water_note: str = ""
    grid_share_note: str = ""
    assumptions_source_ids: list[str] = Field(default_factory=list)


class Mitigation(BaseModel):
    pillar: str
    title: str
    detail: str
    precedent: str = ""               # real-world example, cited


class SiteInput(BaseModel):
    name: str
    lat: float
    lon: float
    slug: str = ""
    address: str = ""
    operator: str = ""
    status: str = ""                  # operating | construction | proposed | contested | rejected
    it_mw: Optional[float] = None
    cooling: CoolingTech = CoolingTech.UNKNOWN
    coord_precision: str = ""         # parcel | address | locality — honesty about geocoding
    provenance: list[dict[str, Any]] = Field(default_factory=list)  # citations for curated facts
    notes: str = ""


class GeoContext(BaseModel):
    tract_geoid: str = ""
    county_fips: str = ""
    county_name: str = ""
    state_abbr: str = ""
    state_name: str = ""
    tract_population: Optional[float] = None
    matched_address: str = ""


class Screening(BaseModel):
    """Complete screening result for one site — the unit of output."""

    site: SiteInput
    geo: GeoContext
    tier: Tier
    tier_reasons: list[str]
    water: PillarScore
    grid: PillarScore
    burden: PillarScore
    demand: Optional[DemandModel] = None
    mitigations: list[Mitigation] = Field(default_factory=list)
    neighborhood: dict[str, Any] = Field(default_factory=dict)  # 5 km pop-weighted context
    nearby_facilities: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)  # ledger records
    limitations: list[str] = Field(default_factory=list)
    generated_at: str = ""
    tool_version: str = ""

    def to_json(self, **kw) -> str:
        return self.model_dump_json(indent=2, **kw)
