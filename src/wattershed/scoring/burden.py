"""Cumulative community-burden pillar (0–100).

CalEnviroScreen-style multiplicative structure, rebuilt at tract level from
primary sources after EJScreen's 2025 takedown:

  P — pollution-burden domain: mean national percentile of up to 10
      indicators (PM2.5, ozone, diesel PM, air-toxics cancer risk &
      respiratory HI, traffic proximity, NPL/RMP/TSDF proximity, live TRI
      density).
  V — population-vulnerability domain: mean national percentile of up to 6
      indicators (low income, unemployment, limited-English households,
      no HS diploma, adult asthma, fair/poor health).

  CBI = P × V / 100, then ranked against all U.S. tracts.

The multiplicative form (vs. additive) encodes the cumulative-impact premise:
pollution landing on a vulnerable population is worse than either alone.
Race/ethnicity is reported for transparency but is NOT a scoring input —
the index screens on environmental and socioeconomic measures (methodology
§4 discusses this choice). Coverage floors prevent synthesizing a domain from
sparse data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import Confidence, Indicator, PillarScore
from . import reference

# (column, label, source_id, vintage, confidence)
_POLLUTION_META = [
    ("pm25", "PM2.5 concentration", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("ozone", "Ozone concentration", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("no2", "NO₂ concentration", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("diesel_pm", "Diesel particulate matter", "ejscreen_v232_replica", "AirToxScreen 2020", Confidence.MEDIUM),
    ("rsei_air_toxics", "Toxic releases to air (RSEI-modeled)", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("traffic_proximity", "Traffic proximity & volume", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("npl_proximity", "Superfund (NPL) site proximity", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("rmp_proximity", "RMP (chemical-accident) facility proximity", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("tsdf_proximity", "Hazardous-waste TSDF proximity", "ejscreen_v232_replica", "EJScreen 2.32 (2024)", Confidence.MEDIUM),
    ("tri_count_5km", "TRI facilities within 5 km (live rebuild)", "frs_national", "FRS snapshot at build date", Confidence.HIGH),
]
_VULN_META = [
    ("pct_low_income", "Low-income share (<2× poverty)", "acs_2023_5yr", "ACS 2019–2023", Confidence.HIGH),
    ("pct_unemployed", "Unemployment rate", "acs_2023_5yr", "ACS 2019–2023", Confidence.HIGH),
    ("pct_limited_english_hh", "Limited-English households", "acs_2023_5yr", "ACS 2019–2023", Confidence.HIGH),
    ("pct_no_hs_diploma", "Adults without HS diploma", "acs_2023_5yr", "ACS 2019–2023", Confidence.HIGH),
    ("pct_adult_asthma", "Adult asthma prevalence", "cdc_places_2024", "CDC PLACES 2024 (BRFSS 2022)", Confidence.MEDIUM),
    ("pct_fair_poor_health", "Fair/poor self-rated health", "cdc_places_2024", "CDC PLACES 2024 (BRFSS 2022)", Confidence.MEDIUM),
]


def band(score: float | None) -> str:
    if score is None:
        return "insufficient data"
    if score >= 90:
        return "severe"
    if score >= 75:
        return "high"
    if score >= 50:
        return "moderate"
    return "low"


def _fmt(v: float, col: str) -> str:
    if col.startswith("pct_"):
        return f"{v:.1f}%"
    if col == "tri_count_5km":
        return f"{v:.0f} facilities"
    return f"{v:.3g}"


def score_burden(geoid: str, lat: float | None = None, lon: float | None = None) -> tuple[PillarScore, dict]:
    """Score the containing tract; if it is unpopulated (industrial/special-use
    tracts carry no percentile ranks), fall back to the 5 km population-weighted
    neighborhood — the people the screening question is actually about."""
    row = reference.tract_row(geoid)
    basis_note = ""
    if row is not None and (pd.isna(row.get("population")) or row.get("population", 0) < 50):
        row = None  # force neighborhood basis for unpopulated tracts
        basis_note = (
            f"Containing tract {geoid} is unpopulated special-use land; burden scored over the "
            "5 km population-weighted neighborhood instead. Percentile values are neighborhood "
            "means, an approximation of a true national percentile."
        )
    if row is None and lat is not None and lon is not None:
        nb = reference.neighborhood_row(lat, lon)
        if nb is not None:
            row, meta = nb
            basis_note = basis_note or (
                f"Tract {geoid} absent from reference table; scored over the 5 km "
                "population-weighted neighborhood."
            )
    if row is None:
        ps = PillarScore(
            pillar="burden",
            score=None,
            band="insufficient data",
            data_gaps=[f"Tract {geoid} not present in the national reference table and no "
                       "populated tracts within 5 km."],
        )
        return ps, {}

    dom = reference.domain_scores(row)
    indicators: list[Indicator] = []
    drivers: list[str] = []
    gaps: list[str] = []

    for col, label, src, vintage, conf in _POLLUTION_META + _VULN_META:
        val = row.get(col)
        pct = row.get(reference.pct_col(col))
        missing = val is None or (isinstance(val, float) and np.isnan(val))
        indicators.append(
            Indicator(
                id=col,
                label=label,
                value=None if missing else round(float(val), 3),
                display="no data" if missing else _fmt(float(val), col),
                percentile=None if missing or pd.isna(pct) else round(float(pct), 1),
                source_id=src,
                vintage=vintage,
                confidence=conf if not missing else Confidence.LOW,
                missing=bool(missing),
            )
        )
        if not missing and pct is not None and not pd.isna(pct) and pct >= 90:
            drivers.append(f"{label}: {_fmt(float(val), col)} — P{pct:.0f} nationally.")

    if basis_note:
        gaps.append(basis_note)
    if dom["pollution"] is None:
        gaps.append(f"Only {dom['pollution_n']}/10 pollution indicators available (floor: 5).")
    if dom["vulnerability"] is None:
        gaps.append(f"Only {dom['vulnerability_n']}/6 vulnerability indicators available (floor: 4).")

    score = dom["cbi_percentile"]
    poc = row.get("pct_people_of_color")
    context = {
        "pollution_domain": None if dom["pollution"] is None else round(dom["pollution"], 1),
        "vulnerability_domain": None if dom["vulnerability"] is None else round(dom["vulnerability"], 1),
        "cbi_raw": None if dom["cbi"] is None else round(dom["cbi"], 1),
        "pct_people_of_color": None if poc is None or np.isnan(poc) else round(float(poc), 1),
        "tract_population": None if pd.isna(row.get("population")) else int(row.get("population")),
    }

    if score is not None and score >= 90:
        drivers.insert(
            0,
            f"Combined burden index is P{score:.0f} of all U.S. tracts "
            f"(pollution domain {context['pollution_domain']}, vulnerability domain "
            f"{context['vulnerability_domain']}).",
        )

    ps = PillarScore(
        pillar="burden",
        score=round(score, 1) if score is not None else None,
        band=band(score),
        indicators=indicators,
        drivers=drivers,
        data_gaps=gaps,
        components={
            k: v
            for k, v in {
                "pollution_domain": context["pollution_domain"],
                "vulnerability_domain": context["vulnerability_domain"],
            }.items()
            if v is not None
        },
    )
    return ps, context
