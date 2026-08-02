# Validation: does the screen predict where siting fights happen?

**Short answer: no — and that null result is the most useful thing this study
produced.** It says something real about how data-center conflict works, and it
sharpens what Wattershed is actually for.

Design was pre-registered in [`data/validation/RUBRIC.md`](../data/validation/RUBRIC.md)
before any site was scored. Reproduce with `python -m wattershed.pipelines.validate`.

## What I tested

I assembled 46 real U.S. data-center sites and labeled each from independent
public sources, **before scoring**:

- **30 "contested"** — documented environmental or land-use opposition (a
  lawsuit, a permit denial, a withdrawal under pressure, or sustained organized
  opposition). Compiled from the Wikipedia "Opposition to AI data centers"
  tracker, Data Center Watch, Earthjustice, and local reporting.
- **16 "quiet"** — established campuses (mostly pre-2020) with no environmental
  opposition found in a good-faith search.

Every site was then screened **blind**: from coordinates only, so no project
scale entered the score (pure location signal). The label was never passed to
the scorer. Hypothesis: contested sites would score higher on water, grid,
and/or burden, and reach a higher tier.

## Result: the screen does not separate the two groups

AUC is the probability the screen ranks a contested site above a quiet one;
0.5 is a coin flip.

| Signal | Contested (mean) | Quiet (mean) | AUC | one-sided p |
|---|---|---|---|---|
| Water stress | 49.9 | 45.4 | 0.55 | 0.28 |
| Grid strain & carbon | 47.3 | 51.1 | 0.44 | 0.74 |
| Community burden | 46.0 | 47.8 | 0.47 | 0.61 |
| Overall tier | 2.1 | 2.1 | 0.53 | 0.35 |

Nothing is significant. Only water leans in the hypothesized direction, weakly
(AUC 0.55), which is at least consistent with water being the most-cited
opposition theme — but I would not claim a signal from it at this sample size.

## Why this happens (the actual finding)

Opposition is **socio-political, not environmental**. The clearest way to see it
is in the extremes of the data:

- The single **most environmentally burdened site in the entire set is a quiet
  one** — Google Council Bluffs, Iowa, community-burden percentile **89** — with
  no organized environmental opposition on record.
- Several **fiercely contested** sites sit in **low-burden, affluent, largely
  suburban** areas: Apex NC (burden **7**), PW Digital Gateway / Gainesville VA
  (**17**), Amazon Warrenton VA (**18**). These fights were about land use,
  noise, traffic, and historic preservation, not cumulative environmental
  burden.

That is the environmental-justice "squeaky wheel" problem, visible in data:
**opposition concentrates where residents have the capacity and standing to
organize, which is often the inverse of where environmental burden is highest.**
The communities a burden screen flags hardest are frequently the ones *least*
able to mount the opposition that would land a project on a contested-sites
list.

## What this means for the tool

It reframes the purpose, and I think correctly:

- Wattershed is **not** a predictor of public opposition, and this study is the
  evidence that it should never be sold as one.
- Its value is the opposite of the political signal: it surfaces environmental
  burden **objectively, everywhere**, including the high-burden communities that
  the opposition map misses entirely. That is exactly the use case for a
  screening tool used by regulators, journalists, and community groups who want
  to look past where the noise already is.

A positive validation would have been a weaker result. It would have meant the
tool merely re-describes the existing political map. The null says the tool sees
something the political process does not.

## Limitations (why this is exploratory, not definitive)

1. **Selection and labeling** were done by one author, not a random draw. This
   is exploratory validation, not a population estimate.
2. **Location-only scoring ignores project scale.** Much opposition tracks
   announced MW (water and power draw), which the blind location screen omits by
   design. A scale-aware test needs per-site MW that is not public for most
   sites.
3. **The quiet controls skew rural** (established hyperscale campuses), which
   raises their grid scores and muddies a clean comparison.
4. **"Quiet" can mean under-reported**, not truly uncontested. That biases
   *toward* the null, so it makes a real signal harder to see, not easier.
5. **n = 46.** Treat every number here as indicative.

## Reproduce

```bash
python -m wattershed.pipelines.validate
# writes data/validation/results.csv and report.json
```

Row-level scores for all 46 sites are in
[`data/validation/results.csv`](../data/validation/results.csv).
