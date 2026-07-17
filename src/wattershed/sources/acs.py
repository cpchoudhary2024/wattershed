"""ACS 2019–2023 5-year tract indicators from the Census *table-based summary
file* — bulk pipe-delimited files, fully keyless and reproducible.

Files: https://www2.census.gov/programs-surveys/acs/summary_file/2023/
       table-based-SF/data/5YRData/acsdt5y2023-<table>.dat

Each file contains every geography for one table; tract rows have
GEO_ID = '1400000US' + 11-digit GEOID.
"""

from __future__ import annotations

import re

import pandas as pd

from .base import cached_download

_BASE = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData"

TABLES = ["c17002", "b23025", "c16002", "b15003", "b03002", "b01003"]


def _load_table(table: str) -> pd.DataFrame:
    url = f"{_BASE}/acsdt5y2023-{table}.dat"
    p = cached_download(url, f"acsdt5y2023-{table}.dat", "acs_2023_5yr")
    df = pd.read_csv(p, sep="|", dtype=str)
    df = df[df["GEO_ID"].str.startswith("1400000US", na=False)].copy()
    df["geoid"] = df["GEO_ID"].str.removeprefix("1400000US")
    return df


def _col(df: pd.DataFrame, table: str, idx: int) -> pd.Series:
    """Resolve an estimate column regardless of naming variant
    (TABLE_E001 vs TABLE_001E) and return it as float."""
    t = table.upper()
    candidates = [f"{t}_E{idx:03d}", f"{t}_{idx:03d}E"]
    for c in candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    pat = re.compile(rf"^{t}_0*{idx}E$|^{t}_E0*{idx}$")
    for c in df.columns:
        if pat.match(c):
            return pd.to_numeric(df[c], errors="coerce")
    raise KeyError(f"{table} estimate column {idx} not found; have e.g. {list(df.columns)[:6]}")


def build_tract_demographics() -> pd.DataFrame:
    """Return one row per tract with the vulnerability-domain inputs."""
    c17 = _load_table("c17002")
    out = pd.DataFrame({"geoid": c17["geoid"]})
    tot = _col(c17, "c17002", 1)
    ge2 = _col(c17, "c17002", 8)
    out["pct_low_income"] = (100 * (tot - ge2) / tot).where(tot > 0)

    b23 = _load_table("b23025").set_index("geoid")
    lf = _col(b23, "b23025", 3)
    unemp = _col(b23, "b23025", 5)
    out = out.set_index("geoid")
    out["pct_unemployed"] = (100 * unemp / lf).where(lf > 0)

    c16 = _load_table("c16002").set_index("geoid")
    hh = _col(c16, "c16002", 1)
    lim = sum(_col(c16, "c16002", i) for i in (4, 7, 10, 13))
    out["pct_limited_english_hh"] = (100 * lim / hh).where(hh > 0)

    b15 = _load_table("b15003").set_index("geoid")
    adults = _col(b15, "b15003", 1)
    no_dip = sum(_col(b15, "b15003", i) for i in range(2, 17))
    out["pct_no_hs_diploma"] = (100 * no_dip / adults).where(adults > 0)

    b03 = _load_table("b03002").set_index("geoid")
    pop_b03 = _col(b03, "b03002", 1)
    nhw = _col(b03, "b03002", 3)
    out["pct_people_of_color"] = (100 * (pop_b03 - nhw) / pop_b03).where(pop_b03 > 0)

    b01 = _load_table("b01003").set_index("geoid")
    out["population"] = _col(b01, "b01003", 1)

    return out.reset_index()
