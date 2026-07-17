"""Resource-demand model: announced IT capacity → energy, water, CO2e.

Everything here is a MODELED ESTIMATE from published engineering factors —
never presented as measured facility data. Constants carry citations; ranges
are shown in reports rather than a single false-precision number.

Key factors and sources:
- Utilization of announced IT capacity: 0.80 assumed (hyperscale AI campuses
  run high, steady load; sensitivity shown at 0.6/0.9). Assumption, documented.
- PUE by cooling family: LBNL 2024 U.S. Data Center Energy Usage Report
  (Shehabi et al.) hyperscale ranges; Uptime Institute 2024 global average
  (1.56) is shown as context in the methodology.
- Site WUE (L/kWh of IT energy): LBNL 2024 report ranges; evaporative systems
  cluster near 1.8, hybrid ~0.6, air-cooled ~0.05.
- Indirect (generation) water: eGRID subregion fuel mix × Macknick et al.
  (2012) median consumption factors; hydropower reservoir evaporation is
  EXCLUDED (contested attribution) and noted.
- CO2e: eGRID subregion annual average output rate (screening-grade;
  marginal-emissions caveat in LIMITATIONS.md).
- Vehicle equivalence: EPA GHG equivalencies, 4.6 t CO2e/passenger vehicle/yr.
"""

from __future__ import annotations

from .models import CoolingTech, DemandModel, DemandScenario

UTILIZATION = 0.80
HOURS_PER_YEAR = 8760

# cooling family -> (PUE, site WUE in L per kWh of IT energy)
COOLING_FACTORS: dict[CoolingTech, tuple[float, float]] = {
    CoolingTech.EVAPORATIVE: (1.20, 1.8),
    CoolingTech.HYBRID: (1.25, 0.6),
    CoolingTech.AIR: (1.35, 0.05),
}

# Macknick et al. 2012 median operational water CONSUMPTION, gal/MWh generated.
# hydro excluded (reservoir-evaporation attribution is contested).
MACKNICK_GAL_PER_MWH = {
    "coal": 687.0,
    "oil": 687.0,
    "gas": 198.0,          # combined cycle median
    "other_fossil": 687.0,
    "nuclear": 672.0,
    "biomass": 553.0,
    "geothermal": 15.0,
    "wind": 0.0,
    "solar": 26.0,         # utility PV
    "hydro": None,         # excluded — see note
    "other": 0.0,
}

LB_PER_TONNE = 2204.62
EPA_TONNES_PER_VEHICLE_YR = 4.6
GAL_PER_L = 0.264172


def indirect_water_l_per_kwh(mix: dict[str, float]) -> tuple[float, float]:
    """(L consumed per kWh generated, share of mix covered by factors)."""
    total_l, covered = 0.0, 0.0
    for fuel, share in mix.items():
        f = MACKNICK_GAL_PER_MWH.get(fuel)
        if f is None or share is None:
            continue
        total_l += share * f * 3.78541 / 1000.0
        covered += share
    return total_l, covered


def build_demand_model(
    it_mw: float,
    cooling: CoolingTech,
    co2e_lb_per_mwh: float | None,
    subregion_net_gen_mwh: float | None,
    county_public_supply_mgd: float | None,
    grid_mix: dict[str, float] | None,
) -> DemandModel:
    it_energy = it_mw * 1000 * HOURS_PER_YEAR * UTILIZATION / 1000  # MWh/yr
    scenarios: list[DemandScenario] = []
    for tech, (pue, wue) in COOLING_FACTORS.items():
        fac_energy = it_energy * pue
        water_l = it_energy * 1000 * wue           # L/yr (WUE is per IT kWh)
        water_mgal = water_l * GAL_PER_L / 1e6
        water_mgd = water_mgal / 365.0
        pct_ps = (
            100 * water_mgd / county_public_supply_mgd
            if county_public_supply_mgd and county_public_supply_mgd > 0
            else None
        )
        co2 = fac_energy * co2e_lb_per_mwh / LB_PER_TONNE if co2e_lb_per_mwh else None
        scenarios.append(
            DemandScenario(
                cooling=tech.value,
                pue=pue,
                wue_l_per_kwh_it=wue,
                facility_energy_mwh_yr=round(fac_energy),
                water_mgal_yr=round(water_mgal, 1),
                water_mgd=round(water_mgd, 2),
                pct_county_public_supply=round(pct_ps, 2) if pct_ps is not None else None,
                co2e_tonnes_yr=round(co2) if co2 is not None else None,
            )
        )
    # order scenarios so the site's actual/likely cooling family leads
    if cooling in COOLING_FACTORS:
        scenarios.sort(key=lambda s: 0 if s.cooling == cooling.value else 1)

    indirect_note = ""
    if grid_mix:
        l_per_kwh, covered = indirect_water_l_per_kwh(grid_mix)
        fac_energy_mid = it_energy * 1.25
        indirect_mgal = fac_energy_mid * 1000 * l_per_kwh * GAL_PER_L / 1e6
        indirect_note = (
            f"Indirect water consumed by power generation for this load, using the regional fuel "
            f"mix and Macknick et al. (2012) median factors (~{l_per_kwh:.2f} L/kWh across "
            f"{covered * 100:.0f}% of the mix; hydropower reservoir evaporation excluded): "
            f"≈{indirect_mgal:,.0f} Mgal/yr at PUE 1.25. Often larger than on-site cooling water."
        )

    grid_note = ""
    if subregion_net_gen_mwh and subregion_net_gen_mwh > 0:
        share = 100 * (it_energy * 1.25) / subregion_net_gen_mwh
        grid_note = (
            f"At PUE 1.25 this load would equal {share:.2f}% of the eGRID subregion's entire "
            f"2023 net generation."
        )

    return DemandModel(
        it_mw=it_mw,
        utilization=UTILIZATION,
        it_energy_mwh_yr=round(it_energy),
        scenarios=scenarios,
        indirect_water_note=indirect_note,
        grid_share_note=grid_note,
        assumptions_source_ids=["lbnl_demand_2024", "macknick_2012", "egrid2023", "epa_ghg_equiv"],
    )
