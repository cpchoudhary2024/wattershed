# Wattershed

> **Automated neighborhood-level environmental suitability and predictive risk-mitigation screening engine for U.S. data center infrastructure deployment.**

[![Tests](https://img.shields.io/badge/pytest-450%20passing-0b6e2e)](#-comprehensive-quality-assurance--testing)
[![Data sync](https://img.shields.io/badge/data%20sync-bi--weekly-475569)](.github/workflows/data_sync.yml)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-475569)](LICENSE)

**▶ Live tool:** https://cpchoudhary2024.github.io/wattershed/

---

## 💡 Executive Summary & Portfolio Context

**Engineered by:** Chandra Prakash Choudhary
**Candidate:** Master of Science in Geography & Environmental Engineering
**Institution:** Department of Environmental Health and Engineering, Johns Hopkins University
**Profile:** https://www.linkedin.com/in/chandra-prakash-choudhary/

*Institutional affiliation is listed for identification and portfolio verification only. This application represents independent engineering research and tool development, and is not affiliated with, endorsed by, or an official work product of Johns Hopkins University.*

### The Real-World Problem

Hyperscale AI and cloud data centers consume unprecedented volumes of localized water and electrical capacity. After EPA withdrew **EJScreen** and CEQ withdrew **CEJST** in 2025, developers, researchers and community advocates lost the common, transparent framework they had used to audit cumulative environmental burden at neighborhood scale.

### The Wattershed Solution

Wattershed fills that gap. It is an open-source, serverless screening tool that geocodes any U.S. street address to its exact census tract and evaluates localized pressure against a committed national reference table of **85,396 census tracts**. Beyond a passive mapping dashboard, it includes an **Actionable Technical Advisory Brief** that turns threshold breaches into concrete engineering and permitting review items.

---

## 🛠 Core Technical Architecture & Data Ingestion

Static-state architecture deployed on **GitHub Pages** at `$0/month`, with all screening computation either precomputed into committed artifacts or run client-side.

```
[User search input] ──> Geocoding pipeline (OpenStreetMap → FCC point-in-polygon)
        │
        ▼
[Defensive spatial edge verification]  150 m adjacent-tract boundary buffer (Census TIGERweb)
        │
        ▼
[Decentralized data chunking]          47 per-state JSON chunks (335 KB total; 69 KB largest)
        │
        ▼
[Dual-mode UX controller]              🧩 Public Summary  │  📊 Consultant Analytics
        │
        ▼
[Conditional advisory brief]  +  [Spatial constraint screen]  +  [Mechanical overlay]
```

### Data Provenance & Strict Verifiability (`data_catalog.json`)

Every 0–100 score maps back to an authoritative registry. `data_catalog.json` is **generated from `sources/versioning.py`, never hand-edited**, and CI fails the build if the committed copy drifts from the code.

| Pillar | Sources actually ingested |
|---|---|
| **Water stress** | WRI **Aqueduct 4.0** baseline water stress (sub-basin) + **U.S. Drought Monitor** weekly map and 5-year county DSCI climatology. USGS contributes county water-*use* denominators (2015 compilation) as unscored demand context. |
| **Grid strain & carbon** | EPA **eGRID2023 rev.2** subregion CO₂e output rate and fuel mix + **NERC 2025 Long-Term Reliability Assessment** (published January 2026; horizon 2026–2035). |
| **Community burden** | **ACS 2019–2023** tract socioeconomics + **CDC PLACES 2024** health prevalence + **EPA FRS** facility proximity + **EJScreen 2.32** community-restored pollution indicators. |

**Declared exclusions.** The catalog carries a `not_ingested` block naming streams a reader might reasonably assume are present but which are not, and the sync logs them on every run: **USGS real-time gauge hydrology** (the dynamic water signal is USDM drought, not NWIS streamflow) and **EIA-930 hourly balancing-authority data** (the grid pillar is annual-average eGRID plus categorical NERC; hourly/marginal emissions remain a v2 item). TRI *release* tonnage is likewise not ingested — toxics burden enters through EJScreen's RSEI-modeled field, not raw TRI reporting.

---

## 🌟 Key Innovations

1. **Automated engineering mitigation logic.** Above a 70/100 breach the engine prints screening-level consulting review items rather than raw data:
   * *Water:* evaluate closed-loop air-cooled or hybrid-adiabatic heat rejection and reclaimed/greywater supply agreements; Zero Liquid Discharge is identified as a **discharge control, not a cooling method**, with its energy and carbon penalty flagged. The stated objective is reducing withdrawal below permitting thresholds on engineering merit — never circumventing them.
   * *Grid:* high location-based Scope 2 intensity plus constrained resource adequacy; interconnection cost allocation, on-site storage, and 24/7 carbon-free or hourly-matched PPAs versus annual unbundled RECs.
   * *Community:* upper-tier cumulative burden, where the principal exposure is **permitting and administrative** — state EJ review, Title VI complaints, organized opposition — more often than litigation. Prompts early Community Benefits Agreements and independent local monitoring.
   * Clean Water Act §401/§404 and NEPA are named explicitly as **not screened**: those turn on an aquatic-resource delineation, a jurisdictional determination, and a federal nexus — none of which a pressure score can establish.
2. **Dual-view UX controller.** ARIA-tablist toggle between a **Public Summary** (3-tier Low/Moderate/High) and a **Consultant Analytics** matrix carrying raw values, national percentiles, z-scores and explicit μ±1σ bounds. One computation, two presentations; toggling re-renders from cache without refetching.
3. **Defensive spatial safeguards.** If a queried address falls within **150 m** of an adjacent census tract, the interface raises a boundary-proximity badge. Distance is measured against real TIGERweb polygons in an azimuthal-equidistant projection centred on the point — degrees are never compared to metres.
4. **Spatial constraint screening.** FEMA National Flood Hazard Layer (Special Flood Hazard Area), USFWS National Wetlands Inventory, and USGS ASCE 7-16 seismic design parameters. An unreachable service reports **unscreened**, never "clear".
5. **Mechanical configuration overlay.** Evaporative / closed-loop air chillers / direct-liquid cooling, with **PUE, WUE and CUE** computed per The Green Grid definitions (CUE from the eGRID subregion rate). The overlay adjusts the *project's* demand and leaves the location pillars untouched — a chiller specification does not make an over-allocated basin less over-allocated.
6. **Idempotent DevOps pipeline.** Free GitHub Actions workflow on a bi-weekly cron (`0 0 1,15 * *`) plus `workflow_dispatch`. The **Python** pipeline pulls facility footprints from **OpenStreetMap via Overpass** (3-mirror rotation), reconciles coordinates to tracts, applies an Infrastructure Density Modifier, scans news RSS for community-friction terms, and commits only on real change. EIA v2 is an **optional, key-gated** capacity layer that skips cleanly when no key is set — every other source is keyless.

---

## 🧪 Comprehensive Quality Assurance & Testing

A **450-test `pytest`** suite, all passing.

* **Idempotency locks.** Regression tests ensure successive cycles produce exactly zero writes unless upstream data changed — including a test that no committed artifact embeds a wall-clock timestamp.
* **Mathematical boundary controls.** Stateless pure functions (`clamp`, band ladders, weighted blends, coordinate validation) are tested against null, NaN, ±inf, out-of-range and non-U.S. inputs, and against JSON-serializability — a NaN score serializes to an invalid token and takes down the client that reads it.
* **Citation alignment scans** (`tests/test_citation_alignment.py`). Scans every `src/**/*.py` and `docs/*.md` file and fails the build if a superseded publication date, non-canonical URL, or misaligned horizon reappears.
* **Architectural boundaries.** Tests assert that no scoring module imports the density, sync, news, hazard, utility, or mechanical-overlay layers — so an unattended job can never move a published score.

```bash
# Local validation
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```

---

## 🔒 Professional Liability & Compliance Disclaimer

Independent open-source research tool by Chandra Prakash Choudhary (Johns Hopkins University M.S. candidate). Academic credentials and affiliations are provided strictly for professional identification and context. Provided "as-is" without express or implied warranty. **Screening-level analysis only** — it is not an environmental impact assessment, NEPA document, jurisdictional determination, or engineering due diligence, and must not be represented as one. No official institutional endorsement by Johns Hopkins University is implied.

© 2026 Chandra Prakash Choudhary. Licensed under the **PolyForm Noncommercial License 1.0.0** — free to read, run, verify and build on for noncommercial use; commercial rights reserved. See [LICENSE](LICENSE).

The U.S. Drought Monitor is jointly produced by the National Drought Mitigation Center at the University of Nebraska-Lincoln, the USDA, and NOAA. Water-risk data: Kuzma et al. (2023), Aqueduct 4.0, World Resources Institute (CC BY 4.0). Facility locations © OpenStreetMap contributors (ODbL 1.0).
