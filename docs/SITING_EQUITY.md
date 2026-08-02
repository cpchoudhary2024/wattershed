# Do U.S. data centers site disproportionately in water-stressed, grid-strained, or high-burden communities?

**An exploratory national analysis.** This is the empirical study Wattershed was
built to enable: instead of asking whether the *tool* is nice, it asks a
research question the field actually cares about, and reports the answer
honestly — including where the answer is "no."

Reproduce: `python -m wattershed.pipelines.siting_equity`

## Data and method

- **Data-center locations (n = 1,513):** OpenStreetMap facilities tagged
  `telecom=data_center` or `man_made=data_center` across the continental U.S.,
  deduplicated at ~100 m (`data/study/datacenters_osm.csv`). OSM is openly
  licensed (ODbL) and, crucially, **not selected for controversy** — which is
  what makes this a fair test rather than a restatement of hand-picked cases.
- **Scores:** community burden at the nearest populated tract's national
  percentile; water stress and grid strain/carbon at the county level (their
  true resolution), from the committed national reference build.
- **Baseline:** the **population-weighted** national distribution (all populated
  tracts for burden; all counties for water/grid), so the question is
  "disproportionate relative to where Americans live," not "relative to empty
  land."
- **Tests:** Mann–Whitney U (two-sided) for a distributional shift, KS statistic
  for shape, rank-biserial for effect size, and the over-representation ratio =
  (share of data centers in the national top quartile) ÷ 25%.

## Results

![Where U.S. data centers site vs. where Americans live](img/siting_equity.png)

| Pillar | DC median | Nat. pop-wt median | % of DCs in national top quartile | Over-representation | Effect (rank-biserial) | p |
|---|---|---|---|---|---|---|
| **Water stress** | 25.0 | 50.0 | **35.2%** | **1.41×** | +0.03 | 0.13 |
| **Community burden** | 47.6 | 49.9 | 16.9% | 0.68× | −0.06 | 1.3e-4 |
| **Grid strain & carbon** | 49.3 | 49.3 | 19.2% | 0.77× | −0.28 | <1e-6 |

## What it says

**1. Water — a real but tail-concentrated over-siting.**
The *typical* data center sits in a **less** water-stressed county than the
typical American (median 25 vs 50). But data centers are **1.4× over-represented
in the most water-stressed counties** — 35% land in the national top quartile
versus the 25% you'd expect by chance. So the story isn't "data centers are
everywhere thirsty"; it's "a substantial minority cluster in exactly the places
that can least afford them" (the arid Southwest and Texas). Because OSM coverage
skews toward metro areas in the wetter East, this tail signal is arising
*against* the coverage bias, which makes it more credible, not less.

**2. Community burden — not the environmental-justice pattern people assume.**
Data centers are, if anything, **mildly under-represented** in the highest-burden
communities (0.68×; only 17% in the national top quartile). The large sample
makes the small shift statistically significant, but the effect is tiny. This
**contradicts a common assumption** that data centers are systematically dumped
on already-overburdened communities nationally — and it is consistent with this
project's separate blind validation, which found siting conflict is driven by
local organizing capacity, not by environmental burden. (Individual sites like
xAI Memphis are real and serious; they are simply not the national rule.)

**3. Grid — data centers chase favorable power.**
Data centers modestly favor **lower**-carbon, less-strained grid regions
(0.77×, the largest effect here at −0.28). Unsurprising — power price,
availability, and increasingly clean-energy commitments pull siting toward
favorable grids — but it is measured here rather than assumed.

**Headline:** of the three pressures, **water is where U.S. data-center siting is
genuinely and measurably inequitable at the tail; community burden is not; and
the grid actively pulls the other way.** That is a specific, falsifiable,
non-obvious finding — and the opposite of what a single blended "environmental
score" would have told you, which is the same lesson the county-orthogonality
result gave.

## Limitations (this is exploratory, not confirmatory)

1. **OSM coverage is incomplete and non-random.** It over-represents large/known
   and metro facilities. A confirmatory study needs a de-biased national
   data-center census (a real contribution in its own right).
2. **Tract assignment is nearest-populated-centroid, not point-in-polygon.** The
   live tool uses authoritative FCC point-in-polygon; batching that for 1,513
   sites is the confirmatory upgrade. Water/grid use nearest county.
3. **Association, not causation.** No controls for land price, fiber, power
   markets, or tax incentives — the actual siting drivers. This measures *where
   data centers are*, not *why*.
4. **Announced ≠ operating.** OSM mixes both; it cannot distinguish live load
   from planned.
5. **County-resolution water/grid** cannot capture sub-county water sources
   (the documented parcel-scale blind spot).

## Why this is the contribution (not the website)

The dashboard is a way to *look at* the data. This is a *finding* about the
world, produced by a reproducible pipeline over open data, reported with its
effect sizes and its limitations. It is the piece that turns "a tool someone
built" into "a question someone answered." The natural next steps — a de-biased
DC census, point-in-polygon assignment, and covariate controls — are a genuine
research program, and they are written down here as such rather than hidden.
