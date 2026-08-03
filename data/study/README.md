# Siting-equity study data

## `datacenters_osm.csv` — U.S. data-center locations

- **Source:** OpenStreetMap, via the Overpass API (mirror: overpass.kumi.systems).
- **Query:** features tagged `telecom=data_center` or `man_made=data_center`
  within the continental-U.S. bounding box (24.5–49.5 N, −125.0 to −66.9 W).
- **Retrieved:** 2026-08-02.
- **Processing:** kept features with coordinates (ways reduced to their center
  point), deduplicated at ~100 m to merge facilities mapped more than once.
  1,565 raw → 1,513 unique.
- **License:** OpenStreetMap data is © OpenStreetMap contributors, licensed
  under the Open Database License (ODbL). Derived analysis here is for research.
- **Fields:** `osm_id, name, operator, lat, lon`.

### Known coverage bias (important)
OSM maps what mappers map: coverage is incomplete and skews toward large,
well-known, and metropolitan facilities. This is the primary limitation of the
study and is disclosed in `docs/SITING_EQUITY.md`. A confirmatory analysis needs
a de-biased national data-center census, which does not yet exist openly and
would be a genuine contribution to build.

## `datacenters_census.csv` — analysis census (with exact geographies)

The `datacenters_osm.csv` locations **unioned** with hand-verified flagship
campuses (`data/curated/sites.yaml`) and the validation set
(`data/validation/sites_labeled.csv`), deduplicated at ~150 m (1,569 sites).
Each site's **census tract and county are assigned by FCC point-in-polygon**
(the authoritative service the live tool uses) and cached in the
`tract_geoid` / `county_fips` columns, so the study is reproducible without
re-calling any API. 95.6% resolved exactly; the remainder fall back to nearest
populated centroid at analysis time.

Rebuild the census + tract assignment (network): `python data/study/_build_census.py`
Regenerate the analysis (offline): `python -m wattershed.pipelines.siting_equity`
