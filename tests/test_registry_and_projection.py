
import yaml

from wattershed import config
from wattershed.dashboard.build import project
from wattershed.models import CoolingTech


def _sites():
    p = config.CURATED_DIR / "sites.yaml"
    return yaml.safe_load(p.read_text())["sites"]


def test_registry_schema():
    sites = _sites()
    slugs = [s["slug"] for s in sites]
    assert len(slugs) == len(set(slugs)), "duplicate slugs"
    for s in sites:
        assert 17 < s["lat"] < 72 and -180 < s["lon"] < -60, s["slug"]
        assert s["coord_precision"] in ("address", "parcel-adjacent", "locality"), s["slug"]
        assert len(s.get("citations", [])) >= 2, f"{s['slug']} needs >=2 citations"
        for c in s["citations"]:
            assert c.get("url", "").startswith("http"), s["slug"]
        CoolingTech(s.get("cooling", "unknown"))  # raises on invalid value
        assert s.get("status") in ("operating", "construction", "proposed", "contested", "rejected")


def test_mw_only_when_cited():
    # every site with announced_mw must carry a note or citation; nulls allowed
    for s in _sites():
        if s.get("announced_mw"):
            assert s["citations"], s["slug"]


def test_projection_orientation():
    seattle = project(-122.33, 47.60)
    miami = project(-80.19, 25.76)
    nyc = project(-74.00, 40.71)
    la = project(-118.24, 34.05)
    assert seattle[1] < miami[1], "north must be up"
    assert la[0] < nyc[0], "west must be left"
    for x, y in (seattle, miami, nyc, la):
        assert 0 <= x <= 975 and 0 <= y <= 610


def test_reference_table_integrity():
    import pytest

    path = config.PROCESSED_DIR / "tract_indicators.parquet"
    if not path.exists():
        pytest.skip("reference table not built in this environment")
    import pandas as pd

    t = pd.read_parquet(path)
    assert len(t) > 80000
    pcols = [c for c in t.columns if c.startswith("p_")]
    for c in pcols:
        v = t[c].dropna()
        assert (v.between(0, 100)).all(), c
    assert t["p_cbi"].notna().mean() > 0.9
