"""NERC 2025 LTRA resource-adequacy risk categories (published Jan 2026).

The categorical designations were transcribed from the assessment's Table 1 /
regional dashboards into data/reference/nerc_ltra.csv (cited, hand-checked).
eGRID subregions map to LTRA assessment areas via
data/reference/egrid_subregion_map.csv; imperfect mappings carry an explicit
confidence flag, and curated sites may pin their true RTO.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from .. import config

RISK_SCORE = {"high": 90.0, "elevated": 55.0, "normal": 10.0, "not_assessed": None}


@lru_cache(maxsize=1)
def _ltra() -> pd.DataFrame:
    return pd.read_csv(config.REFERENCE_DIR / "nerc_ltra.csv")


@lru_cache(maxsize=1)
def _srmap() -> pd.DataFrame:
    return pd.read_csv(config.REFERENCE_DIR / "egrid_subregion_map.csv")


def area_risk(nerc_area: str) -> dict | None:
    df = _ltra()
    row = df[df["assessment_area"] == nerc_area]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "area": r["assessment_area"],
        "category": r["risk_category"],
        "first_high_year": None if pd.isna(r["first_high_year"]) else int(r["first_high_year"]),
        "detail": r["detail"],
        "score": RISK_SCORE.get(r["risk_category"]),
    }


def risk_for_subregion(subrgn: str, rto_override: str | None = None) -> dict | None:
    m = _srmap()
    row = m[m["subrgn"] == subrgn]
    if row.empty:
        return None
    r = row.iloc[0]
    area = rto_override or r["nerc_area"]
    # allow overrides given as RTO labels (e.g. "PJM") that are themselves areas
    res = area_risk(area)
    if res is None and rto_override:
        res = area_risk(r["nerc_area"])
    if res is None:
        return None
    res["rto_label"] = rto_override or r["rto_label"]
    res["map_confidence"] = "high" if rto_override else r["map_confidence"]
    res["map_note"] = "" if rto_override else (r["note"] if isinstance(r["note"], str) else "")
    return res
