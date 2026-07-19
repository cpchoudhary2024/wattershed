"""Tier rules are the contract of the tool — test the trigger matrix."""

from wattershed.models import PillarScore, Tier
from wattershed.scoring.tiers import assign_tier


def _p(pillar, score):
    return PillarScore(pillar=pillar, score=score, band="x")


def _tier(w, g, b, **kw):
    t, _ = assign_tier(_p("water", w), _p("grid", g), _p("burden", b), **kw)
    return t


def test_low_when_all_quiet():
    assert _tier(10, 20, 5) is Tier.LOW


def test_moderate_single_35():
    assert _tier(36, 10, 10) is Tier.MODERATE


def test_elevated_single_60():
    assert _tier(61, 10, 10) is Tier.ELEVATED


def test_elevated_two_45s():
    assert _tier(46, 47, 10) is Tier.ELEVATED


def test_high_any_80():
    assert _tier(10, 10, 81) is Tier.HIGH


def test_high_70_plus_55():
    assert _tier(71, 56, 10) is Tier.HIGH


def test_water_escalator_promotes_one_step():
    # elevated base (61 water) + demand escalator -> High
    assert _tier(61, 10, 10, demand_water_pct=3.0) is Tier.HIGH


def test_water_escalator_needs_stressed_water():
    # water below 45: escalator must NOT fire even with huge demand
    assert _tier(30, 10, 10, demand_water_pct=50.0) is Tier.LOW
    t, reasons = assign_tier(_p("water", 30), _p("grid", 10), _p("burden", 10), demand_water_pct=50.0)
    assert t is Tier.LOW
    assert not any("Escalator" in r for r in reasons)


def test_grid_escalator():
    t, reasons = assign_tier(_p("water", 10), _p("grid", 50), _p("burden", 10), demand_grid_pct=2.0)
    assert t is Tier.ELEVATED
    assert any("Escalator" in r for r in reasons)


def test_missing_pillar_noted():
    t, reasons = assign_tier(_p("water", 10), _p("grid", 10), PillarScore(pillar="burden", score=None, band="insufficient data"))
    assert any("Data gaps" in r for r in reasons)


def test_escalator_never_exceeds_high():
    t, _ = assign_tier(_p("water", 90), _p("grid", 90), _p("burden", 90),
                       demand_water_pct=10, demand_grid_pct=10)
    assert t is Tier.HIGH
