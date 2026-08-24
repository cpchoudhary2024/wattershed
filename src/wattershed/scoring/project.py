# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Project overlay: mechanical configuration → PUE / WUE / CUE and adjusted demand.

WHY THIS IS AN OVERLAY AND NOT A PILLAR EDIT
---------------------------------------------
The three pillars measure the LOCATION. Baseline water stress is the sub-basin's
withdrawal-to-supply balance; grid strain is the subregion's carbon intensity and
resource adequacy. Neither is a property of the building you put there.

Specifying air-cooled chillers does not make an over-allocated basin less
over-allocated, and it does not change the subregion's emission rate. What it
changes is the PROJECT: its water draw falls toward zero and its power draw
rises. So the adjustment belongs to the project profile, computed here and
displayed beside the location scores, rather than written back into them.

Three concrete reasons that separation is load-bearing:
  1. The location scores are the published, citable product; the siting-equity
     study and the blind validation both rest on them. A score that silently
     depends on a UI dropdown is not reproducible from a coordinate.
  2. Zeroing the water pillar for an air-cooled design would report "no water
     issue" for a campus in a basin that is genuinely over-allocated — exactly
     the finding a screening tool exists to surface, since neighbouring users
     still face that scarcity.
  3. Air cooling trades water for power. Reporting only the water improvement,
     while folding the power penalty into a regional index that already
     measures something else, hides the trade instead of quantifying it.

Metrics follow The Green Grid definitions:
    PUE = total facility energy / IT energy                  (dimensionless)
    WUE = site water consumed / IT energy                    (L/kWh)
    CUE = total facility CO2e / IT energy                    (kgCO2e/kWh)
CUE is computed from the eGRID subregion annual output rate, so it is a real
location-based figure, not a placeholder.

Everything here is pure: inputs in, numbers out, no I/O and no state.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import CoolingTech
from .normalize import clamp, is_number

LB_PER_KG = 2.204622
HOURS_PER_YEAR = 8760
L_PER_GAL = 3.785412


@dataclass(frozen=True)
class CoolingProfile:
    """Mechanical configuration factors. PUE/WUE from the LBNL 2024 U.S. Data
    Center Energy Usage Report (Shehabi et al.) hyperscale ranges."""

    key: str
    label: str
    pue: float                 # total facility energy / IT energy
    wue_l_per_kwh: float       # site water per kWh of IT energy
    confidence: str            # high | medium — how well-sourced the factors are
    note: str = ""


# Ordered as presented in the UI. HYBRID is retained because the curated
# registry and the demand model already use it; it is not offered in the
# selector, which mirrors the three configurations under evaluation.
COOLING_PROFILES: dict[str, CoolingProfile] = {
    "evaporative": CoolingProfile(
        "evaporative", "Evaporative cooling loop", 1.20, 1.80, "high",
        "Open or closed-circuit cooling towers. Lowest power, highest site water; "
        "the reference case for both LBNL ranges and most announced campuses.",
    ),
    "air": CoolingProfile(
        "air", "Closed-loop air chillers", 1.35, 0.05, "high",
        "Dry coolers / air-side economisation. Site water approaches zero; total "
        "facility power rises because heat rejection is done with fans and "
        "compressors instead of evaporation.",
    ),
    "dlc": CoolingProfile(
        "dlc", "Direct-liquid cooling", 1.15, 0.20, "medium",
        "Cold-plate or immersion capture at the rack. PUE is the best of the three "
        "because heat is captured at source. WUE is NOT a property of DLC itself — "
        "it depends entirely on the heat-rejection stage. The 0.20 L/kWh here "
        "assumes closed-loop dry rejection; DLC rejecting to evaporative towers "
        "behaves like the evaporative case on water. Flagged medium confidence: "
        "LBNL 2024 does not publish a separate DLC water range.",
    ),
    "hybrid": CoolingProfile(
        "hybrid", "Hybrid (water-side economiser + trim evaporative)", 1.25, 0.60, "high",
    ),
}

SELECTABLE = ("evaporative", "air", "dlc")

_ENUM_TO_KEY = {
    CoolingTech.EVAPORATIVE: "evaporative",
    CoolingTech.AIR: "air",
    CoolingTech.HYBRID: "hybrid",
}

BASELINE_KEY = "evaporative"


def profile_for(cooling) -> CoolingProfile:
    """Resolve a key, CoolingTech, or unknown input to a profile. Pure."""
    if isinstance(cooling, CoolingTech):
        return COOLING_PROFILES[_ENUM_TO_KEY.get(cooling, BASELINE_KEY)]
    key = str(cooling or "").strip().lower()
    return COOLING_PROFILES.get(key, COOLING_PROFILES[BASELINE_KEY])


# --- Green Grid metrics ------------------------------------------------------

def cue_kg_per_kwh(pue: float, grid_lb_co2e_per_mwh) -> float | None:
    """CUE = PUE x grid carbon intensity, in kgCO2e per kWh of IT energy.

    Location-based (eGRID annual average), matching the grid pillar. Market
    instruments do not enter: a PPA changes the reported figure, not the
    physical emissions of the electrons this site draws.
    """
    if not is_number(pue) or not is_number(grid_lb_co2e_per_mwh):
        return None
    kg_per_kwh = float(grid_lb_co2e_per_mwh) / LB_PER_KG / 1000.0
    return float(pue) * kg_per_kwh


def green_grid_metrics(cooling, grid_lb_co2e_per_mwh=None) -> dict:
    """PUE / WUE / CUE for a configuration. Pure."""
    p = profile_for(cooling)
    return {
        "cooling": p.key,
        "label": p.label,
        "pue": p.pue,
        "wue_l_per_kwh": p.wue_l_per_kwh,
        "cue_kg_per_kwh": cue_kg_per_kwh(p.pue, grid_lb_co2e_per_mwh),
        "confidence": p.confidence,
        "note": p.note,
    }


# --- configuration deltas ----------------------------------------------------

def water_demand_multiplier(cooling) -> float:
    """Project site-water draw relative to the evaporative baseline. Pure.

    Air cooling drives this to ~0.03 — the "nullified water penalty" of an
    air-cooled design, expressed where it is true: the project's demand, not
    the basin's stress.
    """
    base = COOLING_PROFILES[BASELINE_KEY].wue_l_per_kwh
    return round(profile_for(cooling).wue_l_per_kwh / base, 4) if base else 0.0


def grid_load_multiplier(cooling) -> float:
    """Project facility power relative to the evaporative baseline. Pure.

    This is the other half of the trade: 1.35/1.20 = 1.125, so an air-cooled
    campus draws ~12.5% more grid energy — and emits ~12.5% more — than the
    same IT load cooled evaporatively.
    """
    base = COOLING_PROFILES[BASELINE_KEY].pue
    return round(profile_for(cooling).pue / base, 4) if base else 1.0


def project_overlay(cooling, water_score=None, grid_score=None,
                    grid_lb_co2e_per_mwh=None, it_mw=None, utilization: float = 0.80) -> dict:
    """Configuration-adjusted project profile beside the unchanged location scores.

    `location_*` are echoed verbatim so a reader can see that the pillars did
    not move; `project_*` carry the configuration effect.
    """
    p = profile_for(cooling)
    w_mult, g_mult = water_demand_multiplier(cooling), grid_load_multiplier(cooling)
    out = {
        "metrics": green_grid_metrics(cooling, grid_lb_co2e_per_mwh),
        "water_demand_multiplier": w_mult,
        "grid_load_multiplier": g_mult,
        "location_water_score": clamp(water_score),
        "location_grid_score": clamp(grid_score),
        "basis": (
            "Location pillars are unchanged: cooling configuration alters this "
            "project's demand, not the basin's water stress or the subregion's "
            "emission rate."
        ),
        "tradeoff": (
            f"Relative to an evaporative baseline this configuration draws "
            f"{w_mult:.2f}x the site water and {g_mult:.3f}x the facility power."
        ),
    }
    if is_number(it_mw) and float(it_mw) > 0:
        it_energy_mwh = float(it_mw) * float(utilization) * HOURS_PER_YEAR
        it_kwh = it_energy_mwh * 1000.0
        facility_mwh = it_energy_mwh * p.pue
        water_l = it_kwh * p.wue_l_per_kwh
        out["annual"] = {
            "it_mw": float(it_mw),
            "utilization": float(utilization),
            "it_energy_mwh_yr": round(it_energy_mwh),
            "facility_energy_mwh_yr": round(facility_mwh),
            "site_water_mgal_yr": round(water_l / L_PER_GAL / 1e6, 2),
            "co2e_tonnes_yr": (
                round(facility_mwh * float(grid_lb_co2e_per_mwh) / LB_PER_KG / 1000.0)
                if is_number(grid_lb_co2e_per_mwh) else None
            ),
        }
    return out


def comparison_table(grid_lb_co2e_per_mwh=None, it_mw=None) -> list[dict]:
    """All selectable configurations, for the side-by-side matrix. Pure."""
    rows = []
    for key in SELECTABLE:
        ov = project_overlay(key, grid_lb_co2e_per_mwh=grid_lb_co2e_per_mwh, it_mw=it_mw)
        row = dict(ov["metrics"])
        row["water_demand_multiplier"] = ov["water_demand_multiplier"]
        row["grid_load_multiplier"] = ov["grid_load_multiplier"]
        if "annual" in ov:
            row["annual"] = ov["annual"]
        rows.append(row)
    return rows


__all__ = [
    "BASELINE_KEY",
    "COOLING_PROFILES",
    "SELECTABLE",
    "CoolingProfile",
    "comparison_table",
    "cue_kg_per_kwh",
    "green_grid_metrics",
    "grid_load_multiplier",
    "profile_for",
    "project_overlay",
    "water_demand_multiplier",
]
