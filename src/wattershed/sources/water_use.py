"""USGS county water use, 2015 (latest complete county-level compilation).

Used ONLY as denominator context ("modeled site demand vs. county public-
supply withdrawals"), never as a current-conditions signal — the vintage is
flagged on every rendered value.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from .base import cached_download

# ScienceBase direct file URL for usco2015v2.0.csv (doi:10.5066/F7TB15V5)
_CSV_URL = (
    "https://www.sciencebase.gov/catalog/file/get/5af3311be4b0da30c1b245d8"
    "?f=__disk__eb%2F74%2Feb%2Feb74ebb41169c76aaf374990bd5a71cac82604c1"
)


@lru_cache(maxsize=1)
def _table() -> pd.DataFrame:
    p = cached_download(_CSV_URL, "usco2015v2.0.csv", "usgs_wateruse_2015")
    # row 0 is the USGS citation line; '--' marks not-available values
    df = pd.read_csv(
        p, skiprows=1, na_values=["--"],
        dtype={"FIPS": str, "STATEFIPS": str, "COUNTYFIPS": str}, low_memory=False,
    )
    df.columns = [c.strip() for c in df.columns]
    df["FIPS"] = df["FIPS"].str.zfill(5)
    return df


def county_water_context(county_fips: str) -> dict | None:
    df = _table()
    row = df[df["FIPS"] == county_fips]
    if row.empty:
        return None
    r = row.iloc[0]

    def num(col):
        try:
            v = float(r[col])
            return v if v >= 0 else None
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "county": f"{r.get('COUNTY', '')}, {r.get('STATE', '')}",
        "public_supply_mgd": num("PS-Wtotl"),      # total public-supply withdrawals
        "total_withdrawals_mgd": num("TO-Wtotl"),  # all categories, fresh+saline
        "irrigation_mgd": num("IR-WFrTo"),         # irrigation freshwater total
        "population_thousands": num("TP-TotPop"),
    }
