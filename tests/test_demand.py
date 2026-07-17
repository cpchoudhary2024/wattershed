from wattershed.demand import build_demand_model, indirect_water_l_per_kwh
from wattershed.models import CoolingTech


def test_energy_math():
    dm = build_demand_model(100, CoolingTech.EVAPORATIVE, 800.0, 1e8, 100.0, None)
    assert dm.it_energy_mwh_yr == round(100 * 1000 * 8760 * 0.8 / 1000)
    evap = next(s for s in dm.scenarios if s.cooling == "evaporative")
    assert evap.facility_energy_mwh_yr == round(dm.it_energy_mwh_yr * 1.2)


def test_water_scales_with_wue():
    dm = build_demand_model(100, CoolingTech.UNKNOWN, None, None, None, None)
    by = {s.cooling: s for s in dm.scenarios}
    # evaporative (1.8) vs air (0.05): factor 36
    assert abs(by["evaporative"].water_mgal_yr / by["air"].water_mgal_yr - 36) < 0.5


def test_co2_conversion():
    dm = build_demand_model(10, CoolingTech.AIR, 1000.0, None, None, None)
    air = next(s for s in dm.scenarios if s.cooling == "air")
    expected = air.facility_energy_mwh_yr * 1000 / 2204.62
    assert abs(air.co2e_tonnes_yr - expected) < 1


def test_pct_county_supply():
    dm = build_demand_model(300, CoolingTech.EVAPORATIVE, None, None, 146.93, None)
    evap = next(s for s in dm.scenarios if s.cooling == "evaporative")
    assert abs(evap.pct_county_public_supply - 100 * evap.water_mgd / 146.93) < 0.05


def test_site_cooling_scenario_leads():
    dm = build_demand_model(100, CoolingTech.AIR, None, None, None, None)
    assert dm.scenarios[0].cooling == "air"


def test_indirect_water_excludes_hydro():
    l_all, covered = indirect_water_l_per_kwh({"hydro": 1.0})
    assert l_all == 0.0 and covered == 0.0
    l_gas, cov = indirect_water_l_per_kwh({"gas": 1.0})
    assert 0.7 < l_gas < 0.8 and cov == 1.0  # 198 gal/MWh ≈ 0.75 L/kWh
