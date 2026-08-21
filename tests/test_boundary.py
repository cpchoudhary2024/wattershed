"""Tract-boundary proximity: pure geometry, synthetic polygons, no network.

The measurement must be right, and — more important for a screening tool —
it must never report a false all-clear. An undetermined check is an unknown,
not "not near a boundary".
"""

import pytest

from wattershed.spatial.boundary import (
    BOUNDARY_WARNING,
    DEFAULT_BUFFER_M,
    assess,
    nearest_adjacent_tract_m,
    query_envelope,
)

LAT, LON = 35.0000, -90.0000
M_PER_DEG_LAT = 111132.0


def _deg_north(metres: float) -> float:
    return metres / M_PER_DEG_LAT


def _square(geoid: str, south: float, north: float, west: float, east: float) -> dict:
    """A GeoJSON tract-like feature spanning the given lat/lon box."""
    return {
        "properties": {"GEOID": geoid},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        },
    }


# Half-width of the synthetic tracts, in degrees of longitude (~450 m).
# Deliberately narrow: these squares have only four corners, so their southern
# edge is a straight chord rather than a true parallel. Across 0.1 deg that
# chord sags ~1.1 m closer to the point than the parallel it represents, which
# is real geometry, not a defect — but it would put a metre of slop into every
# assertion below. Real TIGER polygons carry densified vertices and do not have
# this artifact. Keeping the span short makes the sag ~0.01 m: negligible.
_HALF_LON = 0.005


def _neighbour_at(metres_north: float, geoid: str = "22222222222") -> dict:
    """A neighbouring tract whose southern edge sits `metres_north` above the point."""
    edge = LAT + _deg_north(metres_north)
    return _square(geoid, edge, edge + _deg_north(2000), LON - _HALF_LON, LON + _HALF_LON)


HOME = "11111111111"


# --- measurement -------------------------------------------------------------

@pytest.mark.parametrize("metres", [10, 50, 100, 149, 150, 300, 1000])
def test_distance_to_the_neighbouring_tract_edge_is_measured_in_metres(metres):
    got = nearest_adjacent_tract_m(LAT, LON, HOME, [_neighbour_at(metres)])
    assert got["distance_m"] == pytest.approx(metres, rel=0.02)
    assert got["nearest_geoid"] == "22222222222"


def test_the_home_tract_is_never_its_own_neighbour():
    """A polygon containing the point must not be measured against itself —
    otherwise every point reads as 0 m from a boundary."""
    home_poly = _square(HOME, LAT - 0.01, LAT + 0.01, LON - _HALF_LON, LON + _HALF_LON)
    got = nearest_adjacent_tract_m(LAT, LON, HOME, [home_poly])
    assert got["distance_m"] is None
    assert got["neighbors_considered"] == 0


def test_the_nearest_of_several_neighbours_wins():
    feats = [_neighbour_at(800, "33333333333"), _neighbour_at(90, "22222222222"),
             _neighbour_at(400, "44444444444")]
    got = nearest_adjacent_tract_m(LAT, LON, HOME, feats)
    assert got["nearest_geoid"] == "22222222222"
    assert got["distance_m"] == pytest.approx(90, rel=0.02)
    assert got["neighbors_considered"] == 3


def test_multipolygon_geometry_is_handled():
    n = _neighbour_at(70)
    n["geometry"] = {"type": "MultiPolygon", "coordinates": [n["geometry"]["coordinates"]]}
    assert nearest_adjacent_tract_m(LAT, LON, HOME, [n])["distance_m"] == pytest.approx(70, rel=0.02)


# --- the flag ----------------------------------------------------------------

def test_flag_fires_inside_the_buffer_and_carries_the_warning():
    got = assess(LAT, LON, HOME, [_neighbour_at(80)], buffer_m=DEFAULT_BUFFER_M)
    assert got["near_boundary"] is True
    assert got["warning"] == BOUNDARY_WARNING


def test_flag_is_silent_outside_the_buffer():
    got = assess(LAT, LON, HOME, [_neighbour_at(400)], buffer_m=DEFAULT_BUFFER_M)
    assert got["near_boundary"] is False
    assert got["warning"] == ""


def test_the_buffer_boundary_is_inclusive():
    assert assess(LAT, LON, HOME, [_neighbour_at(150)], buffer_m=150)["near_boundary"] is True


def test_buffer_is_configurable_without_touching_the_measurement():
    feats = [_neighbour_at(200)]
    assert assess(LAT, LON, HOME, feats, buffer_m=150)["near_boundary"] is False
    assert assess(LAT, LON, HOME, feats, buffer_m=250)["near_boundary"] is True


# --- refusing to give a false all-clear --------------------------------------

def test_no_neighbours_is_reported_as_unknown_not_as_safely_inland():
    """A coastline or the edge of tract coverage yields no neighbour. That is
    an unmeasured distance, and it must say so rather than imply safety."""
    got = assess(LAT, LON, HOME, [], buffer_m=DEFAULT_BUFFER_M)
    assert got["distance_m"] is None
    assert got["near_boundary"] is False
    assert got["note"], "an undetermined check must explain itself"


def test_malformed_geometry_is_skipped_without_aborting_the_screening():
    bad = [
        {"properties": {"GEOID": "99999999999"}, "geometry": None},
        {"properties": {"GEOID": "99999999998"}, "geometry": {"type": "Polygon", "coordinates": []}},
        {"properties": {"GEOID": "99999999997"}, "geometry": {"type": "Nonsense", "coordinates": [1]}},
        {"properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]}},
        {},
    ]
    got = nearest_adjacent_tract_m(LAT, LON, HOME, bad + [_neighbour_at(60)])
    assert got["distance_m"] == pytest.approx(60, rel=0.02)


@pytest.mark.parametrize(
    "lat,lon", [(48.8566, 2.3522), (0.0, 0.0), (91.0, -90.0), (float("nan"), -90.0), (None, None)]
)
def test_non_us_or_impossible_coordinates_return_a_reason_not_an_exception(lat, lon):
    got = nearest_adjacent_tract_m(lat, lon, HOME, [_neighbour_at(50)])
    assert got["distance_m"] is None
    assert got["note"]


# --- purity ------------------------------------------------------------------

def test_measurement_is_deterministic_and_does_not_mutate_its_inputs():
    feats = [_neighbour_at(120), _neighbour_at(300, "33333333333")]
    snapshot = repr(feats)
    a = nearest_adjacent_tract_m(LAT, LON, HOME, feats)
    b = nearest_adjacent_tract_m(LAT, LON, HOME, feats)
    assert a == b
    assert repr(feats) == snapshot, "input features were mutated"


def test_assess_always_returns_the_same_keys():
    """Callers must never have to branch on result shape."""
    keys = {"distance_m", "nearest_geoid", "neighbors_considered", "note",
            "buffer_m", "near_boundary", "warning"}
    for feats in ([], [_neighbour_at(50)], [_neighbour_at(5000)]):
        assert set(assess(LAT, LON, HOME, feats).keys()) == keys


# --- query envelope ----------------------------------------------------------

def test_query_envelope_is_centred_and_scales_with_the_requested_width():
    env = query_envelope(LAT, LON, 1000)
    assert env["xmin"] < LON < env["xmax"]
    assert env["ymin"] < LAT < env["ymax"]
    assert (env["ymax"] - LAT) * M_PER_DEG_LAT == pytest.approx(1000, rel=0.02)


def test_query_envelope_stays_within_valid_latitudes_near_the_poles():
    env = query_envelope(89.999, 0.0, 100000)
    assert -90.0 <= env["ymin"] <= env["ymax"] <= 90.0


def test_envelope_longitude_span_widens_with_latitude():
    """A degree of longitude shrinks toward the poles, so a fixed metre buffer
    must span more degrees in Alaska than in Texas."""
    def span(lat: float) -> float:
        env = query_envelope(lat, -100.0, 1000)
        return env["xmax"] - env["xmin"]

    assert span(64.0) > span(30.0)


@pytest.mark.parametrize(
    "lat,lon", [(25.8, -80.2), (40.0, -100.0), (64.0, -150.0)]  # Miami, Kansas, interior Alaska
)
def test_measured_distance_is_consistent_across_latitudes(lat, lon):
    """The same 100 m offset must measure 100 m in Florida and in Alaska —
    the projection is recentred on the point, so latitude cannot bias it."""
    edge = lat + 100.0 / M_PER_DEG_LAT
    n = _square("22222222222", edge, edge + 0.02, lon - _HALF_LON, lon + _HALF_LON)
    got = nearest_adjacent_tract_m(lat, lon, HOME, [n])
    assert got["distance_m"] == pytest.approx(100, rel=0.03), lat
