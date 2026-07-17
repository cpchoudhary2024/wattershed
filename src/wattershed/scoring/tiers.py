"""Overall screening tier: rule-based, not a weighted composite.

Wattershed deliberately does NOT average the three pillars into one number.
Water scarcity, grid strain, and community burden are incommensurable harms;
averaging lets a good score on one silently buy down a terrible score on
another — the exact failure mode cumulative-impact literature warns about.
Instead, transparent trigger rules assign an action tier, and every tier
comes with its reasons attached. Thresholds are documented and testable.
"""

from __future__ import annotations

from ..models import PillarScore, Tier

# escalators: modeled-demand context that pushes a tier up one step
DEMAND_WATER_ESCALATOR_PCT = 2.0   # evaporative draw ≥2% of county public supply
DEMAND_GRID_ESCALATOR_PCT = 1.0    # load ≥1% of subregion net generation


def assign_tier(
    water: PillarScore,
    grid: PillarScore,
    burden: PillarScore,
    demand_water_pct: float | None = None,
    demand_grid_pct: float | None = None,
    demand_cooling_label: str = "",
) -> tuple[Tier, list[str]]:
    scores = {p.pillar: p.score for p in (water, grid, burden)}
    known = {k: v for k, v in scores.items() if v is not None}
    reasons: list[str] = []

    def any_ge(x: float) -> list[str]:
        return [k for k, v in known.items() if v >= x]

    tier = Tier.LOW
    if any_ge(35):
        tier = Tier.MODERATE
    two_45 = len(any_ge(45)) >= 2
    if any_ge(60) or two_45:
        tier = Tier.ELEVATED
    top = any_ge(80)
    high_combo = len(any_ge(70)) >= 1 and len(any_ge(55)) >= 2
    if top or high_combo:
        tier = Tier.HIGH

    if top:
        reasons.append(
            "Pillar(s) at or above 80/100: " + ", ".join(f"{k} ({known[k]:.0f})" for k in top) + "."
        )
    elif high_combo:
        reasons.append(
            "One pillar ≥70 with a second ≥55: "
            + ", ".join(f"{k} {v:.0f}" for k, v in sorted(known.items(), key=lambda x: -x[1]))
            + "."
        )
    elif tier is Tier.ELEVATED:
        reasons.append(
            "Pillar scores: " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(known.items(), key=lambda x: -x[1])) + "."
        )

    # demand escalators (one step, never past HIGH)
    escalated = False
    if (
        demand_water_pct is not None
        and demand_water_pct >= DEMAND_WATER_ESCALATOR_PCT
        and scores.get("water") is not None
        and scores["water"] >= 45
    ):
        escalated = True
        reasons.append(
            f"Escalator: modeled {demand_cooling_label or 'cooling'} draw = {demand_water_pct:.1f}% "
            f"of county public-supply withdrawals (threshold {DEMAND_WATER_ESCALATOR_PCT:.0f}%) in "
            "an already water-stressed county."
        )
    if (
        demand_grid_pct is not None
        and demand_grid_pct >= DEMAND_GRID_ESCALATOR_PCT
        and scores.get("grid") is not None
        and scores["grid"] >= 45
    ):
        escalated = True
        reasons.append(
            f"Escalator: modeled load = {demand_grid_pct:.1f}% of subregion net generation "
            f"(threshold {DEMAND_GRID_ESCALATOR_PCT:.0f}%) on an already strained grid."
        )
    if escalated:
        order = [Tier.LOW, Tier.MODERATE, Tier.ELEVATED, Tier.HIGH]
        tier = order[min(order.index(tier) + 1, len(order) - 1)]

    missing = [k for k, v in scores.items() if v is None]
    if missing:
        reasons.append(
            "Data gaps in: " + ", ".join(missing) + " — tier reflects available pillars only "
            "and may understate risk."
        )
    if not reasons:
        reasons.append("No pillar reached the Moderate threshold (35/100).")
    return tier, reasons
