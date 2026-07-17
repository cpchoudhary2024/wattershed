"""Water-stress pillar (0–100).

Three sub-signals with distinct time horizons, blended with documented
weights (sensitivity analysis in METHODOLOGY.md §6):

  structural (50%) — WRI Aqueduct 4.0 baseline water stress: the long-run
      demand/supply balance of the sub-basin. Dominant siting determinant.
  chronic (30%)   — 5-year mean county DSCI (USDM climatology): recurring
      drought pressure not captured by the Aqueduct baseline vintage.
  current (20%)   — this week's USDM category: transient, but it is the
      screening trigger regulators and journalists reach for first.

Site-demand context (modeled draw vs. county public supply) deliberately does
NOT enter the score — it depends on user-supplied MW — but can escalate the
overall tier (see tiers.py).
"""

from __future__ import annotations

from ..models import Confidence, Indicator, PillarScore
from ..provenance import retrieved_at
from .. import config

BWS_BASE_SCORE = {-1: 85.0, 0: 5.0, 1: 25.0, 2: 50.0, 3: 75.0, 4: 95.0}

WEIGHTS = {"structural": 0.5, "chronic": 0.3, "current": 0.2}

CURRENT_SCORE = {None: 0.0, 0: 20.0, 1: 40.0, 2: 60.0, 3: 80.0, 4: 100.0}


def band(score: float | None) -> str:
    if score is None:
        return "insufficient data"
    if score >= 75:
        return "severe"
    if score >= 55:
        return "high"
    if score >= 35:
        return "moderate"
    return "low"


def score_water(
    bws: dict | None,
    current: dict,
    history: dict,
    demand_context: dict | None,
) -> PillarScore:
    indicators: list[Indicator] = []
    components: dict[str, float] = {}
    drivers: list[str] = []
    gaps: list[str] = []

    # structural scarcity — Aqueduct 4.0
    if bws and bws.get("bws_cat") is not None:
        cat = bws["bws_cat"]
        structural = BWS_BASE_SCORE.get(cat)
        components["structural"] = structural
        note = (
            "Category 'Arid & low water use' scores 85: absolute availability is minimal even "
            "though current use is low — new large withdrawals change that arithmetic."
            if cat == -1
            else ""
        )
        indicators.append(
            Indicator(
                id="aqueduct_bws",
                label="Baseline water stress (WRI Aqueduct 4.0, sub-basin)",
                value=bws.get("bws_raw"),
                display=bws.get("bws_label", ""),
                unit="withdrawals ÷ renewable supply",
                source_id="aqueduct40",
                vintage="1979–2019 baseline (pub. 2023)",
                confidence=Confidence.HIGH,
                note=note,
            )
        )
        if cat is not None and cat >= 3:
            drivers.append(f"Sub-basin baseline water stress is {bws.get('bws_label', '')}.")
    else:
        gaps.append("Aqueduct baseline water stress unavailable for this point.")
        indicators.append(
            Indicator(
                id="aqueduct_bws",
                label="Baseline water stress (WRI Aqueduct 4.0, sub-basin)",
                source_id="aqueduct40",
                missing=True,
                confidence=Confidence.LOW,
                note="No sub-basin polygon matched; score computed from drought signals only.",
            )
        )

    # chronic drought — 5-yr county DSCI
    mean_dsci = history.get("mean_dsci")
    if mean_dsci is not None:
        chronic = min(100.0, 100.0 * mean_dsci / 500.0)
        components["chronic"] = chronic
        indicators.append(
            Indicator(
                id="usdm_5yr_dsci",
                label="5-year mean drought severity (county DSCI)",
                value=round(mean_dsci, 1),
                display=f"{mean_dsci:.0f} / 500 · D2+ in {history.get('pct_weeks_d2plus', 0):.0f}% of weeks",
                unit="DSCI (0–500)",
                source_id="usdm_county_history",
                vintage=history.get("window", "past 5 years"),
                confidence=Confidence.HIGH,
            )
        )
        if history.get("pct_weeks_d2plus", 0) >= 25:
            drivers.append(
                f"County spent {history['pct_weeks_d2plus']:.0f}% of the past five years with "
                "severe-or-worse (D2+) drought covering ≥10% of its area."
            )
    else:
        gaps.append("County drought history unavailable.")

    # current drought — this week's map
    cat = current.get("category")
    components["current"] = CURRENT_SCORE.get(cat, 0.0)
    from ..sources.usdm import CATEGORY_LABELS

    indicators.append(
        Indicator(
            id="usdm_current",
            label="Current drought status (USDM weekly map)",
            value=float(cat) if cat is not None else None,
            display=CATEGORY_LABELS.get(cat, "None"),
            source_id="usdm_current",
            vintage=f"map of {current.get('map_date', '?')}",
            retrieved=retrieved_at(config.CACHE_DIR / "usdm_current.zip") or "",
            confidence=Confidence.HIGH,
            note="Transient signal — a single wet or dry week should not drive siting; weighted 20%.",
        )
    )
    if cat is not None and cat >= 2:
        drivers.append(f"Site is currently in {CATEGORY_LABELS[cat]}.")

    # demand context (unscored)
    if demand_context and demand_context.get("pct_public_supply") is not None:
        pct = demand_context["pct_public_supply"]
        cooling_label = demand_context.get("cooling_label") or "cooling"
        indicators.append(
            Indicator(
                id="demand_vs_supply",
                label=f"Modeled {cooling_label} draw vs. county public supply (2015)",
                value=round(pct, 2),
                display=f"{pct:.1f}% of county public-supply withdrawals",
                unit="%",
                source_id="usgs_wateruse_2015",
                vintage="county denominators: 2015 (latest USGS county compilation)",
                confidence=Confidence.MEDIUM,
                note="Context only — not part of the water score; can escalate the overall tier.",
            )
        )
        if pct >= 2.0:
            drivers.append(
                f"Modeled {cooling_label} demand equals {pct:.1f}% of the county's entire "
                "2015 public-supply withdrawals."
            )

    # blend available components, renormalizing weights over what exists
    avail = {k: v for k, v in components.items() if v is not None}
    if avail:
        wsum = sum(WEIGHTS[k] for k in avail)
        score = sum(WEIGHTS[k] * v for k, v in avail.items()) / wsum
    else:
        score = None
    return PillarScore(
        pillar="water",
        score=round(score, 1) if score is not None else None,
        band=band(score),
        indicators=indicators,
        drivers=drivers,
        data_gaps=gaps,
        components={k: round(v, 1) for k, v in components.items()},
    )
