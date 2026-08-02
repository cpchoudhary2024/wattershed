"""Siting-equity study: do U.S. data centers locate disproportionately in
water-stressed, grid-strained, or high community-burden places?

This is the empirical study the tool was building toward. It compares the
distribution of the three pillar scores at data-center locations against the
national, population-weighted baseline of all U.S. counties/tracts.

Data-center locations come from OpenStreetMap (data/study/datacenters_osm.csv),
an openly licensed source NOT selected for controversy — which is what makes
this a fair test rather than a confirmation of hand-picked cases. Coverage is
incomplete (OSM maps what mappers map); this biases toward the facilities that
are large/known, and is disclosed as the primary limitation.

Method:
  - burden: tract-level (FCC point-in-polygon would be ideal; here we use the
    tract whose population-weighted centroid is nearest, from the committed
    reference table — an approximation documented in LIMITATIONS).
  - water/grid: county-level (their true resolution), from the county atlas.
  - Baseline: population-weighted distribution over all counties (for water/grid)
    and all populated tracts (for burden), so we ask "relative to where people
    live," not "relative to empty land."
  - Tests: Mann-Whitney U (two-sided) + rank-biserial effect size; KS statistic;
    over-representation ratio of DC sites in the national top quartile.

Run: python -m wattershed.pipelines.siting_equity
"""

from __future__ import annotations

import csv
import json
import math

import numpy as np
import pandas as pd

from .. import config
from ..pipelines import atlas as atlas_mod
from ..scoring import reference

DIR = config.PROCESSED_DIR.parent / "study"
DC_CSV = DIR / "datacenters_osm.csv"


def _nearest_tract_burden(t: pd.DataFrame, lat: float, lon: float) -> float | None:
    la, lo = math.radians(lat), math.radians(lon)
    tlat = np.radians(t["intptlat"].values)
    tlon = np.radians(t["intptlon"].values)
    a = np.sin((tlat - la) / 2) ** 2 + np.cos(la) * np.cos(tlat) * np.sin((tlon - lo) / 2) ** 2
    idx = int(np.argmin(a))
    v = t.iloc[idx]["p_cbi"]
    return None if pd.isna(v) else float(v)


def _mannwhitney(a, b):
    """Two-sided p (normal approx, tie-corrected) + rank-biserial effect size."""
    a, b = list(a), list(b)
    comb = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks = [0.0] * len(comb)
    i = 0
    while i < len(comb):
        j = i
        while j + 1 < len(comb) and comb[j + 1][0] == comb[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    r_a = sum(ranks[k] for k in range(len(comb)) if comb[k][1] == 0)
    na, nb = len(a), len(b)
    u_a = r_a - na * (na + 1) / 2
    mu = na * nb / 2
    n = na + nb
    tie = 0.0
    i = 0
    while i < len(comb):
        j = i
        while j + 1 < len(comb) and comb[j + 1][0] == comb[i][0]:
            j += 1
        tcnt = j - i + 1
        tie += tcnt**3 - tcnt
        i = j + 1
    sigma = math.sqrt(na * nb / 12 * ((n + 1) - tie / (n * (n - 1)))) if n > 1 else 0.0
    z = (u_a - mu) / sigma if sigma else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))  # two-sided
    rbc = 2 * u_a / (na * nb) - 1  # rank-biserial: + => a>b
    return p, rbc


def _ks(a, b):
    a, b = np.sort(a), np.sort(b)
    grid = np.sort(np.concatenate([a, b]))
    ca = np.searchsorted(a, grid, side="right") / len(a)
    cb = np.searchsorted(b, grid, side="right") / len(b)
    return float(np.max(np.abs(ca - cb)))


def _weighted_quantile(values, weights, q):
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    m = ~np.isnan(v)
    v, w = v[m], w[m]
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w) - 0.5 * w
    cw /= np.sum(w)
    return float(np.interp(q, cw, v))


def run() -> dict:
    dc = list(csv.DictReader(DC_CSV.open()))
    t = reference.table()
    counties = pd.read_csv(atlas_mod.ATLAS_PATH, dtype={"county": str})
    counties["county"] = counties["county"].str.zfill(5)
    catlas = counties.set_index("county")

    # ---- score each data center ----
    from ..sources import egrid  # noqa: F401  (kept for potential extension)

    dc_burden, dc_water, dc_grid = [], [], []
    for r in dc:
        lat, lon = float(r["lat"]), float(r["lon"])
        b = _nearest_tract_burden(t, lat, lon)
        if b is not None:
            dc_burden.append(b)
        # county for water/grid: nearest county centroid in the atlas
        d2 = (catlas["lat"] - lat) ** 2 + ((catlas["lon"] - lon) * math.cos(math.radians(lat))) ** 2
        crow = catlas.loc[d2.idxmin()]
        if pd.notna(crow["water"]):
            dc_water.append(float(crow["water"]))
        if pd.notna(crow["grid"]):
            dc_grid.append(float(crow["grid"]))

    # ---- national population-weighted baselines ----
    pop_t = t["population"].fillna(0).clip(lower=0).values
    base_burden = t["p_cbi"].values
    cpop = counties["population"].fillna(0).clip(lower=0).values

    def summarize(name, dc_vals, base_vals, base_w):
        dc_vals = [v for v in dc_vals if v is not None and not np.isnan(v)]
        p, rbc = _mannwhitney(dc_vals, [v for v in base_vals if not np.isnan(v)])
        ks = _ks(np.array(dc_vals), np.array([v for v in base_vals if not np.isnan(v)]))
        top_q = _weighted_quantile(base_vals, base_w, 0.75)
        dc_top = np.mean([v >= top_q for v in dc_vals]) * 100
        # national share in its own top quartile is 25% by construction (pop-wt)
        return {
            "n_dc": len(dc_vals),
            "dc_mean": round(float(np.mean(dc_vals)), 1),
            "national_popwt_median": round(_weighted_quantile(base_vals, base_w, 0.5), 1),
            "dc_median": round(float(np.median(dc_vals)), 1),
            "pct_dc_in_national_top_quartile": round(float(dc_top), 1),
            "over_representation_x": round(float(dc_top / 25.0), 2),
            "ks_stat": round(ks, 3),
            "mannwhitney_p": round(p, 6),
            "effect_rank_biserial": round(rbc, 3),
        }

    report = {
        "n_datacenters": len(dc),
        "source": "OpenStreetMap (telecom/man_made=data_center), CONUS bbox",
        "burden": summarize("burden", dc_burden, base_burden, pop_t),
        "water": summarize("water", dc_water, counties["water"].values, cpop),
        "grid": summarize("grid", dc_grid, counties["grid"].values, cpop),
    }
    (DIR / "siting_equity_report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    import pprint

    pprint.pp(run())
