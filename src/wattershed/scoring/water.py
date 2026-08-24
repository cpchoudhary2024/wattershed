# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
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

from .. import config
from ..models import Confidence, Indicator, PillarScore
from ..provenance import retrieved_at
from .normalize import band, blend, clamp, is_number

BWS_BASE_SCORE = {-1: 85.0, 0: 5.0, 1: 25.0, 2: 50.0, 3: 75.0, 4: 95.0}

WEIGHTS = {"structural": 0.5, "chronic": 0.3, "current": 0.2}

CURRENT_SCORE = {None: 0.0, 0: 20.0, 1: 40.0, 2: 60.0, 3: 80.0, 4: 100.0}


def score_water(
    bws: dict | None,
    current: dict,
    history: dict,
    demand_context: dict | None,
) -> PillarScore:
    """Score the water-stress pillar for one screening point.

    Blends three sub-signals on documented weights (structural 50%, chronic 30%,
    current 20%); see METHODOLOGY.md §6 for the sensitivity analysis. Site demand
    is deliberately excluded from the score because it depends on user-supplied MW,
    though it can escalate the overall tier (see ``tiers.py``).

    Args:
        bws (dict | None): WRI Aqueduct 4.0 sub-basin record. Expects
            ``bws_cat`` (int, -1..4), ``bws_raw`` (float, withdrawals ÷ renewable
            supply, dimensionless) and ``bws_label`` (str). None when the point
            falls outside Aqueduct coverage.
        current (dict): This week's US Drought Monitor record; ``d_cat`` is the
            D0-D4 category (int 0-4) or None for no drought.
        history (dict): Five-year county USDM climatology; ``dsci_mean`` is the
            mean Drought Severity and Coverage Index (dimensionless, 0-500).
        demand_context (dict | None): Modeled site draw vs. county public supply.
            Reported for context only; does NOT enter the score.

    Returns:
        PillarScore: Score on 0-100 where HIGHER means MORE water-stressed, with
        per-indicator provenance, the component breakdown, plain-language drivers,
        and an explicit list of data gaps.

    Assumptions:
        Aqueduct's 1979-2019 baseline is treated as the long-run structural signal
        and is not adjusted for recent hydrology. 'Arid & low water use' (category
        -1) is scored 85, not 5: absolute availability is minimal even where
        current use is low, and a new large withdrawal changes that arithmetic.
    """
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
    if is_number(mean_dsci):
        # clamp, not min(): a negative or non-finite DSCI is a data defect,
        # and 100*(-40)/500 would otherwise enter the blend as -8.
        chronic = clamp(100.0 * mean_dsci / 500.0) if is_number(mean_dsci) else None
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

    # current drought — this week's map.
    # `None` legitimately means "not inside any drought polygon" → 0. An
    # UNRECOGNIZED category is a different thing entirely and must not default
    # to the best-case score; it drops out of the blend as a data gap.
    cat = current.get("category")
    if cat in CURRENT_SCORE:
        components["current"] = CURRENT_SCORE[cat]
    else:
        components["current"] = None
        gaps.append(f"Unrecognized USDM drought category {cat!r} — current-drought signal excluded.")
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
    # `in CATEGORY_LABELS` guard: an unrecognized category reached this line as
    # a raw KeyError and aborted the whole screening.
    if cat in CATEGORY_LABELS and cat is not None and cat >= 2:
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
    score = blend(components, WEIGHTS)
    return PillarScore(
        pillar="water",
        score=round(score, 1) if score is not None else None,
        band=band(score),
        indicators=indicators,
        drivers=drivers,
        data_gaps=gaps,
        components={k: round(v, 1) for k, v in components.items() if is_number(v)},
    )
