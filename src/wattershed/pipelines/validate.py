# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Validation pipeline: does Wattershed's screening actually track where real
data-center siting fights happen?

Design is pre-registered in data/validation/RUBRIC.md. Scoring is blind: each
site is screened from coordinates only (no MW, no cooling, so no demand
escalators — pure location signal), and the label is never passed to the
scorer. Statistics: Mann-Whitney U (one-sided) per pillar, AUC of each pillar
and of the ordinal tier as a classifier of "contested", and tier hit-rates.

Outputs data/validation/results.csv and data/validation/report.json.
Run: python -m wattershed.pipelines.validate
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ..models import SiteInput
from .screen import screen_site

DIR = Path(__file__).resolve().parents[1].parent.parent / "data" / "validation"
LABELED = DIR / "sites_labeled.csv"
TIER_RANK = {"Low": 0, "Moderate": 1, "Elevated": 2, "High": 3}


def _load() -> list[dict]:
    with LABELED.open() as f:
        return list(csv.DictReader(f))


def _mannwhitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """U statistic and one-sided p (a > b) via normal approx with tie
    correction. Kept dependency-free and transparent."""
    import math

    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    # average ranks with ties
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    r_a = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    na, nb = len(a), len(b)
    u_a = r_a - na * (na + 1) / 2
    mu = na * nb / 2
    # tie-corrected sigma
    n = na + nb
    tie_term = 0.0
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        t = j - i + 1
        tie_term += t**3 - t
        i = j + 1
    sigma = math.sqrt(na * nb / 12 * ((n + 1) - tie_term / (n * (n - 1)))) if n > 1 else 0.0
    if sigma == 0:
        return u_a, 1.0
    z = (u_a - mu) / sigma
    p_one_sided = 0.5 * math.erfc(z / math.sqrt(2))  # P(U_a >= observed): a > b
    return u_a, p_one_sided


def _auc(scores: list[float], labels: list[int]) -> float:
    """AUC = P(score of positive > score of negative), ties count 0.5.
    Equivalent to the normalized Mann-Whitney U statistic."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for ng in neg:
            wins += 1.0 if p > ng else 0.5 if p == ng else 0.0
    return wins / (len(pos) * len(neg))


def run() -> dict:
    sites = _load()
    rows = []
    for s in sites:
        site = SiteInput(
            name=s["name"],
            lat=float(s["lat"]),
            lon=float(s["lon"]),
            operator=s.get("operator", ""),
            coord_precision="locality",
        )
        scr = screen_site(site)  # blind: label never passed in
        rows.append(
            {
                "name": s["name"],
                "location": s["location"],
                "label": s["label"],
                "water": scr.water.score,
                "grid": scr.grid.score,
                "burden": scr.burden.score,
                "tier": scr.tier.value,
                "tier_rank": TIER_RANK.get(scr.tier.value, 0),
            }
        )

    with (DIR / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    contested = [r for r in rows if r["label"] == "contested"]
    quiet = [r for r in rows if r["label"] == "quiet"]

    def vals(group, key):
        return [r[key] for r in group if r[key] is not None]

    report = {"n_contested": len(contested), "n_quiet": len(quiet), "pillars": {}}

    for key in ("water", "grid", "burden", "tier_rank"):
        c, q = vals(contested, key), vals(quiet, key)
        med_c = sorted(c)[len(c) // 2] if c else None
        med_q = sorted(q)[len(q) // 2] if q else None
        _, p = _mannwhitney_u(c, q)
        # AUC needs aligned scores/labels over rows where key present
        paired = [(r[key], 1 if r["label"] == "contested" else 0) for r in rows if r[key] is not None]
        auc = _auc([x for x, _ in paired], [y for _, y in paired])
        report["pillars"][key] = {
            "median_contested": med_c,
            "median_quiet": med_q,
            "mean_contested": round(sum(c) / len(c), 1) if c else None,
            "mean_quiet": round(sum(q) / len(q), 1) if q else None,
            "auc": round(auc, 3),
            "p_one_sided": round(p, 4),
        }

    # tier hit-rates
    def share_ge(group, rank):
        g = [r for r in group if r["tier_rank"] is not None]
        return round(100 * sum(1 for r in g if r["tier_rank"] >= rank) / len(g), 1) if g else None

    report["tier_hit_rate"] = {
        "contested_pct_elevated_or_high": share_ge(contested, 2),
        "quiet_pct_elevated_or_high": share_ge(quiet, 2),
        "contested_pct_high": share_ge(contested, 3),
        "quiet_pct_high": share_ge(quiet, 3),
    }
    (DIR / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    import pprint

    pprint.pp(run())
