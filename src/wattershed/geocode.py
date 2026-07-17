"""U.S. Census Bureau geocoder (free, keyless).

- coordinates → tract GEOID / county / state  (point screening context)
- one-line address → coordinates              (address input mode)
"""

from __future__ import annotations

from .models import GeoContext
from .sources.base import SourceUnavailable, fetch_json

_GEO_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
_ADDR_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def locate(lat: float, lon: float) -> GeoContext:
    data = fetch_json(
        _GEO_URL,
        params={
            "x": lon,
            "y": lat,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        },
    )
    geogs = data.get("result", {}).get("geographies", {})
    tracts = geogs.get("Census Tracts", [])
    counties = geogs.get("Counties", [])
    states = geogs.get("States", [])
    if not tracts or not counties:
        raise SourceUnavailable(
            f"Census geocoder returned no tract/county for ({lat:.4f}, {lon:.4f}) — "
            "point may be outside U.S. tract coverage."
        )
    t, c = tracts[0], counties[0]
    s = states[0] if states else {}
    return GeoContext(
        tract_geoid=t["GEOID"],
        county_fips=c["GEOID"],
        county_name=c.get("BASENAME", ""),
        state_abbr=s.get("STUSAB", ""),
        state_name=s.get("BASENAME", ""),
    )


def geocode_address(oneline: str) -> tuple[float, float, str]:
    data = fetch_json(
        _ADDR_URL,
        params={"address": oneline, "benchmark": "Public_AR_Current", "format": "json"},
    )
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        raise SourceUnavailable(f"No geocoder match for address: {oneline!r}")
    m = matches[0]
    return m["coordinates"]["y"], m["coordinates"]["x"], m.get("matchedAddress", oneline)
