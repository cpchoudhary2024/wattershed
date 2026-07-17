"""Mitigation engine: rule-based, driver-aware recommendations.

Each rule fires off specific screening findings and cites a real, named
precedent — these are the levers environmental consultants actually put in
front of clients and planning boards, not generic advice.
"""

from __future__ import annotations

from ..models import CoolingTech, Mitigation, PillarScore, SiteInput


def recommend(
    site: SiteInput,
    water: PillarScore,
    grid: PillarScore,
    burden: PillarScore,
    demand_water_pct: float | None,
) -> list[Mitigation]:
    out: list[Mitigation] = []
    w, g, b = water.score or 0, grid.score or 0, burden.score or 0

    if w >= 55 and site.cooling in (CoolingTech.EVAPORATIVE, CoolingTech.UNKNOWN):
        out.append(
            Mitigation(
                pillar="water",
                title="Shift cooling design off potable evaporative water",
                detail=(
                    "Air-cooled or hybrid (water-side economizer + trim) designs cut site water use "
                    "85–97% versus open cooling towers at a 0.10–0.15 PUE penalty — see the demand "
                    "scenario table for this site's quantified trade-off."
                ),
                precedent=(
                    "Microsoft's post-2023 U.S. designs are announced as zero-water-for-cooling "
                    "(closed-loop); Meta standardized on indirect evaporative with target WUE ≤0.20 "
                    "in arid regions."
                ),
            )
        )
    if w >= 55:
        out.append(
            Mitigation(
                pillar="water",
                title="Contract reclaimed / non-potable supply before permitting",
                detail=(
                    "A reclaimed-water service agreement moves the draw off the potable system and is "
                    "the single most effective de-risking signal for water-stressed jurisdictions."
                ),
                precedent=(
                    "Loudoun Water (VA) serves data centers reclaimed water for cooling; Google's "
                    "Douglas County, GA campus runs on treated wastewater."
                ),
            )
        )
    if demand_water_pct is not None and demand_water_pct >= 2.0:
        out.append(
            Mitigation(
                pillar="water",
                title="Commit to metered, public water-use reporting",
                detail=(
                    "Where modeled demand is a visible share of county supply, voluntary public "
                    "metering defuses the records-fight dynamic that has repeatedly turned siting "
                    "contests hostile."
                ),
                precedent=(
                    "The Dalles, OR: Google's water use became public through a records lawsuit the "
                    "city fought and lost (2023) — disclosure-by-design avoids that path."
                ),
            )
        )
    if g >= 55:
        out.append(
            Mitigation(
                pillar="grid",
                title="Pair the load with new clean firm capacity or storage-backed PPAs",
                detail=(
                    "In NERC elevated/high-risk areas, additionality matters more than RECs: bring "
                    "new dispatchable-clean or storage-firmed generation to the same grid, sized to "
                    "the campus."
                ),
                precedent=(
                    "AWS–Talen Susquehanna nuclear colocation (PA); Google–NV Energy 115 MW "
                    "geothermal Clean Transition Tariff (2024)."
                ),
            )
        )
        out.append(
            Mitigation(
                pillar="grid",
                title="Design for curtailable / flexible operation",
                detail=(
                    "Registering training-class load as curtailable during grid emergencies converts "
                    "the facility from a reliability liability into a demand-response asset."
                ),
                precedent=(
                    "ERCOT's 2025 large-load curtailment framework (SB6, Texas); Google's "
                    "demand-response commitments with Indiana Michigan Power (2025)."
                ),
            )
        )
    if b >= 75:
        out.append(
            Mitigation(
                pillar="burden",
                title="Negotiate an enforceable community-benefits agreement (CBA)",
                detail=(
                    "In a top-quartile cumulative-burden tract, a CBA with independent monitoring "
                    "(local hiring, utility-bill relief, health investments) is the credible floor "
                    "for community legitimacy — not a voluntary donation program."
                ),
                precedent=(
                    "Community coalitions in South Memphis (xAI, 2024–25) demanded exactly this after "
                    "unpermitted turbine operation; several Georgia counties now condition rezoning "
                    "on CBAs."
                ),
            )
        )
        out.append(
            Mitigation(
                pillar="burden",
                title="Eliminate on-site combustion backup where feasible",
                detail=(
                    "Diesel/gas backup fleets concentrate exactly the pollutants (diesel PM, NOx) "
                    "that drive the tract's existing burden. BESS backup, Tier 4 Final engines with "
                    "runtime caps, and grid-interactive UPS remove the largest local air-quality "
                    "delta."
                ),
                precedent=(
                    "Microsoft's Dublin and San Jose sites permit grid-interactive batteries in lieu "
                    "of diesel; Santa Clara County caps generator test hours."
                ),
            )
        )
    if b >= 75 and (site.status in ("proposed", "contested") or not site.status):
        out.append(
            Mitigation(
                pillar="burden",
                title="Commission an independent Health Impact Assessment pre-permit",
                detail=(
                    "An HIA with community participation, done before land-use votes, is the "
                    "professional standard for cumulative-burden sites and materially changes "
                    "approval odds."
                ),
                precedent="Standard practice in EJ-sensitive permitting (EPA EJ Legal Tools, 2022).",
            )
        )
    if not out:
        out.append(
            Mitigation(
                pillar="general",
                title="Maintain the screening margin",
                detail=(
                    "No pillar triggered mitigation thresholds. Preserve that position: publish "
                    "water/energy metrics annually and re-screen at design changes."
                ),
                precedent="",
            )
        )
    return out
