# Validation study — pre-registered design

Written **before** any site was scored, to keep the test honest. The scoring
engine sees only coordinates; it has no access to the outcome label, so scoring
is blind by construction.

## Unit of analysis
A specific, named U.S. data-center campus with a public physical location
(geocodable to a point). One row per campus.

## Outcome label (the thing we are trying to predict)
Binary, assigned from **independent public evidence**, not from the tool:

- **contested** — documented, organized public or legal opposition on
  *environmental* grounds (water, grid/power, air/emissions, or environmental
  justice). Evidence = at least one of: a lawsuit; a permit denial or
  rescission; a formal government rejection of a rezoning/annexation/water
  request; or sustained news coverage of organized community opposition citing
  environmental impact.
- **quiet** — operating or under construction with **no** such documented
  environmental opposition found in a good-faith search.

Each label carries a source URL in `sites_labeled.csv`.

## Hypothesis (directional, pre-registered)
Contested sites have **higher** water, grid, and/or community-burden pillar
scores than quiet sites, and a **higher** overall screening tier. If the data
do not show this, that null result is reported as-is.

## Primary tests
1. Mann–Whitney U (one-sided) on each pillar, contested vs. quiet.
2. AUC (area under ROC) of each pillar, and of the ordinal tier, as a
   classifier of "contested". AUC 0.5 = no signal; higher = the pillar ranks
   contested sites above quiet ones.
3. Tier hit-rate: share of contested sites reaching Elevated/High tier.

## Blinding
`screen_site()` receives latitude/longitude only. Labels live in a separate
file the scorer never reads. Verified in `pipelines/validate.py`.

## Confounds and limitations (disclosed up front)
- **Selection/labeling bias:** sites and labels compiled by the author, not a
  random draw. This is exploratory validation, not a population estimate.
- **"quiet" ≠ truly uncontested:** absence of coverage is not proof of absence
  of opposition. Under-reporting biases toward the null (makes it *harder* to
  see a real signal, not easier).
- **Contestation is multi-causal:** local politics, media presence, and
  developer conduct drive opposition alongside environmental conditions. The
  tool only measures the environmental substrate, so even a true signal will be
  partial by design.
- **Small n:** treat effect sizes as indicative, not precise.
