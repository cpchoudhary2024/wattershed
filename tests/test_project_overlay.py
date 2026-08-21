"""Mechanical configuration overlay: Green Grid metrics and demand deltas.

The load-bearing property under test is that cooling configuration changes the
PROJECT and never the LOCATION. Water stress is a sub-basin property and grid
strain a subregion property; neither is altered by the chiller specification.
"""

import pytest

from wattershed.models import CoolingTech
from wattershed.scoring import project
from wattershed.scoring.project import (
    COOLING_PROFILES,
    SELECTABLE,
    comparison_table,
    cue_kg_per_kwh,
    green_grid_metrics,
    grid_load_multiplier,
    profile_for,
    project_overlay,
    water_demand_multiplier,
)


# --- resolution --------------------------------------------------------------

@pytest.mark.parametrize("key", SELECTABLE)
def test_every_selectable_configuration_resolves(key):
    assert profile_for(key).key == key


def test_cooling_enum_resolves_to_the_same_profiles():
    assert profile_for(CoolingTech.AIR).key == "air"
    assert profile_for(CoolingTech.EVAPORATIVE).key == "evaporative"


@pytest.mark.parametrize("bad", [None, "", "nonsense", 42, CoolingTech.UNKNOWN])
def test_unknown_configuration_falls_back_to_the_baseline(bad):
    assert profile_for(bad).key == project.BASELINE_KEY


# --- the trade, in both directions ------------------------------------------

def test_air_cooling_nullifies_project_water_demand():
    """The 'nullified water penalty', expressed where it is true."""
    assert water_demand_multiplier("air") < 0.05
    assert COOLING_PROFILES["air"].wue_l_per_kwh < 0.1


def test_air_cooling_scales_project_power_up_proportionately():
    """PUE 1.35 / 1.20 = 1.125 — the other half of the trade."""
    assert grid_load_multiplier("air") == pytest.approx(1.35 / 1.20, rel=1e-6)
    assert grid_load_multiplier("air") > 1.0


def test_the_baseline_is_unity_on_both_axes():
    assert water_demand_multiplier("evaporative") == 1.0
    assert grid_load_multiplier("evaporative") == 1.0


def test_direct_liquid_cooling_improves_power_and_water_together():
    assert grid_load_multiplier("dlc") < 1.0
    assert water_demand_multiplier("dlc") < 1.0


def test_water_and_power_multipliers_move_in_opposition_for_air():
    """Trading water for power must be visible as a trade, not a free win."""
    assert water_demand_multiplier("air") < 1.0 < grid_load_multiplier("air")


# --- Green Grid metrics ------------------------------------------------------

def test_cue_is_pue_times_grid_intensity():
    # 900 lb/MWh -> 900/2.204622/1000 = 0.40823 kg/kWh; x PUE 1.20
    assert cue_kg_per_kwh(1.20, 900.0) == pytest.approx(1.20 * 900 / 2.204622 / 1000, rel=1e-9)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "900"])
def test_cue_is_none_when_grid_intensity_is_unusable(bad):
    assert cue_kg_per_kwh(1.20, bad) is None


def test_cue_rises_with_pue_on_the_same_grid():
    assert cue_kg_per_kwh(1.35, 900.0) > cue_kg_per_kwh(1.20, 900.0)


def test_cue_is_zero_on_a_zero_carbon_grid():
    assert cue_kg_per_kwh(1.20, 0.0) == 0.0


def test_metrics_expose_all_three_green_grid_values():
    m = green_grid_metrics("evaporative", 900.0)
    assert {"pue", "wue_l_per_kwh", "cue_kg_per_kwh"} <= set(m)
    assert m["pue"] > 1.0


def test_metrics_degrade_without_a_grid_rate():
    m = green_grid_metrics("air")
    assert m["cue_kg_per_kwh"] is None
    assert m["pue"] and m["wue_l_per_kwh"] is not None


def test_dlc_water_factor_is_flagged_medium_confidence():
    """WUE is a property of the heat-rejection stage, not of DLC itself."""
    assert COOLING_PROFILES["dlc"].confidence == "medium"
    assert "rejection" in COOLING_PROFILES["dlc"].note


# --- location pillars are never mutated -------------------------------------

@pytest.mark.parametrize("cooling", SELECTABLE)
def test_overlay_echoes_location_scores_unchanged(cooling):
    ov = project_overlay(cooling, water_score=82.0, grid_score=61.0)
    assert ov["location_water_score"] == 82.0
    assert ov["location_grid_score"] == 61.0


def test_air_cooling_does_not_zero_the_location_water_score():
    """A basin does not become less over-allocated because of a chiller spec."""
    ov = project_overlay("air", water_score=88.0, grid_score=50.0)
    assert ov["location_water_score"] == 88.0
    assert ov["water_demand_multiplier"] < 0.05   # the project's draw does fall


def test_overlay_states_the_separation_and_the_tradeoff():
    ov = project_overlay("air", water_score=88.0, grid_score=50.0)
    assert "unchanged" in ov["basis"]
    assert "site water" in ov["tradeoff"] and "facility power" in ov["tradeoff"]


def _imported_modules(path) -> set[str]:
    """Module names a file actually imports, via AST — not substring matching,
    which trips over ordinary prose like "projected shortfall"."""
    import ast

    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[-1] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[-1])
            names.update(a.name for a in node.names)
    return names


@pytest.mark.parametrize("mod", ["water", "grid", "burden", "tiers"])
def test_no_scoring_pillar_imports_the_project_overlay(mod):
    """A pillar that depended on a UI dropdown would not be reproducible from
    a coordinate, and would break the study and validation artifacts."""
    from pathlib import Path

    import wattershed.scoring as pkg

    imported = _imported_modules(Path(pkg.__file__).parent / f"{mod}.py")
    assert "project" not in imported, f"scoring.{mod} imports the overlay"
    assert "hazards" not in imported, f"scoring.{mod} imports the hazard screen"
    assert "utility" not in imported, f"scoring.{mod} imports the utility layer"


# --- annual figures ----------------------------------------------------------

def test_annual_block_appears_only_with_a_capacity():
    assert "annual" not in project_overlay("air")
    assert "annual" in project_overlay("air", it_mw=300)


def test_annual_water_falls_and_carbon_rises_for_air_cooling():
    ev = project_overlay("evaporative", grid_lb_co2e_per_mwh=900.0, it_mw=300)["annual"]
    air = project_overlay("air", grid_lb_co2e_per_mwh=900.0, it_mw=300)["annual"]
    assert air["site_water_mgal_yr"] < ev["site_water_mgal_yr"] * 0.05
    assert air["co2e_tonnes_yr"] > ev["co2e_tonnes_yr"]
    assert air["facility_energy_mwh_yr"] > ev["facility_energy_mwh_yr"]


@pytest.mark.parametrize("mw", [0, -5, None, float("nan")])
def test_invalid_capacity_yields_no_annual_block_rather_than_garbage(mw):
    assert "annual" not in project_overlay("air", it_mw=mw)


def test_comparison_table_covers_every_selectable_configuration():
    rows = comparison_table(grid_lb_co2e_per_mwh=900.0, it_mw=300)
    assert [r["cooling"] for r in rows] == list(SELECTABLE)
    assert all(r["cue_kg_per_kwh"] is not None for r in rows)


def test_overlay_is_pure_and_deterministic():
    a = project_overlay("dlc", water_score=50, grid_score=50, grid_lb_co2e_per_mwh=900, it_mw=100)
    b = project_overlay("dlc", water_score=50, grid_score=50, grid_lb_co2e_per_mwh=900, it_mw=100)
    assert a == b
