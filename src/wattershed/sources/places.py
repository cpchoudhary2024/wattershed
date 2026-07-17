"""CDC PLACES (2024 release) — tract-level modeled health outcomes.

Measures used: CASTHMA (current adult asthma), GHLTH (fair/poor self-rated
health). Small-area estimates modeled from BRFSS — appropriate for relative
screening, not clinical surveillance (flagged MEDIUM confidence).
"""

from __future__ import annotations

import pandas as pd

from .. import config
from .base import fetch_json

_SODA = "https://data.cdc.gov/resource/cwsq-ngmh.json"
_CACHE = config.CACHE_DIR / "places_tract_2024.csv"

MEASURES = ("CASTHMA", "GHLTH")


def build_tract_health(force: bool = False) -> pd.DataFrame:
    if _CACHE.exists() and not force:
        return pd.read_csv(_CACHE, dtype={"geoid": str})
    rows: list[dict] = []
    offset, page = 0, 50000
    where = "measureid in" + str(tuple(MEASURES))
    while True:
        batch = fetch_json(
            _SODA,
            params={
                "$select": "locationname,measureid,data_value",
                "$where": where,
                "$limit": page,
                "$offset": offset,
                "$order": "locationname,measureid",
            },
            timeout=180,
        )
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    df = pd.DataFrame(rows)
    df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")
    wide = df.pivot_table(index="locationname", columns="measureid", values="data_value").reset_index()
    wide = wide.rename(
        columns={"locationname": "geoid", "CASTHMA": "pct_adult_asthma", "GHLTH": "pct_fair_poor_health"}
    )
    wide["geoid"] = wide["geoid"].astype(str).str.zfill(11)
    wide.to_csv(_CACHE, index=False)
    return wide
