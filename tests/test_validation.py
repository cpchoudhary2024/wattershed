"""Guardrails for the validation study: the labeled set stays balanced and
honestly labeled, and the statistics helpers are correct on known inputs."""

from __future__ import annotations

import csv
from pathlib import Path

from wattershed.pipelines.validate import _auc, _mannwhitney_u

LABELED = Path(__file__).resolve().parents[1] / "data" / "validation" / "sites_labeled.csv"


def test_labeled_set_is_valid():
    rows = list(csv.DictReader(LABELED.open()))
    assert len(rows) >= 40
    labels = {r["label"] for r in rows}
    assert labels == {"contested", "quiet"}
    for r in rows:
        assert 17 < float(r["lat"]) < 72, r["name"]
        assert -180 < float(r["lon"]) < -60, r["name"]
        assert r["source"], f"{r['name']} missing an outcome source"
    # coordinates must be unique — no two sites collapsing to one point
    coords = [(r["lat"], r["lon"]) for r in rows]
    assert len(coords) == len(set(coords)), "duplicate coordinates in labeled set"


def test_auc_perfect_separation():
    # _auc(scores, labels): positives outscore negatives -> AUC 1.0
    assert _auc([9, 8, 7, 3, 2, 1], [1, 1, 1, 0, 0, 0]) == 1.0
    # reversed -> 0.0
    assert _auc([3, 2, 1, 9, 8, 7], [1, 1, 1, 0, 0, 0]) == 0.0
    # identical -> 0.5 (all ties)
    assert _auc([5, 5, 5, 5], [1, 1, 0, 0]) == 0.5


def test_mannwhitney_direction():
    # a clearly greater than b -> small one-sided p
    _, p = _mannwhitney_u([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
    assert p < 0.05
    # no separation -> large p
    _, p2 = _mannwhitney_u([5, 6, 7], [5, 6, 7])
    assert p2 > 0.4
