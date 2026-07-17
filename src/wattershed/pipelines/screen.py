"""Screening orchestrator: one point in, one fully-provenanced Screening out."""

from __future__ import annotations

from .. import config, demand as demand_mod, geocode, provenance
from ..models import CoolingTech, Screening, SiteInput
from ..scoring import burden as burden_mod
from ..scoring import grid as grid_mod
from ..scoring import mitigation, reference, tiers
from ..scoring import water as water_mod
from ..sources import aqueduct, egrid, frs, nerc, usdm, water_use
from ..sources.base import SourceUnavailable
from .. import __version__

STANDING_LIMITATIONS = [
    "Tract-level indicators describe the area around a point, not the parcel itself; a site on a "
    "tract boundary inherits its containing tract's profile.",
    "eGRID rates are annual average (location-based) intensities, not marginal emissions; actual "
    "incremental emissions depend on dispatch and contracted supply.",
    "County public-supply denominators are from the 2015 USGS compilation — the latest complete "
    "county water-use census; fast-growing counties will have shifted.",
    "Five pollution indicators are frozen at EPA EJScreen 2.32 vintage (2024 release) because EPA "
    "withdrew the tool in Feb 2025; they no longer update.",
    "All demand figures are modeled from published engineering factors, not measured facility data.",
    "The neighborhood summary assigns tracts by population-weighted centroid distance, an "
    "approximation of true buffer intersection.",
]


def screen_site(site: SiteInput, rto_override: str | None = None) -> Screening:
    ledger = provenance.Ledger()
    lat, lon = site.lat, site.lon

    geo = geocode.locate(lat, lon)
    ledger.touch("census_geocoder")

    # ---- water pillar inputs
    try:
        current = usdm.current_drought(lat, lon)
        ledger.touch("usdm_current", provenance.retrieved_at(config.CACHE_DIR / "usdm_current.zip"))
    except SourceUnavailable:
        current = {"category": None, "map_date": "unavailable"}
    try:
        history = usdm.county_drought_history(geo.county_fips)
        ledger.touch("usdm_county_history")
    except SourceUnavailable:
        history = {"mean_dsci": None, "pct_weeks_d2plus": None}

    bws = aqueduct.bws_for_point(lat, lon)
    if bws:
        ledger.touch("aqueduct40")

    county_ctx = None
    try:
        county_ctx = water_use.county_water_context(geo.county_fips)
        if county_ctx:
            ledger.touch("usgs_wateruse_2015")
    except SourceUnavailable:
        pass

    # ---- grid pillar inputs
    subrgn = egrid.subregion_for_point(lat, lon)
    stats = egrid.subregion_stats(subrgn) if subrgn else None
    if stats:
        ledger.touch("egrid2023")
        ledger.touch("egrid_subregions_gis")
    risk = nerc.risk_for_subregion(subrgn, rto_override) if subrgn else None
    if risk:
        ledger.touch("nerc_ltra_2025")

    # ---- demand model (only when capacity is known)
    dm = None
    demand_water_pct = None
    demand_grid_pct = None
    demand_cooling_label = ""
    if site.it_mw:
        dm = demand_mod.build_demand_model(
            it_mw=site.it_mw,
            cooling=site.cooling,
            co2e_lb_per_mwh=stats["co2e_lb_per_mwh"] if stats else None,
            subregion_net_gen_mwh=stats["net_gen_mwh"] if stats else None,
            county_public_supply_mgd=(county_ctx or {}).get("public_supply_mgd"),
            grid_mix=stats["mix"] if stats else None,
        )
        for sid in dm.assumptions_source_ids:
            ledger.touch(sid)
        # water-demand context follows the site's documented cooling design;
        # only unknown-cooling sites are judged on the evaporative hypothetical
        known = {s.cooling: s for s in dm.scenarios}
        if site.cooling.value in known:
            lead = known[site.cooling.value]
            demand_cooling_label = f"{lead.cooling}-cooling (site design)"
        else:
            lead = known["evaporative"]
            demand_cooling_label = "evaporative-cooling (hypothetical — site design undisclosed)"
        demand_water_pct = lead.pct_county_public_supply
        if stats and stats["net_gen_mwh"]:
            demand_grid_pct = 100 * (dm.it_energy_mwh_yr * 1.25) / stats["net_gen_mwh"]

    # ---- score pillars
    water = water_mod.score_water(
        bws, current, history,
        {"pct_public_supply": demand_water_pct, "cooling_label": demand_cooling_label}
        if demand_water_pct is not None
        else None,
    )
    grid = grid_mod.score_grid(stats, risk, demand_grid_pct)
    burden, burden_ctx = burden_mod.score_burden(geo.tract_geoid, lat=lat, lon=lon)
    for sid in ("acs_2023_5yr", "cdc_places_2024", "ejscreen_v232_replica", "frs_national"):
        if burden.score is not None:
            ledger.touch(sid)

    if burden_ctx.get("tract_population") is not None:
        geo.tract_population = burden_ctx["tract_population"]

    # ---- neighborhood + live facility list
    try:
        hood = reference.neighborhood(lat, lon) or {}
    except reference.ReferenceUnavailable:
        hood = {}
    hood_extra = dict(hood)
    hood_extra.update({f"tract_{k}": v for k, v in burden_ctx.items()})
    if stats:
        hood_extra["_grid_mix"] = stats["mix"]  # consumed by the report's mix bar

    nearby = frs.tri_near(lat, lon) or {}
    facilities = nearby.get("nearest", [])
    if facilities:
        ledger.touch("frs_national")

    # ---- tier + mitigations
    tier, reasons = tiers.assign_tier(
        water, grid, burden, demand_water_pct, demand_grid_pct,
        demand_cooling_label=demand_cooling_label,
    )
    mits = mitigation.recommend(site, water, grid, burden, demand_water_pct)

    if site.provenance:
        ledger.touch("curated_sites")

    limitations = list(STANDING_LIMITATIONS)
    if site.coord_precision and site.coord_precision != "address":
        limitations.insert(
            0,
            f"Site coordinates are {site.coord_precision}-precision; tract-level results may shift "
            "with the exact parcel.",
        )

    return Screening(
        site=site,
        geo=geo,
        tier=tier,
        tier_reasons=reasons,
        water=water,
        grid=grid,
        burden=burden,
        demand=dm,
        mitigations=mits,
        neighborhood=hood_extra,
        nearby_facilities=facilities,
        sources=ledger.to_records(),
        limitations=limitations,
        generated_at=provenance.utc_now_iso(),
        tool_version=__version__,
    )


def screen_point(
    lat: float,
    lon: float,
    name: str = "Unnamed site",
    it_mw: float | None = None,
    cooling: str = "unknown",
    address: str = "",
) -> Screening:
    site = SiteInput(
        name=name, lat=lat, lon=lon, address=address,
        it_mw=it_mw, cooling=CoolingTech(cooling),
        coord_precision="address" if address else "point",
    )
    return screen_site(site)
