import numpy as np
import pandas as pd

from wattershed.scoring import reference
from wattershed.scoring.water import score_water


def _fake_row(fill_pollution=10, fill_vuln=6, pct=50.0):
    data = {}
    for i, c in enumerate(reference.POLLUTION_COLS):
        v = pct if i < fill_pollution else np.nan
        data[c] = 1.0 if i < fill_pollution else np.nan
        data[reference.pct_col(c)] = v
    for i, c in enumerate(reference.VULNERABILITY_COLS):
        v = pct if i < fill_vuln else np.nan
        data[c] = 1.0 if i < fill_vuln else np.nan
        data[reference.pct_col(c)] = v
    data["p_cbi"] = pct
    data["population"] = 1000
    return pd.Series(data)


def test_domain_floors_enforced():
    dom = reference.domain_scores(_fake_row(fill_pollution=4))
    assert dom["pollution"] is None  # below 5-indicator floor
    dom = reference.domain_scores(_fake_row(fill_vuln=3))
    assert dom["vulnerability"] is None  # below 4-indicator floor


def test_cbi_multiplicative():
    dom = reference.domain_scores(_fake_row(pct=80.0))
    assert abs(dom["cbi"] - 64.0) < 1e-6  # 80 * 80 / 100


def test_water_weight_renormalization_without_bws():
    ps = score_water(
        bws=None,
        current={"category": 2, "map_date": "2026-01-01"},
        history={"mean_dsci": 250.0, "pct_weeks_d2plus": 40.0, "window": "w"},
        demand_context=None,
    )
    # chronic=50 (0.3), current=60 (0.2) -> (0.3*50+0.2*60)/0.5 = 54
    assert abs(ps.score - 54.0) < 0.2
    assert any("unavailable" in g.lower() or "matched" in g.lower() for g in ps.data_gaps) or ps.indicators[0].missing


def test_water_arid_low_use_flagged_high():
    ps = score_water(
        bws={"bws_cat": -1, "bws_raw": None, "bws_score": None, "bws_label": "Arid & low water use"},
        current={"category": None, "map_date": "2026-01-01"},
        history={"mean_dsci": 0.0, "pct_weeks_d2plus": 0.0, "window": "w"},
        demand_context=None,
    )
    # structural 85*0.5 + chronic 0*0.3 + current 0*0.2 = 42.5
    assert abs(ps.score - 42.5) < 0.2
