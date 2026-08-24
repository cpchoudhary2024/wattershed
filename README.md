# Wattershed

Neighborhood-scale environmental screening for U.S. data center siting: water stress, grid
strain and carbon, and cumulative community burden, computed from public data with
per-value provenance.

**Live tool:** https://cpchoudhary2024.github.io/wattershed/
**License:** PolyForm Noncommercial 1.0.0 · **Tests:** 450 passing · **Data sync:** bi-weekly

---

## 1. Executive Summary & Problem Statement

### The engineering challenge

Hyperscale AI and cloud data centers consume unprecedented volumes of localized water and
electrical capacity. Siting decisions are made at the parcel scale, but the environmental
constraints that determine whether a site is viable — sub-basin water availability, grid
resource adequacy, cumulative pollution burden on the surrounding population — operate at
watershed, balancing-authority, and census-tract scale respectively. These are three
different geographies, three different data vintages, and three different units.

After EPA withdrew **EJScreen** and CEQ withdrew **CEJST** in 2025, developers,
researchers, and community advocates lost the common, transparent framework they had used
to audit cumulative environmental burden at neighborhood scale. What remained was either
proprietary, non-reproducible, or unavailable.

### Technical objective

Geocode any U.S. street address to its census tract and evaluate localized environmental
pressure against a committed national reference table of **85,396 census tracts**, with
every 0–100 score traceable to an authoritative registry, a named vintage, and a retrieval
date. Convert threshold breaches into concrete engineering and permitting review items
rather than raw indicator values.

### Compliance and risk-mitigation impact

The screen supports three decisions. It identifies whether a candidate site sits in a
sub-basin where new large withdrawals are likely to encounter permitting resistance on
hydrologic merit. It quantifies location-based Scope 2 carbon intensity and resource
adequacy risk before interconnection commitments are made. And it flags cumulative
community burden early enough that engagement and benefits agreements remain available as
options rather than reactions.

The dominant exposure identified by the community pillar is **permitting and
administrative** — state environmental justice review, Title VI complaints, organized
opposition — more often than litigation. That distinction changes the mitigation strategy,
and the advisory output states it explicitly.

### Screening scope, stated plainly

This is a **screening-level** analysis. It is not an environmental impact assessment, a
NEPA document, a jurisdictional determination, or engineering due diligence, and it must
not be represented as one.

---

## 2. Regulatory & Industry Standards Alignment

### Explicitly not screened

Clean Water Act **§401** and **§404**, and **NEPA**, are named in the output as *not
screened*. Those determinations turn on an aquatic-resource delineation, a jurisdictional
determination, and a federal nexus — none of which a pressure score can establish. Naming
them prevents a reader from assuming a clean screen implies clean permitting.

### Frameworks applied

| Framework | Application |
|---|---|
| **EPA eGRID2023 rev.2** | Subregion CO₂e output rate and generation mix; location-based Scope 2 accounting |
| **NERC 2025 Long-Term Reliability Assessment** | Resource-adequacy category by assessment area (published Jan 2026; horizon 2026–2035) |
| **WRI Aqueduct 4.0** | Sub-basin baseline water stress (Kuzma et al., 2023) |
| **U.S. Drought Monitor** | Weekly categorical drought and 5-year county DSCI climatology |
| **EJScreen 2.32** | Community-restored pollution indicators, including the RSEI-modeled toxics field |
| **CDC PLACES 2024** | Tract-level health prevalence |
| **ACS 2019–2023** | Tract socioeconomic characteristics |
| **EPA FRS** | Regulated facility proximity |
| **FEMA National Flood Hazard Layer** | Special Flood Hazard Area screening |
| **USFWS National Wetlands Inventory** | Wetland presence screening |
| **ASCE 7-16** (via USGS) | Seismic design parameters |
| **The Green Grid** | PUE, WUE, and CUE definitions for the mechanical overlay |

### GHG Protocol context

Grid carbon is reported as an **annual-average, location-based** emission factor. This is
the location-based method under the GHG Protocol Scope 2 Guidance. Marginal and
hourly-matched emissions are not modelled; the advisory output distinguishes 24/7
carbon-free and hourly-matched PPAs from annual unbundled RECs where that distinction
governs the mitigation.

### Declared exclusions

`data_catalog.json` carries a `not_ingested` block naming streams a reader might reasonably
assume are present but which are not, and the sync logs them on every run:

- **USGS NWIS real-time gauge hydrology** — the dynamic water signal is USDM drought, not
  streamflow
- **EIA-930 hourly balancing-authority data** — the grid pillar is annual-average eGRID
  plus categorical NERC; hourly and marginal emissions remain a v2 item
- **TRI release tonnage** — toxics burden enters through EJScreen's RSEI-modeled field, not
  raw TRI reporting

---

## 3. Technical Methodology & Mathematical Framework

### Architecture

Static-state architecture deployed on GitHub Pages at zero hosting cost, with all screening
computation either precomputed into committed artifacts or run client-side.

```
[User address] ──> Geocoding pipeline (OpenStreetMap → FCC point-in-polygon)
        │
        ▼
[Spatial edge verification]     150 m adjacent-tract boundary buffer (Census TIGERweb)
        │
        ▼
[Decentralized data chunking]   47 per-state JSON chunks (335 KB total; 69 KB largest)
        │
        ▼
[Pillar scoring]                water · grid · burden  →  0–100 each
        │
        ▼
[Tier assignment]  +  [Advisory brief]  +  [Constraint screen]  +  [Mechanical overlay]
```

### Water stress pillar

Three sub-signals with distinct time horizons, blended on documented weights (sensitivity
analysis in `docs/METHODOLOGY.md` §6):

```
S_water = 0.50 · structural + 0.30 · chronic + 0.20 · current
```

- **structural (50%)** — Aqueduct 4.0 baseline water stress, the long-run demand/supply
  balance of the sub-basin. Categorical mapping to score:

  | Aqueduct category | Score |
  |---|---|
  | −1 (Arid & low water use) | 85 |
  | 0 | 5 |
  | 1 | 25 |
  | 2 | 50 |
  | 3 | 75 |
  | 4 | 95 |

  Category −1 scores 85, not 5. Absolute availability is minimal even where current use is
  low, and a new large withdrawal changes that arithmetic.

- **chronic (30%)** — 5-year mean county DSCI, capturing recurring drought pressure not
  present in the Aqueduct baseline vintage
- **current (20%)** — this week's USDM category; transient, but it is the screening trigger
  regulators and journalists reach for first

Site demand context (modeled draw versus county public supply) deliberately does **not**
enter the score, because it depends on user-supplied MW. It can escalate the overall tier.

### Grid strain and carbon pillar

```
S_grid = 0.60 · carbon + 0.40 · strain
```

- **carbon (60%)** — eGRID subregion CO₂e output-rate percentile across all U.S. subregions
- **strain (40%)** — NERC LTRA resource-adequacy category: high = 90, elevated = 55,
  normal = 10

Load share (modeled load versus subregion net generation) is reported and can escalate the
tier, but is not in the score.

### Demand model

```
E_IT      = MW_IT × 1000 × 8760 × utilization          [MWh/yr]
E_facility = E_IT × PUE                                 [MWh/yr]
W_direct  = E_IT × 1000 × WUE                           [L/yr]
W_MGD     = W_direct × 0.264172 / 10⁶ / 365             [MGD]
CO₂e      = E_facility × rate / 2204.62                 [tonnes/yr]
```

WUE is applied per **IT kWh**, matching The Green Grid definition. Indirect
(thermoelectric) generation water is estimated separately using Macknick et al. withdrawal
and consumption factors against the subregion fuel mix, and is reported apart from on-site
cooling water.

### Spatial handling

Boundary proximity is measured against real TIGERweb polygons in an **azimuthal-equidistant
projection centred on the queried point**. Degrees are never compared to metres. If an
address falls within **150 m** of an adjacent census tract, the interface raises a
boundary-proximity badge, because a tract-level score is not reliable at the edge.

An unreachable constraint service reports **unscreened**, never "clear".

### Mechanical configuration overlay

Evaporative, closed-loop air chiller, and direct-liquid cooling configurations, with PUE,
WUE, and CUE computed per The Green Grid definitions (CUE derived from the eGRID subregion
rate). The overlay adjusts the **project's demand** and leaves the location pillars
untouched: a chiller specification does not make an over-allocated basin less
over-allocated.

Zero Liquid Discharge is identified as a **discharge control, not a cooling method**, with
its energy and carbon penalty flagged. The stated objective of the water advisory is
reducing withdrawal below permitting thresholds on engineering merit — never circumventing
them.

### Model limitations and physical assumptions

- **Census tract is the burden geography.** Sub-tract variation is not resolved, and
  boundary-adjacent addresses are flagged rather than silently scored.
- **Aqueduct's 1979–2019 baseline** is treated as the structural signal and is not adjusted
  for recent hydrology.
- **eGRID rates are annual-average and location-based**, not marginal or hourly-matched.
- **Pillar weights are fixed and documented.** They are a stated engineering judgment, with
  the sensitivity analysis in `docs/METHODOLOGY.md` §6.
- **Demand modelling depends on user-supplied IT MW** and a fixed utilization assumption
  across all 8,760 h/yr.
- **NERC categories are ordinal**, mapped to scores on a documented ladder; the mapping is
  not a continuous risk measure.

### Verification

A **450-test pytest suite**, all passing.

- **Idempotency locks.** Successive sync cycles produce exactly zero writes unless upstream
  data changed, including a test that no committed artifact embeds a wall-clock timestamp.
- **Mathematical boundary controls.** Stateless pure functions (`clamp`, band ladders,
  weighted blends, coordinate validation) are tested against null, NaN, ±inf,
  out-of-range, and non-U.S. inputs, and against JSON-serializability — a NaN score
  serializes to an invalid token and takes down the client that reads it.
- **Citation alignment** (`tests/test_citation_alignment.py`). Scans every `src/**/*.py`
  and `docs/*.md` and fails the build if a superseded publication date, non-canonical URL,
  or misaligned horizon reappears.
- **Architectural boundaries.** No scoring module may import the density, sync, news,
  hazard, utility, or mechanical-overlay layers, so an unattended job can never move a
  published score.
- **Provenance enforcement** (`tests/test_provenance.py`). Every emitted value carries a
  source, vintage, and confidence.

`data_catalog.json` is generated from `sources/versioning.py` and never hand-edited; CI
fails the build if the committed copy drifts from the code.

---

## 4. Data Schema & Engineering Units

### Sources ingested

| Pillar | Sources |
|---|---|
| **Water stress** | WRI Aqueduct 4.0 baseline water stress (sub-basin); U.S. Drought Monitor weekly map and 5-year county DSCI climatology; USGS county water-use denominators (2015 compilation, unscored demand context) |
| **Grid strain & carbon** | EPA eGRID2023 rev.2 subregion CO₂e output rate and fuel mix; NERC 2025 LTRA |
| **Community burden** | ACS 2019–2023 tract socioeconomics; CDC PLACES 2024 health prevalence; EPA FRS facility proximity; EJScreen 2.32 restored pollution indicators |
| **Constraints** | FEMA NFHL; USFWS NWI; USGS ASCE 7-16 seismic |
| **Facilities** | OpenStreetMap via Overpass (3-mirror rotation) |
| **Capacity (optional)** | EIA v2, key-gated; skips cleanly when unset. Every other source is keyless. |

### Variables and units

| Variable | Definition | Units |
|---|---|---|
| `bws_raw` | Aqueduct baseline water stress | withdrawals ÷ renewable supply (dimensionless) |
| `bws_cat` | Aqueduct stress category | ordinal, −1 to 4 |
| `dsci_mean` | 5-year mean Drought Severity and Coverage Index | dimensionless, 0–500 |
| `d_cat` | Current USDM drought category | ordinal, 0–4 (D0–D4) |
| `county_public_supply_mgd` | County public-supply withdrawals | MGD |
| `water_mgd` | Modeled facility direct water draw | MGD |
| `water_mgal_yr` | Modeled facility direct water draw | Mgal/yr |
| `pct_county_public_supply` | Facility draw ÷ county public supply | % |
| `co2e_lb_per_mwh` | eGRID subregion annual output emission rate | lb CO₂e/MWh |
| `rate_percentile` | National percentile of that rate | 0–100 |
| `fossil_share_pct` | Fossil generation share of subregion mix | % |
| `carbon_free_share_pct` | Carbon-free generation share | % |
| `subregion_net_gen_mwh` | Subregion annual net generation | MWh/yr |
| `it_mw` | IT (server) load, excluding cooling overhead | MW |
| `facility_energy_mwh_yr` | Total facility energy | MWh/yr |
| `co2e_tonnes_yr` | Modeled facility emissions | tonnes CO₂e/yr |
| `pue` | Power Usage Effectiveness | dimensionless |
| `wue_l_per_kwh_it` | Water Usage Effectiveness | L/kWh (IT) |
| `cue` | Carbon Usage Effectiveness | kg CO₂e/kWh (IT) |
| `load_share_pct` | Facility load ÷ subregion net generation | % |
| `pillar score` | Water / grid / burden pressure | 0–100, higher = more pressure |
| `percentile` | National percentile of an indicator | 0–100 |
| `z-score` | Standardized indicator value | σ from national mean |
| `boundary_distance_m` | Distance to nearest adjacent tract edge | m |

Scores are oriented so that **higher always means more environmental pressure**.

### Output presentation

A dual-view controller (ARIA tablist) toggles between a **Public Summary** (three-tier
Low/Moderate/High) and a **Consultant Analytics** matrix carrying raw values, national
percentiles, z-scores, and explicit μ±1σ bounds. One computation, two presentations;
toggling re-renders from cache without refetching.

Above a 70/100 breach the engine emits screening-level engineering and permitting review
items rather than raw indicator values.

---

## 5. Verification & Reproduction Instructions

### Requirements

Python 3.11 or later. All sources are keyless except the optional EIA capacity layer.

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Run the test suite

```bash
.venv/bin/pytest -q
```

Expected: **450 passing**.

Targeted suites:

```bash
.venv/bin/pytest tests/test_scoring.py -v            # pillar math
.venv/bin/pytest tests/test_normalization.py -v      # boundary controls
.venv/bin/pytest tests/test_provenance.py -v         # per-value provenance
.venv/bin/pytest tests/test_citation_alignment.py -v # citation drift
.venv/bin/pytest tests/test_data_sync.py -v          # idempotency locks
```

Lint:

```bash
.venv/bin/ruff check src tests
```

### Run a screening

```bash
.venv/bin/wattershed screen --address "1600 Pennsylvania Ave NW, Washington, DC"
.venv/bin/wattershed screen --lat 41.6 --lon -93.6 --it-mw 150
```

### Rebuild reference data

```bash
.venv/bin/wattershed data-sync          # refresh sources, commit only on real change
.venv/bin/wattershed build-reference    # rebuild the 85,396-tract national table
.venv/bin/wattershed validate           # verify catalog against versioning.py
```

The GitHub Actions workflow runs the sync on a bi-weekly cron (`0 0 1,15 * *`) plus
`workflow_dispatch`. The pipeline pulls facility footprints from OpenStreetMap via Overpass,
reconciles coordinates to tracts, applies an Infrastructure Density Modifier, scans news
RSS for community-friction terms, and commits only on real change.

### Reproducibility notes

Committed artifacts embed no wall-clock timestamps, enforced by test, so a rebuild against
unchanged upstream data produces a byte-identical result. `data_catalog.json` records the
vintage and retrieval date of every source.

---

## Documentation

| Document | Contents |
|---|---|
| `docs/METHODOLOGY.md` | Full derivation, weights, and §6 sensitivity analysis |
| `docs/DATA_SOURCES.md` | Every source with access notes and vintages |
| `docs/LIMITATIONS.md` | Known limitations and conditions of use |
| `docs/VALIDATION.md` | Ground-truth comparisons |
| `docs/SITING_EQUITY.md` | Cumulative burden methodology |
| `docs/FLAGSHIP_ANALYSIS.md` | Worked analysis of named facilities |
| `data_catalog.json` | Machine-readable source registry (generated, never hand-edited) |

## Disclaimer and license

Provided "as-is" without express or implied warranty. **Screening-level analysis only** —
not an environmental impact assessment, NEPA document, jurisdictional determination, or
engineering due diligence, and must not be represented as one.

© 2026 Chandra Prakash Choudhary. Licensed under the **PolyForm Noncommercial License
1.0.0** — free to read, run, verify, and build on for noncommercial use; commercial rights
reserved. See [LICENSE](LICENSE).

The U.S. Drought Monitor is jointly produced by the National Drought Mitigation Center at
the University of Nebraska-Lincoln, the USDA, and NOAA. Water-risk data: Kuzma et al.
(2023), Aqueduct 4.0, World Resources Institute (CC BY 4.0). Facility locations
© OpenStreetMap contributors (ODbL 1.0).
