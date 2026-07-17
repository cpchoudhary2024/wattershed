# Methodology

This document explains every scoring decision in Wattershed, why it was made,
what the alternatives were, and where the method is fragile. It is written to
be checkable: someone who disagrees with a choice should be able to locate it,
change it, and re-run the flagship set in minutes.

## 1. What kind of instrument this is

Wattershed is a **screening tool**, in the specific sense that term carries in
environmental practice (EPA EJScreen used the same word deliberately): it
identifies places where a closer look is warranted, using nationally
consistent data. It does not measure impacts, it does not replace field
studies, hydrogeological modeling, interconnection studies, or NEPA review,
and its outputs should never be quoted without their confidence flags.

Screening tools fail in two directions. A false negative sends a vulnerable
community into a permitting fight without data; a false positive burdens a
defensible project with unearned suspicion. The design choices below — 
percentile framing, coverage floors, rule-based tiers with published
thresholds, provenance on every number — are all attempts to make both
failure modes *visible* rather than to pretend they don't exist.

## 2. Structure: three pillars, no composite

Wattershed reports three pillar scores (0–100, higher = more concern) and an
overall **tier** (Low / Moderate / Elevated / High) assigned by transparent
trigger rules. It deliberately does **not** average the pillars into a single
index.

The reason is well established in the cumulative-impact literature and in the
design history of the federal tools themselves: water scarcity, grid strain,
and community burden are incommensurable. A weighted average lets an
excellent grid score silently buy down a severe community-burden score — the
exact masking failure that critics of composite environmental indices have
documented for years (see OECD/JRC *Handbook on Constructing Composite
Indicators* on compensability; EPA's EJScreen likewise refused to combine
environmental and demographic indicators into one "score" and CEQ's CEJST
used threshold counting rather than weighted addition).

Within a pillar, indicators *are* combined — but only where they measure the
same kind of thing (three water-availability signals; two grid signals; a
pollution domain and a vulnerability domain).

### Tier rules (from `scoring/tiers.py`, testable)

| Tier | Trigger |
|---|---|
| High | any pillar ≥ 80 · or one ≥ 70 with a second ≥ 55 · or an escalator fires on an Elevated base |
| Elevated | any pillar ≥ 60 · or two pillars ≥ 45 · or an escalator fires on a Moderate base |
| Moderate | any pillar ≥ 35 |
| Low | none of the above |

**Escalators** couple modeled project demand to local context (one step up,
never past High, and only when the relevant pillar is already ≥ 45):

- modeled cooling draw ≥ 2% of county public-supply withdrawals (site's
  documented cooling design; the evaporative hypothetical is used only when
  the design is undisclosed, and is labeled as such);
- modeled facility load ≥ 1% of the eGRID subregion's annual net generation.

The 2%/1% thresholds are judgment calls, chosen because shares at that level
are the ones that have historically forced infrastructure responses (new
wells, new plants) rather than being absorbed quietly. They are constants in
one file, and the sensitivity section below reports what happens when the
weighting around them moves.

## 3. Water-stress pillar

Three signals with different time constants, blended 50/30/20:

| Component | Weight | Source | Why it's here |
|---|---|---|---|
| Structural scarcity | 0.5 | WRI Aqueduct 4.0 baseline water stress (withdrawals ÷ renewable supply, sub-basin, 1979–2019 baseline) | The long-run supply/demand balance — the dominant siting consideration and the industry-standard metric (the same layer consultants and the "two-thirds of new data centers are in drought areas" analyses use) |
| Chronic drought | 0.3 | 5-year mean county DSCI from U.S. Drought Monitor weekly history | Recent climate reality that a 1979–2019 baseline can't see; DSCI is NDMC's own aggregation metric (0–500) |
| Current drought | 0.2 | This week's USDM category at the point | The transient trigger that dominates headlines; weighted lowest *because* it is transient — a wet week must not launder a desert site |

Mappings: Aqueduct categories map to {Low 5, Low-Med 25, Med-High 50,
High 75, Extremely High 95}; **"Arid & low water use" maps to 85**, not to a
low score — the category means current human use is small *because there is
little water*; a gigawatt campus changes that arithmetic. This is exactly the
category Project Blue (Tucson) falls in, and scoring it low would reproduce
the mistake that siting fight is about. DSCI scales linearly to 0–100
(mean DSCI/5); current category maps {none 0, D0 20, D1 40, D2 60, D3 80,
D4 100}.

Weights are renormalized over available components, and every missing
component is reported as an explicit data gap.

**What is NOT in the water score:** modeled site demand (it depends on
user-supplied MW, so it acts as tier escalator and context line, not score);
water rights, source type (groundwater vs surface vs reclaimed), and utility
contracts — all parcel-specific facts a screening tool cannot know. They are
listed in each report's limitations.

## 4. Grid strain & carbon pillar

Two signals, blended 60/40:

| Component | Weight | Source | Notes |
|---|---|---|---|
| Carbon intensity | 0.6 | eGRID2023 (rev.2) subregion CO₂e output rate, expressed as the percentile across all U.S. subregions | Annual average, location-based accounting. **Not** marginal emissions — the honest screening-grade choice; the difference is documented in LIMITATIONS.md |
| Resource-adequacy strain | 0.4 | NERC 2025 Long-Term Reliability Assessment risk category for the mapped assessment area (High 90 / Elevated 55 / Normal 10) | The 2025 LTRA names data-center growth as the dominant demand driver, which makes it the most defensible public strain metric available |

eGRID subregions map to NERC assessment areas through a hand-maintained
crosswalk (`data/reference/egrid_subregion_map.csv`). Imperfect mappings
(e.g. SRVC spans PJM-Virginia and the Carolinas) carry a `medium` confidence
flag that propagates into reports, and curated sites can pin their true RTO
from public record (e.g. Northern Virginia → PJM).

Market instruments (RECs, PPAs) deliberately do not modify the carbon
component: the score describes the physical grid the load sits on
(location-based accounting). Council Bluffs in the flagship set is the
illustrative case — Google's wind PPAs are real and laudable, and the
MISO-West physical mix is still coal-heavy; both statements appear in the
report, in their correct registers. Nuclear colocation (Susquehanna) shows
the same discipline in the opposite direction.

## 5. Cumulative community-burden pillar

A CalEnviroScreen-style multiplicative index rebuilt at tract level from
primary sources, necessitated by EPA's February 2025 withdrawal of EJScreen
and CEQ's takedown of CEJST:

- **Pollution domain (P)** — mean national percentile over up to 10
  indicators: PM2.5, ozone, NO₂, diesel PM, RSEI-modeled toxic air releases,
  traffic proximity, NPL proximity, RMP proximity, TSDF proximity (all from
  the community-restored EJScreen 2.32 final release, vintage-frozen and
  flagged) + live TRI facility density within 5 km (rebuilt from EPA FRS at
  reference-build time).
- **Vulnerability domain (V)** — mean national percentile over up to 6
  indicators: % low-income (<2× poverty), unemployment, limited-English
  households, adults without HS diploma (ACS 2019–2023 bulk files), adult
  asthma, fair/poor self-rated health (CDC PLACES 2024).
- **CBI = P × V / 100**, ranked against all 85,396 U.S. tracts; the pillar
  score is that national percentile.

**Why multiplicative:** the cumulative-impact premise is that pollution
landing on a vulnerable population is categorically worse than either alone.
An additive form treats a pristine-but-poor tract and a polluted-but-affluent
tract as equivalent; the product does not. This mirrors CalEnviroScreen 4.0,
the longest-standing regulatory cumulative index in the U.S.

**Race is reported, not scored.** Reports show % people of color for
transparency (it is central to how communities themselves describe these
fights), but the index scores on environmental and socioeconomic measures
only — following CEJST's approach. Both the legal robustness rationale and
the critique of that choice are real; the report surfaces the data either
way so no reader is deprived of it.

**Coverage floors:** a domain is only computed from ≥5 (pollution) / ≥4
(vulnerability) present indicators. Below the floor the pillar reports
"insufficient data" rather than a number synthesized from scraps.

**Unpopulated industrial tracts:** special-use tracts (population ≈ 0) carry
no percentile ranks — correctly, since there is no resident population to
rank. When a site lands in one (xAI Memphis does), burden is scored over the
5 km population-weighted neighborhood instead, clearly labeled, because the
people the question is about live *around* the parcel. The neighborhood mean
of percentiles is an approximation and is flagged as such.

## 6. Demand model

`MW → energy → water → CO₂e`, from published factors, always presented as a
scenario table (never one number):

- Energy: announced IT MW × 8760 h × 0.80 utilization; facility energy = IT
  energy × PUE.
- PUE / site WUE by cooling family (LBNL 2024 *U.S. Data Center Energy Usage
  Report* ranges): evaporative 1.20 / 1.8 L·kWh⁻¹(IT); hybrid 1.25 / 0.6;
  air 1.35 / 0.05.
- Indirect (generation) water: eGRID subregion fuel mix × Macknick et al.
  (2012) median consumption factors; hydropower reservoir evaporation
  excluded (contested attribution), coverage share reported.
- CO₂e: facility MWh × subregion output rate (location-based).
- Context denominators: USGS 2015 county public-supply withdrawals (latest
  complete county compilation — vintage flagged on every use); eGRID2023
  subregion net generation.

## 7. Sensitivity: what moves when the weights move

Computed on the 10-site flagship set (all shifts are single-step; nothing
jumps two tiers):

| Perturbation | Tier changes (of 10) |
|---|---|
| Water 0.5/0.3/0.2 → 0.4/0.4/0.2 | 1 (Meta Newton Moderate→Low) |
| Water → 0.7/0.2/0.1 | 1 (Project Blue Elevated→High) |
| Grid 0.6/0.4 → 0.5/0.5 | 3 (The Dalles, Council Bluffs, Hyperion each Elevated→High) |
| Grid → 0.8/0.2 | 3 (Stargate High→Elevated; PW Gateway, Susquehanna one step down) |

Reading: the water blend is robust to ±0.2 reweighting. The grid pillar is
the sensitivity hot-spot — specifically the carbon-vs-strain balance — which
is honest, because "how much should looming resource-adequacy shortfalls
count against a clean-ish grid?" is a genuine policy question, not a data
question. The 60/40 default reflects that carbon intensity is a measured
quantity while the strain category is itself an assessment; users who weight
reliability higher can change one constant and re-run.

## 8. Known methodological debts

Carried openly (see LIMITATIONS.md for the full list): average-vs-marginal
emissions; 2015 water denominators; frozen EJScreen pollution fields;
centroid-based neighborhood membership; unweighted subregion rate
percentiles; announced-MW ≠ built-MW. Each has a planned v2 remedy in
SELF_ASSESSMENT.md.
