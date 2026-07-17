# Data sources

Every upstream source, its vintage, license, access mode, and role. All
sources are free and keyless. Access date for all sources: **2026-07-16**
(retrieval timestamps are also stamped per-file in `data/cache/*.meta.json`
and per-run in every screening JSON/report).

| Source | Provider | Vintage | Access | Role | License / attribution |
|---|---|---|---|---|---|
| [U.S. Drought Monitor weekly shapefile](https://droughtmonitor.unl.edu/data/shapefiles_m/USDM_current_M.zip) | NDMC / USDA / NOAA | weekly (Thursdays) | bulk zip, refreshed ≤3-day cache | current drought category at point | Public; courtesy line required (rendered in every report footer) |
| [USDM county statistics API](https://usdmdataservices.unl.edu/) | NDMC | weekly series 2000– | REST, keyless | 5-year county DSCI climatology | Public |
| [WRI Aqueduct 4.0](https://www.wri.org/data/aqueduct-global-maps-40-data) | World Resources Institute | 1979–2019 baseline (pub. 2023) | 261 MB zip once at reference build; U.S. extract committed | baseline water stress (sub-basin) | CC BY 4.0 — Kuzma et al. (2023) |
| [USGS county water use 2015](https://www.sciencebase.gov/catalog/item/5af3311be4b0da30c1b245d8) | USGS | calendar 2015 | CSV via ScienceBase | county public-supply denominators | Public domain; doi:10.5066/F7TB15V5 |
| [EPA eGRID2023 rev.2](https://www.epa.gov/egrid) | U.S. EPA | calendar 2023 (pub. Jun 2025) | xlsx + subregion shapefile | CO₂e rates, fuel mix, net generation, subregion geometry | Public domain |
| [NERC 2025 Long-Term Reliability Assessment](https://www.nerc.com/globalassets/our-work/assessments/nerc_ltra_2025.pdf) | NERC | horizon 2026–2035 (pub. Jan 2026) | risk categories hand-transcribed to `data/reference/nerc_ltra.csv` from Table 1 / regional dashboards | resource-adequacy strain | Public assessment; transcription checkable against the PDF |
| [Census geocoder](https://geocoding.geo.census.gov/) | U.S. Census Bureau | current benchmark | REST, keyless | address/point → tract, county | Public domain |
| [ACS 2019–2023 5-yr table-based summary files](https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/) | U.S. Census Bureau | 2019–2023 pooled | bulk pipe-delimited files (keyless — no API key needed even for full rebuilds) | tract socioeconomics (C17002, B23025, C16002, B15003, B03002, B01003) | Public domain |
| [CDC PLACES 2024](https://data.cdc.gov/resource/cwsq-ngmh.json) | CDC | BRFSS 2022 model year | Socrata SODA, keyless | tract asthma & self-rated health | Public domain |
| [EPA Facility Registry Service national file](https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip) | U.S. EPA | rolling snapshot | 40 MB zip at reference build | TRI facility coordinates → live proximity + per-tract density | Public domain |
| [EPA Envirofacts](https://data.epa.gov/efservice/) | U.S. EPA | rolling | REST, keyless | per-site facility enrichment | Public domain |
| [EJScreen 2.32 (community-restored)](https://screening-tools.com/epa-ejscreen) | Public Environmental Data Partners (orig. U.S. EPA) | 2.32 final (2024; ACS 2018–22; AirToxScreen 2020) | paged ArcGIS feature-service query at reference build; block groups aggregated to tracts population-weighted | 9 frozen pollution indicators | Public-domain federal work product, community-rehosted. EPA withdrew the tool Feb 2025 |
| [Census 2024 tract gazetteer](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/) & [cartographic state boundaries](https://www2.census.gov/geo/tiger/GENZ2024/shp/) | U.S. Census Bureau | 2024 TIGER | bulk | tract centroids; dashboard basemap | Public domain |
| [LBNL 2024 U.S. Data Center Energy Usage Report](https://eta.lbl.gov/publications/2024-lbnl-data-center-energy-usage-report) | LBNL (Shehabi et al.) | pub. Dec 2024 | constants transcribed | PUE/WUE scenario factors | Public report, cited |
| [Macknick et al. 2012](https://iopscience.iop.org/article/10.1088/1748-9326/7/4/045802) | NREL / ERL | 2012 medians | constants transcribed | generation water-consumption factors | Open access, cited |
| `data/curated/sites.yaml` | this repo | per-fact citation dates | hand-curated | flagship site registry | MIT (compilation); every load-bearing fact cites public reporting. **Not exhaustive, not authoritative** |

## Resilience notes (post-2025 federal data environment)

Two inputs were affected by 2025 federal takedowns and are handled explicitly:

- **EJScreen** — the tool is gone from epa.gov; the underlying final release
  survives via the Public Environmental Data Partners coalition (plus the
  Harvard Dataverse `doi:10.7910/DVN/RLR5AX` and Zenodo
  `doi:10.5281/zenodo.14767363` archives as alternates). Wattershed touches
  it once, at reference-build time, then works from the committed table.
- **CEJST** — not used directly; its methodology informed the burden-pillar
  design (threshold logic, race-neutral scoring inputs).

If any live endpoint disappears, screening still runs from committed
artifacts; only `build-reference` (full reproduction) would need the
documented alternates.

## Committed data artifacts

So that `git clone` → `wattershed screen` works with zero keys and no
600 MB of downloads, three build outputs are committed:

| Artifact | Size | Contents | Rebuild |
|---|---|---|---|
| `data/processed/tract_indicators.parquet` | 26 MB | 85,396 tracts × 16 indicators + national percentiles + CBI | `wattershed build-reference` |
| `data/processed/aqueduct_bws_us.gpkg` | 21 MB | U.S. clip of Aqueduct 4.0 baseline-annual bws fields | idem |
| `data/processed/tri_facilities.csv.gz` | 1.7 MB | geocoded TRI-linked facilities from FRS | idem |
| `data/processed/county_atlas.csv` | <1 MB | all-county siting-pressure atlas (three pillar scores per county) | `wattershed build-atlas` (derives from the artifacts above) |

`data/processed/reference_manifest.json` records build timestamps, row
counts, and per-indicator coverage for the committed build.
