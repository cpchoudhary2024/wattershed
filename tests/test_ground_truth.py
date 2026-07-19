"""Ground-truth regression tests: recompute pillar scores from the RAW source
files (eGRID workbook, Aqueduct polygons, USDM history, tract parquet) without
going through the scoring modules, and assert the committed flagship outputs
match. These are the tests that would catch a silent join error or a shifted
column — the failure mode that would destroy the tool's credibility.

Skipped automatically when the raw caches/outputs are absent (e.g. a fresh
clone that has not run a screening yet); CI runs them after the flagship build.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wattershed import config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

BWS_BASE_SCORE = {-1: 85.0, 0: 5.0, 1: 25.0, 2: 50.0, 3: 75.0, 4: 95.0}
CURRENT_SCORE = {None: 0.0, 0: 20.0, 1: 40.0, 2: 60.0, 3: 80.0, 4: 100.0}
NERC_STRAIN = {"high": 90.0, "elevated": 55.0, "normal": 10.0}

POLL = ["pm25", "ozone", "no2", "diesel_pm", "rsei_air_toxics", "traffic_proximity",
        "npl_proximity", "rmp_proximity", "tsdf_proximity", "tri_count_5km"]
VULN = ["pct_low_income", "pct_unemployed", "pct_limited_english_hh",
        "pct_no_hs_diploma", "pct_adult_asthma", "pct_fair_poor_health"]


def _result(slug: str) -> dict:
    p = OUT / f"{slug}.json"
    if not p.exists():
        pytest.skip(f"{slug} screening output not present")
    return json.loads(p.read_text())


def _ind(result: dict, pillar: str, ind_id: str) -> dict | None:
    return next((i for i in result[pillar]["indicators"] if i["id"] == ind_id), None)


def test_grid_pillar_matches_raw_egrid_and_nerc():
    """Rainier: grid = 0.6 * (raw eGRID rate percentile) + 0.4 * (NERC category)."""
    xlsx = config.CACHE_DIR / "egrid2023_data_rev2.xlsx"
    if not xlsx.exists():
        pytest.skip("eGRID workbook not cached")
    r = _result("aws-rainier-new-carlisle")
    rate_ind, nerc_ind = _ind(r, "grid", "egrid_co2e_rate"), _ind(r, "grid", "nerc_ltra_risk")
    assert rate_ind and nerc_ind

    xl = pd.ExcelFile(xlsx)
    sheet = next(s for s in xl.sheet_names if s.upper().startswith("SRL"))
    raw = pd.read_excel(xl, sheet_name=sheet, header=1)
    raw = raw[raw["SUBRGN"].notna()].copy()
    raw["SRC2ERTA"] = pd.to_numeric(raw["SRC2ERTA"], errors="coerce")
    raw = raw.dropna(subset=["SRC2ERTA"])

    subrgn = rate_ind["label"].split("(")[-1].rstrip(")")
    rate = float(raw.loc[raw["SUBRGN"] == subrgn, "SRC2ERTA"].iloc[0])
    pctile = float((raw["SRC2ERTA"].rank(pct=True) * 100)[raw["SUBRGN"] == subrgn].iloc[0])

    assert abs(float(rate_ind["value"]) - round(rate)) <= 1.0
    assert abs(float(rate_ind["percentile"]) - pctile) < 0.2

    strain = NERC_STRAIN[nerc_ind["display"].split(" ")[0].lower()]
    assert abs(r["grid"]["score"] - (0.6 * pctile + 0.4 * strain)) < 0.15


def test_water_pillar_matches_raw_aqueduct_and_usdm():
    """Abilene: water = 0.5*structural(Aqueduct) + 0.3*chronic(DSCI) + 0.2*current."""
    gpkg = config.PROCESSED_DIR / "aqueduct_bws_us.gpkg"
    if not gpkg.exists():
        pytest.skip("Aqueduct extract not built")
    import geopandas as gpd
    import yaml

    r = _result("stargate-abilene")
    sites = {s["slug"]: s for s in yaml.safe_load((ROOT / "data/curated/sites.yaml").read_text())["sites"]}
    site = sites["stargate-abilene"]

    basins = gpd.read_file(gpkg)
    pt = gpd.GeoDataFrame(geometry=gpd.points_from_xy([site["lon"]], [site["lat"]]), crs=4326)
    bcat = int(gpd.sjoin(pt, basins, predicate="within").iloc[0]["bws_cat"])
    structural = BWS_BASE_SCORE[bcat]

    wi = {i["id"]: i for i in r["water"]["indicators"]}
    chronic = min(100.0, 100.0 * float(wi["usdm_5yr_dsci"]["value"]) / 500.0)
    cur = wi["usdm_current"]["value"]
    current = CURRENT_SCORE[None if cur is None else int(cur)]

    assert abs(r["water"]["components"]["structural"] - structural) < 0.05
    assert abs(r["water"]["score"] - (0.5 * structural + 0.3 * chronic + 0.2 * current)) < 0.15


def test_burden_pillar_matches_raw_tract_table():
    """Memphis: P and V domains and the CBI percentile recomputed from parquet.

    Also asserts the reported neighborhood tract count equals the number of
    POPULATED tracts actually driving the score — the two must never diverge.
    """
    pq = config.PROCESSED_DIR / "tract_indicators.parquet"
    if not pq.exists():
        pytest.skip("reference table not present")
    import yaml

    r = _result("xai-colossus-memphis")
    t = pd.read_parquet(pq)
    t["geoid"] = t["geoid"].astype(str).str.zfill(11)
    sites = {s["slug"]: s for s in yaml.safe_load((ROOT / "data/curated/sites.yaml").read_text())["sites"]}
    site = sites["xai-colossus-memphis"]

    lat_r, lon_r = np.radians(site["lat"]), np.radians(site["lon"])
    tlat, tlon = np.radians(t["intptlat"].values), np.radians(t["intptlon"].values)
    a = np.sin((tlat - lat_r) / 2) ** 2 + np.cos(lat_r) * np.cos(tlat) * np.sin((tlon - lon_r) / 2) ** 2
    dist = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
    sub = t[(dist <= config.NEIGHBORHOOD_RADIUS_KM) & (t["population"].fillna(0) > 0)]
    assert not sub.empty

    w = sub["population"].values.astype(float)
    p_cbi = sub["p_cbi"].values.astype(float)
    m = ~np.isnan(p_cbi)
    hand_score = float(np.average(p_cbi[m], weights=w[m]))

    assert abs(r["burden"]["score"] - hand_score) < 0.6, "burden score drifted from raw tract data"
    # reported basis must equal the true populated-tract basis
    assert r["neighborhood"]["tracts"] == int(len(sub))
    assert r["neighborhood"]["population"] == int(w.sum())
    # a thin basis must be disclosed, not silently presented as neighborhood-wide
    if len(sub) < 3:
        gaps = " ".join(r["burden"]["data_gaps"])
        assert "populated tract" in gaps and "robustness check" in gaps


def test_burden_domains_are_multiplicative_on_real_tract():
    """CBI = P x V / 100 must hold on a real populated tract, end to end."""
    pq = config.PROCESSED_DIR / "tract_indicators.parquet"
    if not pq.exists():
        pytest.skip("reference table not present")
    t = pd.read_parquet(pq)
    row = t[(t["population"].fillna(0) > 500) & t["cbi"].notna()].iloc[0]
    P = np.nanmean([row[f"p_{c}"] for c in POLL])
    V = np.nanmean([row[f"p_{c}"] for c in VULN])
    assert abs(row["pollution_domain"] - P) < 1e-6
    assert abs(row["vulnerability_domain"] - V) < 1e-6
    assert abs(row["cbi"] - P * V / 100.0) < 1e-6
