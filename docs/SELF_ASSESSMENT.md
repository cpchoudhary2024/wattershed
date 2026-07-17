# Self-assessment

An honest accounting of what this build is and isn't, written the way an
engineer would brief a reviewer who is deciding whether to trust it.

## What is genuinely strong

**The provenance discipline.** Every number in every output traces to a
registered source with provider, vintage, license, and retrieval timestamp —
enforced by structure (an `Indicator` cannot exist without a `source_id`;
CI tests the registry) rather than by diligence. This is the property
consulting reviewers check first and most tools fake.

**Keyless, offline-capable reproducibility.** `git clone` → `pip install`
→ screen any U.S. point, with zero API keys, because the national reference
table (85,396 tracts × 16 indicators), the Aqueduct U.S. extract, and the
TRI facility table are committed with a build manifest — and anyone can
regenerate all three from primary sources with one command and diff the
result. The bulk-ACS route (no Census key even for rebuilds) was a
deliberate find.

**The no-composite scoring architecture.** Three pillars, rule-based tiers
with published thresholds, demand escalators, coverage floors, and a
computed sensitivity table — the methodology takes positions and shows its
arithmetic. The flagship set empirically vindicates the design: the three
pillars separate almost orthogonally across ten real sites.

**Timeliness with resilience.** The tool rebuilds capability the federal
government withdrew in 2025 (EJScreen/CEJST) from primary and
durably-archived sources, and incorporates the January 2026 NERC LTRA — the
first public strain assessment to name data centers as the dominant demand
driver.

**Honesty as a feature.** The unpopulated-industrial-tract fallback, the
"arid & low water use scores high" rule, the labeled evaporative
hypothetical, and the Newton County blind-spot writeup all encode the same
principle: where the method is weak, the output says so in place.

## What is weaker than it looks

- **The grid pillar leans on one categorical input.** NERC's risk category
  carries 40% of the pillar from a hand-transcribed 18-row table. It's the
  best free national strain signal, but it is coarse, annual, and itself a
  contested forecast. The sensitivity analysis shows this is where tier
  assignments are most fragile.
- **Ten curated sites is a demonstration, not a validation.** The
  "tiers track outcomes" claims in the flagship analysis are consistent
  anecdotes, not a validated model. Real validation would score a few
  hundred sites against permitting/opposition outcomes.
- **Burden indicators mix vintages** (ACS 2019–23, PLACES 2022, EJScreen
  2.32/AirToxScreen 2020). Percentile framing softens but does not remove
  cross-vintage comparability issues.
- **Tier thresholds were set by judgment, sanity-checked on the flagship
  set** — a set with no Low-tier member. The thresholds are honest and
  published, but they have not been calibrated against an external
  ground truth.
- **Single-developer surface area.** Nine source integrations, a scoring
  engine, a report renderer, and a dashboard is a lot of surface for the
  test count (28 unit tests + one integrity test). The network layer is
  exercised by reproduction, not CI.

## What v2 would add, in priority order

1. **Marginal-emissions option** for the carbon component (open marginal
   surfaces where licensable), with the average-vs-marginal gap shown
   per-site.
2. **Interconnection-queue analytics** (LBNL Queued Up + ISO queues) as a
   second, quantitative strain signal to dilute the single-source NERC
   dependency.
3. **Sub-county water:** USGS groundwater-level networks and state
   water-rights databases (TX, AZ, GA first) to catch Newton-County-class
   parcel-scale hydrology; construction-phase indicators.
4. **True buffer geometry** (tract polygons via on-demand TIGER state
   fetches) replacing centroid membership; population-weighted buffer
   reports like EJScreen's.
5. **Validation study:** score 300+ sites from public permitting dockets
   against outcomes (approved / conditioned / withdrawn / litigated);
   publish the confusion matrix, recalibrate tier thresholds.
6. **Batch + comparison UX:** `wattershed compare a b c` side-by-side
   memos; CSV batch mode for portfolio screening.
7. **Continuously updated deployment** (weekly GitHub Action: refresh USDM,
   re-screen registry, redeploy dashboard) — the repo is structured for it;
   it just wasn't turned on for v1.

## Bottom line

v1 is a defensible screening instrument with unusually good provenance
hygiene and an unusually honest methodology, demonstrated on a real,
newsworthy case set — and it knows, precisely and in writing, where its
edges are.
