"""Mathematical guarantees for the 0–100 normalization layer.

The contract under test: no input — null, NaN, infinite, out-of-range,
wrong-typed, or non-U.S. — may produce a score that escapes [0, 100], a band
that misreads a data gap as a real reading, an exception that aborts a
screening, or a value that cannot be serialized to valid JSON.

That last one is the one that actually freezes the app: `float('nan')`
serializes as the bare token `NaN`, which `JSON.parse` rejects, so a single
NaN in a pillar score takes down the dashboard widget that reads the file.
"""

import json
import math

import pytest

from wattershed.scoring.normalize import (
    BAND_INSUFFICIENT,
    band,
    blend,
    clamp,
    is_number,
    mean_or_none,
    percentile_band,
    percentile_of,
    to_score,
    validate_coordinates,
)

# Every value that must never be treated as a number.
NON_NUMBERS = [
    None,
    float("nan"),
    float("inf"),
    float("-inf"),
    "50",
    "",
    [],
    {},
    True,   # bool is an int subclass — must not score as 1.0
    False,
]


# --- is_number ---------------------------------------------------------------

@pytest.mark.parametrize("v", NON_NUMBERS)
def test_is_number_rejects_every_non_number(v):
    assert is_number(v) is False


@pytest.mark.parametrize("v", [0, 100, -5, 3.14, 1e6])
def test_is_number_accepts_real_finite_numbers(v):
    assert is_number(v) is True


# --- clamp / to_score --------------------------------------------------------

@pytest.mark.parametrize("v", NON_NUMBERS)
def test_clamp_returns_none_for_unusable_input_instead_of_raising(v):
    assert clamp(v) is None


@pytest.mark.parametrize(
    "raw,expected",
    [(-1, 0.0), (-1e9, 0.0), (0, 0.0), (50, 50.0), (100, 100.0), (101, 100.0), (1e9, 100.0)],
)
def test_clamp_constrains_out_of_bounds_metrics(raw, expected):
    assert clamp(raw) == expected


def test_to_score_never_escapes_the_contract():
    for raw in NON_NUMBERS + [-500, -0.001, 100.001, 12345]:
        s = to_score(raw)
        assert s is None or (isinstance(s, float) and 0.0 <= s <= 100.0)


# --- band --------------------------------------------------------------------

@pytest.mark.parametrize("v", NON_NUMBERS)
def test_band_reads_unusable_input_as_insufficient_not_low(v):
    """A NaN score compares False against every threshold, so a naive chain of
    `>=` labels it 'low' — the most reassuring band available. It must not."""
    assert band(v) == BAND_INSUFFICIENT


@pytest.mark.parametrize(
    "score,expected",
    [(100, "severe"), (75, "severe"), (74.9, "high"), (55, "high"),
     (54.9, "moderate"), (35, "moderate"), (34.9, "low"), (0, "low")],
)
def test_band_thresholds_are_inclusive_at_the_cut_points(score, expected):
    assert band(score) == expected


def test_band_clamps_before_classifying():
    assert band(150) == "severe"
    assert band(-50) == "low"


@pytest.mark.parametrize(
    "score,expected",
    [(95, "severe"), (90, "severe"), (89.9, "high"), (75, "high"),
     (74.9, "moderate"), (50, "moderate"), (49.9, "low")],
)
def test_percentile_band_uses_its_own_deliberately_different_ladder(score, expected):
    """Burden's score IS a percentile, so 'severe' means top decile — not the
    same cut points as a constructed index. The divergence is intentional."""
    assert percentile_band(score) == expected


def test_the_two_ladders_actually_differ():
    assert band(80) != percentile_band(80)


# --- blend -------------------------------------------------------------------

def test_blend_drops_null_and_nan_components_and_renormalizes():
    # 50 at weight .5 survives; the NaN at weight .5 is dropped, not propagated
    assert blend({"a": 50, "b": float("nan")}, {"a": 0.5, "b": 0.5}) == 50.0
    assert blend({"a": 50, "b": None}, {"a": 0.5, "b": 0.5}) == 50.0


def test_blend_matches_a_hand_computed_weighted_mean():
    got = blend({"a": 80, "b": 30}, {"a": 0.6, "b": 0.4})
    assert got == pytest.approx(0.6 * 80 + 0.4 * 30)


def test_blend_renormalizes_over_survivors_not_declared_weights():
    # only 'b' survives, so the result is b itself — not b * 0.4
    assert blend({"a": None, "b": 30}, {"a": 0.6, "b": 0.4}) == 30.0


def test_blend_returns_none_when_nothing_is_usable():
    assert blend({}, {"a": 1.0}) is None
    assert blend({"a": None, "b": float("nan")}, {"a": 0.5, "b": 0.5}) is None


def test_blend_ignores_components_with_no_declared_weight():
    """An unweighted component used to raise KeyError mid-screening."""
    assert blend({"a": 50, "rogue": 99}, {"a": 1.0}) == 50.0


@pytest.mark.parametrize("w", [0, -1, float("nan"), None, "0.5"])
def test_blend_ignores_invalid_weights(w):
    assert blend({"a": 50, "b": 90}, {"a": 1.0, "b": w}) == 50.0


def test_blend_survives_a_zero_total_weight_without_dividing_by_zero():
    assert blend({"a": 50}, {"a": 0.0}) is None


def test_blend_clamps_out_of_range_components_before_weighting():
    """One corrupt input must not drag the blend outside 0-100."""
    assert blend({"a": 500, "b": 50}, {"a": 0.5, "b": 0.5}) == 75.0
    assert blend({"a": -500, "b": 50}, {"a": 0.5, "b": 0.5}) == 25.0


def test_blend_min_weight_share_refuses_a_score_resting_on_a_minor_signal():
    # only the 0.2-weight component survives -> 20% of declared weight
    assert blend({"c": 90}, {"a": 0.5, "b": 0.3, "c": 0.2}, min_weight_share=0.5) is None
    assert blend({"c": 90}, {"a": 0.5, "b": 0.3, "c": 0.2}) == 90.0


def test_blend_output_is_always_in_range_over_a_grid_of_hostile_inputs():
    hostile = [None, float("nan"), float("inf"), float("-inf"), -1e6, -1, 0, 50, 100, 101, 1e6]
    for a in hostile:
        for b in hostile:
            out = blend({"a": a, "b": b}, {"a": 0.6, "b": 0.4})
            assert out is None or (0.0 <= out <= 100.0 and math.isfinite(out))


def test_blend_output_is_always_valid_json():
    """The failure that freezes the dashboard: NaN is not valid JSON."""
    for a in [None, float("nan"), float("inf"), 50, 1e9]:
        payload = json.dumps({"score": blend({"a": a}, {"a": 1.0})})
        assert "NaN" not in payload and "Infinity" not in payload
        json.loads(payload)  # must round-trip


def test_blend_is_pure_and_does_not_mutate_its_inputs():
    comps = {"a": 50, "b": None}
    weights = {"a": 0.5, "b": 0.5}
    before = (dict(comps), dict(weights))
    assert blend(comps, weights) == blend(comps, weights)  # deterministic
    assert (comps, weights) == before                      # unmutated


# --- coverage floors & percentiles ------------------------------------------

def test_mean_or_none_enforces_a_coverage_floor():
    assert mean_or_none([10, 20, 30], minimum=3) == pytest.approx(20.0)
    assert mean_or_none([10, 20], minimum=3) is None


def test_mean_or_none_ignores_unusable_values_when_counting_coverage():
    assert mean_or_none([10, None, float("nan"), 30], minimum=3) is None
    assert mean_or_none([10, None, 30], minimum=2) == pytest.approx(20.0)


def test_percentile_of_splits_ties_and_never_exceeds_100():
    assert percentile_of(10, [10, 10, 10]) == 50.0      # all tied -> mid-rank
    assert percentile_of(30, [10, 20, 30]) == pytest.approx(83.3, abs=0.1)
    assert percentile_of(5, [10, 20, 30]) == 0.0


def test_percentile_of_handles_empty_and_unusable_populations():
    assert percentile_of(10, []) is None
    assert percentile_of(10, [None, float("nan")]) is None
    assert percentile_of(None, [1, 2, 3]) is None


# --- non-U.S. and malformed coordinates -------------------------------------

@pytest.mark.parametrize(
    "lat,lon,label",
    [
        (48.8566, 2.3522, "Paris"),
        (-33.8688, 151.2093, "Sydney"),
        (51.5074, -0.1278, "London"),
        (0.0, 0.0, "Null Island"),
        (19.4326, -99.1332, "Mexico City"),
    ],
)
def test_non_us_coordinates_are_rejected_with_a_reason_not_an_exception(lat, lon, label):
    ok, reason = validate_coordinates(lat, lon)
    assert ok is False
    assert reason, f"{label} rejected without an explanation"


@pytest.mark.parametrize(
    "lat,lon",
    [(35.06, -90.07), (61.2181, -149.9003), (21.3069, -157.8583), (18.4655, -66.1057)],
)
def test_us_coordinates_including_alaska_hawaii_and_puerto_rico_are_accepted(lat, lon):
    ok, reason = validate_coordinates(lat, lon)
    assert ok is True and reason == ""


def test_aleutian_islands_across_the_antimeridian_are_accepted():
    assert validate_coordinates(52.9, 173.2)[0] is True


@pytest.mark.parametrize(
    "lat,lon",
    [(91, -90), (-91, -90), (35, 181), (35, -181), (float("nan"), -90),
     (35, float("inf")), (None, None), ("35", "-90"), (True, False)],
)
def test_impossible_coordinates_are_rejected_without_raising(lat, lon):
    ok, reason = validate_coordinates(lat, lon)
    assert ok is False and reason


def test_validate_coordinates_never_raises_on_arbitrary_input():
    for bad in [object(), b"x", [], {}, complex(1, 2)]:
        assert validate_coordinates(bad, bad)[0] is False


# --- the pillars actually use the shared layer -------------------------------

def test_pillar_scorers_degrade_to_insufficient_data_rather_than_crashing():
    """Empty upstream data must yield a null score and an honest band, not an
    exception that aborts the screening."""
    from wattershed.scoring.grid import score_grid
    from wattershed.scoring.water import score_water

    w = score_water(bws=None, current={}, history={}, demand_context=None)
    assert w.score is None or 0 <= w.score <= 100
    g = score_grid(egrid_stats=None, nerc_risk=None, load_share_pct=None)
    assert g.score is None and g.band == BAND_INSUFFICIENT


def test_grid_scorer_survives_a_malformed_egrid_row():
    """A missing percentile used to raise KeyError and abort the run."""
    from wattershed.scoring.grid import score_grid

    g = score_grid(egrid_stats={"name": "x", "subrgn": "X"}, nerc_risk=None, load_share_pct=None)
    assert g.score is None and g.band == BAND_INSUFFICIENT


def test_unrecognized_drought_category_is_not_scored_as_no_drought():
    """An unknown USDM category must become a data gap, not the best case."""
    from wattershed.scoring.water import score_water

    w = score_water(bws=None, current={"category": 99}, history={}, demand_context=None)
    assert "current" not in w.components
    assert any("Unrecognized USDM" in g for g in w.data_gaps)


def test_all_three_pillars_share_one_band_definition():
    from wattershed.scoring.burden import band as burden_band
    from wattershed.scoring.grid import band as grid_band
    from wattershed.scoring.water import band as water_band

    assert water_band is grid_band                      # identical ladder
    assert burden_band is percentile_band               # deliberately different
