"""Guardrails for the siting-equity study: the DC dataset stays valid, and the
statistics helpers are correct on known inputs."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from wattershed.pipelines.siting_equity import _ks, _mannwhitney, _weighted_quantile

STUDY = Path(__file__).resolve().parents[1] / "data" / "study"
DC = STUDY / "datacenters_osm.csv"
CENSUS = STUDY / "datacenters_census.csv"


def test_datacenter_set_valid():
    rows = list(csv.DictReader(DC.open()))
    assert len(rows) > 500, "expected a national-scale sample"
    coords = set()
    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        assert 24 < lat < 50, r["osm_id"]
        assert -125 < lon < -66, r["osm_id"]
        coords.add((round(lat, 3), round(lon, 3)))
    assert len(coords) == len(rows), "coordinates should be deduplicated"


def test_census_has_exact_tracts():
    rows = list(csv.DictReader(CENSUS.open()))
    assert len(rows) > 1000
    with_tract = [r for r in rows if (r.get("tract_geoid") or "").strip()]
    # the study relies on a high exact-assignment rate
    assert len(with_tract) / len(rows) > 0.9
    for r in with_tract[:50]:
        assert len(r["tract_geoid"]) == 11 and r["county_fips"] == r["tract_geoid"][:5]


def test_mannwhitney_and_effect():
    # a strictly greater than b: significant, positive rank-biserial
    p, rbc = _mannwhitney([10, 11, 12, 13, 14, 15], [1, 2, 3, 4, 5, 6])
    assert p < 0.01 and rbc > 0.9
    # identical: ns, ~zero effect
    p2, rbc2 = _mannwhitney([5, 6, 7], [5, 6, 7])
    assert p2 > 0.4 and abs(rbc2) < 1e-9


def test_ks_bounds():
    assert _ks(np.array([1, 2, 3]), np.array([1, 2, 3])) == 0.0
    assert _ks(np.array([0, 0, 0]), np.array([1, 1, 1])) == 1.0


def test_weighted_quantile():
    # equal weights -> ordinary median
    assert abs(_weighted_quantile([1, 2, 3, 4, 5], [1, 1, 1, 1, 1], 0.5) - 3) < 1e-9
