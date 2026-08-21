"""Spatial constraint screening and utility load-concentration context.

Both are site/market CONTEXT, not pillar scores. The tests below fix that
boundary and the refusal to read an outage as an all-clear.
"""

import pytest

from wattershed.scoring import hazards, utility


# --- flood -------------------------------------------------------------------

def test_sfha_intersection_is_flagged_high():
    f = hazards.classify_flood([{"FLD_ZONE": "AE", "SFHA_TF": "T", "ZONE_SUBTY": ""}])
    assert f.severity == "high" and f.triggered
    assert "Special Flood Hazard Area" in f.headline


def test_zone_x_outside_the_sfha_is_not_flagged():
    f = hazards.classify_flood([{"FLD_ZONE": "X", "SFHA_TF": "F",
                                 "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD"}])
    assert f.severity == "none" and not f.triggered


def test_five_hundred_year_area_is_an_advisory_not_a_clear():
    f = hazards.classify_flood([{"FLD_ZONE": "X", "SFHA_TF": "F",
                                 "ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"}])
    assert f.severity == "advisory"


def test_unmapped_coverage_is_an_advisory_not_a_clear():
    """Absence of a polygon is not evidence of absence of flood risk."""
    f = hazards.classify_flood([])
    assert f.severity == "advisory"
    assert "not evidence of absence" in f.detail


def test_unreachable_service_reads_as_unscreened_never_as_clear():
    f = hazards.classify_flood(None)
    assert f.severity == "unscreened" and not f.triggered


# --- wetland -----------------------------------------------------------------

def test_wetland_intersection_is_flagged_with_the_jurisdiction_caveat():
    f = hazards.classify_wetland([{"WETLAND_TYPE": "Freshwater Emergent", "ACRES": 3.4}])
    assert f.severity == "elevated"
    assert "404" in f.detail
    assert "NOT a jurisdictional determination" in f.detail
    assert f.value == pytest.approx(3.4)


def test_no_wetland_still_states_that_nwi_is_not_a_determination():
    f = hazards.classify_wetland([])
    assert f.severity == "none"
    assert "jurisdictional determination" in f.detail


def test_wetland_service_failure_is_unscreened():
    assert hazards.classify_wetland(None).severity == "unscreened"


def test_wetland_tolerates_missing_acreage():
    f = hazards.classify_wetland([{"WETLAND_TYPE": "Riverine"}])
    assert f.severity == "elevated" and f.value is None


# --- seismic -----------------------------------------------------------------

@pytest.mark.parametrize("sds,expected", [
    (0.10, "none"), (0.32, "none"), (0.33, "elevated"),
    (0.49, "elevated"), (0.50, "high"), (0.70, "high"),
])
def test_seismic_thresholds_are_inclusive_at_the_cut_points(sds, expected):
    assert hazards.classify_seismic(sds).severity == expected


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "0.5"])
def test_unusable_sds_is_unscreened_not_low(bad):
    assert hazards.classify_seismic(bad).severity == "unscreened"


# --- assembly ----------------------------------------------------------------

def test_screen_reports_the_worst_severity():
    s = hazards.classify([{"FLD_ZONE": "X", "SFHA_TF": "F"}],
                         [{"WETLAND_TYPE": "Riverine"}], 0.10)
    assert s.worst == "elevated"
    assert [f.hazard for f in s.triggered] == ["wetland"]


def test_unscreened_hazards_are_listed_separately_from_triggered():
    s = hazards.classify(None, [], 0.6)
    assert "flood" in [f.hazard for f in s.unscreened]
    assert "seismic" in [f.hazard for f in s.triggered]


def test_all_clear_screen_triggers_nothing():
    s = hazards.classify([{"FLD_ZONE": "X", "SFHA_TF": "F"}], [], 0.1)
    assert s.worst == "none" and not s.triggered


def test_screen_serializes_for_the_json_contract():
    d = hazards.classify([{"FLD_ZONE": "AE", "SFHA_TF": "T"}], [], 0.1).to_dict()
    assert d["worst_severity"] == "high"
    assert len(d["flags"]) == 3


def test_out_of_country_coordinates_are_unscreened_without_network(monkeypatch):
    def boom(*a, **k):  # any network call here would be a bug
        raise AssertionError("hazard screen must validate coordinates first")

    monkeypatch.setattr(hazards, "fetch_flood", boom)
    s = hazards.screen(48.8566, 2.3522)
    assert all(f.severity == "unscreened" for f in s.flags)


def test_hazards_are_not_a_pillar_score():
    """Severity is ordinal. Nothing here exposes a 0-100 value."""
    f = hazards.classify_seismic(0.7)
    assert isinstance(f.severity, str)
    assert not hasattr(f, "score")


# --- utility context ---------------------------------------------------------

def test_subregion_map_loads_and_covers_the_egrid_topology():
    m = utility.subregion_to_rto()
    assert len(m) >= 20
    assert all("rto" in v for v in m.values())


def test_operator_lookup_states_its_resolution_honestly():
    o = utility.operator_for_subregion("RFCE")
    assert o["rto"]
    assert "not a retail service territory" in o["resolution"]


def test_unknown_subregion_returns_blanks_rather_than_guessing():
    o = utility.operator_for_subregion("ZZZZ")
    assert o["rto"] == "" and o["nerc_area"] == ""


def test_load_concentration_scales_linearly_with_facility_count():
    # Compare implied load, which is unrounded; share_pct is reported to 2dp.
    a = utility.load_concentration(10, 100_000_000)["implied_load_mwh_yr"]
    b = utility.load_concentration(40, 100_000_000)["implied_load_mwh_yr"]
    assert b == pytest.approx(4 * a, rel=1e-9)


@pytest.mark.parametrize("count,gen", [(None, 1e8), (10, None), (10, 0), (10, -5)])
def test_concentration_is_none_not_zero_when_inputs_are_unusable(count, gen):
    """An unknown denominator is not the same as no concentration."""
    c = utility.load_concentration(count, gen)
    assert c["share_pct"] is None
    assert c["band"] == "insufficient data"


@pytest.mark.parametrize("count,expected", [
    (1, "low"),        # 0.42% of annual net generation
    (10, "notable"),   # 4.20%
    (30, "high"),      # 12.61%
])
def test_concentration_bands(count, expected):
    assert utility.load_concentration(count, 100_000_000)["band"] == expected


def test_concentration_discloses_its_assumed_campus_size():
    c = utility.load_concentration(10, 1e8)
    assert c["assumed_campus_mw"] == utility.ASSUMED_CAMPUS_MW
    assert "assumed" in c["basis"]


def test_context_refuses_to_imply_a_rate_forecast():
    """No rate data is ingested; the module must say so rather than imply one."""
    c = utility.context("RFCE", 20, 1e8)
    assert "not modelled" in c["not_modelled"].lower()
    assert "rate" in c["not_modelled"].lower()
    assert not any("price" in k for k in c)
    assert "volatility" not in str(c).lower()
