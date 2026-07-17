"""Grid strain & carbon pillar (0–100).

  carbon (60%) — eGRID subregion CO2e output-rate percentile across all
      subregions. Annual average (location-based accounting), not marginal.
  strain (40%) — NERC 2025 LTRA resource-adequacy category for the mapped
      assessment area (high=90 / elevated=55 / normal=10).

Load-share context (modeled load vs. subregion net generation) is reported
and can escalate the tier, but is not in the score (depends on user MW).
"""

from __future__ import annotations

from ..models import Confidence, Indicator, PillarScore

WEIGHTS = {"carbon": 0.6, "strain": 0.4}


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


def score_grid(egrid_stats: dict | None, nerc_risk: dict | None, load_share_pct: float | None) -> PillarScore:
    indicators: list[Indicator] = []
    components: dict[str, float] = {}
    drivers: list[str] = []
    gaps: list[str] = []

    if egrid_stats:
        components["carbon"] = egrid_stats["rate_percentile"]
        indicators.append(
            Indicator(
                id="egrid_co2e_rate",
                label=f"Grid carbon intensity — {egrid_stats['name']} ({egrid_stats['subrgn']})",
                value=round(egrid_stats["co2e_lb_per_mwh"], 0),
                display=f"{egrid_stats['co2e_lb_per_mwh']:,.0f} lb CO₂e/MWh "
                f"(P{egrid_stats['rate_percentile']:.0f} of U.S. subregions)",
                unit="lb CO₂e/MWh (annual output rate)",
                percentile=round(egrid_stats["rate_percentile"], 1),
                source_id="egrid2023",
                vintage="calendar 2023 (eGRID2023 rev.2, pub. June 2025)",
                confidence=Confidence.HIGH,
                note="Annual average rate — not marginal emissions; see limitations.",
            )
        )
        indicators.append(
            Indicator(
                id="egrid_mix",
                label="Generation mix (subregion)",
                display=f"{egrid_stats['fossil_share_pct']:.0f}% fossil · "
                f"{egrid_stats['carbon_free_share_pct']:.0f}% carbon-free",
                source_id="egrid2023",
                vintage="calendar 2023",
                confidence=Confidence.HIGH,
            )
        )
        if egrid_stats["rate_percentile"] >= 70:
            drivers.append(
                f"Subregion emission rate ({egrid_stats['co2e_lb_per_mwh']:,.0f} lb CO₂e/MWh) is in "
                f"the top {100 - egrid_stats['rate_percentile']:.0f}% nationally."
            )
    else:
        gaps.append("eGRID subregion could not be resolved for this point.")

    if nerc_risk and nerc_risk.get("score") is not None:
        components["strain"] = nerc_risk["score"]
        year = f" (first High year: {nerc_risk['first_high_year']})" if nerc_risk.get("first_high_year") else ""
        conf = Confidence.HIGH if nerc_risk.get("map_confidence") == "high" else Confidence.MEDIUM
        indicators.append(
            Indicator(
                id="nerc_ltra_risk",
                label=f"Resource-adequacy risk — {nerc_risk['area']}",
                display=f"{nerc_risk['category'].upper()}{year}",
                source_id="nerc_ltra_2025",
                vintage="2025 LTRA (pub. Jan 2026), 2026–2030 window",
                confidence=conf,
                note=nerc_risk.get("map_note", ""),
            )
        )
        if nerc_risk["category"] == "high":
            drivers.append(
                f"NERC classifies {nerc_risk['area']} as HIGH resource-adequacy risk{year} — "
                "new large loads directly deepen the projected shortfall."
            )
        elif nerc_risk["category"] == "elevated":
            drivers.append(f"NERC classifies {nerc_risk['area']} as ELEVATED resource-adequacy risk.")
    else:
        gaps.append("No NERC LTRA assessment area mapped (AK/HI/PR are not LTRA areas).")

    if load_share_pct is not None:
        indicators.append(
            Indicator(
                id="load_share",
                label="Modeled load vs. subregion net generation",
                value=round(load_share_pct, 2),
                display=f"{load_share_pct:.2f}% of subregion 2023 net generation",
                unit="%",
                source_id="egrid2023",
                vintage="denominator: calendar 2023",
                confidence=Confidence.MEDIUM,
                note="Context only — not part of the grid score; can escalate the overall tier.",
            )
        )
        if load_share_pct >= 1.0:
            drivers.append(
                f"This single campus would consume ≈{load_share_pct:.1f}% of the subregion's "
                "entire current net generation."
            )

    avail = {k: v for k, v in components.items() if v is not None}
    if avail:
        wsum = sum(WEIGHTS[k] for k in avail)
        score = sum(WEIGHTS[k] * v for k, v in avail.items()) / wsum
    else:
        score = None
    return PillarScore(
        pillar="grid",
        score=round(score, 1) if score is not None else None,
        band=band(score),
        indicators=indicators,
        drivers=drivers,
        data_gaps=gaps,
        components={k: round(v, 1) for k, v in components.items()},
    )
