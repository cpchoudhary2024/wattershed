"""Build the multi-source data-center census and assign each site an exact
census tract + county by point-in-polygon (FCC Census Area API, the same
authoritative service the live tool uses).

Sources unioned (deduped at ~150 m):
  - OpenStreetMap (datacenters_osm.csv), the bulk national sample
  - curated flagship campuses (data/curated/sites.yaml) — hand-verified
  - validation labeled set (data/validation/sites_labeled.csv) — hand-verified

Output: datacenters_census.csv with tract_geoid + county_fips filled in and
cached, so the study reads exact geographies with no re-calls (reproducible).
Run once: python data/study/_build_census.py
"""
import csv
import time
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).parent
ROOT = HERE.parent.parent


def load_osm():
    for r in csv.DictReader((HERE / "datacenters_osm.csv").open()):
        yield {"name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"]), "source": "osm"}


def load_curated():
    d = yaml.safe_load((ROOT / "data/curated/sites.yaml").read_text())
    for s in d["sites"]:
        yield {"name": s["name"], "lat": float(s["lat"]), "lon": float(s["lon"]), "source": "curated"}


def load_validation():
    for r in csv.DictReader((ROOT / "data/validation/sites_labeled.csv").open()):
        yield {"name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"]), "source": "validation"}


def dedupe(rows, prec=3):
    seen, out = set(), []
    # prefer hand-verified rows when coordinates collide
    order = {"curated": 0, "validation": 1, "osm": 2}
    for r in sorted(rows, key=lambda r: order[r["source"]]):
        k = (round(r["lat"], prec), round(r["lon"], prec))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def fcc_tract(lat, lon):
    """(tract_geoid, county_fips) via FCC point-in-polygon; None on failure."""
    try:
        r = requests.get(
            "https://geo.fcc.gov/api/census/area",
            params={"lat": lat, "lon": lon, "censusYear": 2020, "format": "json"},
            timeout=20,
        )
        res = (r.json().get("results") or [])[0]
        b = res.get("block_fips")
        return (b[:11], b[:5]) if b else (None, None)
    except Exception:
        return (None, None)


def main():
    rows = dedupe(list(load_osm()) + list(load_curated()) + list(load_validation()))
    print(f"census after union+dedupe: {len(rows)} sites")
    ok = 0
    for i, r in enumerate(rows):
        g, c = fcc_tract(r["lat"], r["lon"])
        r["tract_geoid"], r["county_fips"] = g or "", c or ""
        if g:
            ok += 1
        if i % 200 == 0:
            print(f"  {i}/{len(rows)} assigned ({ok} ok)", flush=True)
        time.sleep(0.08)
    out = HERE / "datacenters_census.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "source", "lat", "lon", "tract_geoid", "county_fips"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out}: {len(rows)} sites, {ok} with exact tract ({100*ok/len(rows):.1f}%)")


if __name__ == "__main__":
    main()
