# Launch posts (draft — edit to your voice before posting)

Post the LinkedIn one first. Lead with the finding, not the tech. Link the
**live tool**, not the repo — the repo link belongs in the first comment.

---

## LinkedIn (primary)

> Two data center fights. Same headlines. Completely different problems.
>
> In Memphis, xAI's Colossus became the most-covered data center controversy in
> the country. Most coverage framed it as a water story. It isn't. When I
> screened the site, water stress came back at 9 out of 100 — Memphis sits on
> one of the most abundant aquifers in North America. What came back at 91 was
> cumulative community burden: the surrounding tract ranks in the 95th
> percentile nationally for modeled toxic air releases and the 92nd for
> proximity to chemical-accident facilities, in a community that is 97% people
> of color. The fight there is about who already carries the load — not water.
>
> In Newton County, Georgia, it's the opposite. Residents' wells ran dry next to
> a Meta campus. But that damage happened at the scale of individual
> parcels — and my tool scores that county as moderate, because no public
> dataset resolves groundwater interference at that scale. The screen misses
> it, and I documented that as a known blind spot rather than quietly claiming
> a hit.
>
> No two site fights are the same fight. That's the whole reason I built this.
>
> The two federal tools that used to answer questions like these — EPA's
> EJScreen and CEQ's CEJST — were taken offline in 2025. So I rebuilt the
> capability from primary sources and made it open:
>
> **Wattershed** screens any U.S. location for data center siting pressure
> across three axes — water stress, grid strain and carbon intensity, and
> cumulative community burden — with every value traceable to its source,
> vintage, and retrieval date.
>
> A few things I'd point a technical reader to:
>
> • It refuses to produce a single composite score. I checked whether that
> refusal was justified by scoring all 3,109 U.S. counties: the three pressures
> correlate at |r| ≤ 0.15. They're effectively independent. Averaging them
> would destroy nearly all the information — which is exactly what a one-number
> siting index does.
>
> • I hand-verified the pillar scores against the raw EPA eGRID workbook, WRI
> Aqueduct polygons, and Drought Monitor history, then froze those checks as
> regression tests. That verification caught a real defect in my own output,
> which I fixed and documented.
>
> • It ships a limitations document listing 15 things it cannot see. A
> screening tool that hides its blind spots is worse than no tool.
>
> Live tool (search your own county): https://cpchoudhary2024.github.io/wattershed/
>
> Built as an M.S. Environmental Engineering project at Johns Hopkins. Feedback
> from anyone doing siting, permitting, or EJ analysis is genuinely welcome —
> especially where you think the methodology is wrong.
>
> #EnvironmentalEngineering #DataCenters #WaterResources #EnvironmentalJustice
> #GIS #OpenData

*First comment:* "Source, methodology, and the full 15-item limitations list:
https://github.com/cpchoudhary2024/wattershed"

---

## r/gis (atlas-focused — post the map image)

**Title:** I scored all 3,109 U.S. counties for data center siting pressure
(water / grid / community burden) and the three layers turn out to be
statistically independent

> Built this after EJScreen and CEJST went offline in 2025. Three pillars from
> primary sources: WRI Aqueduct 4.0 baseline water stress, EPA eGRID2023 +
> NERC's 2025 reliability assessment for grid, and a CalEnviroScreen-style
> cumulative burden index I rebuilt at census-tract level (85,396 tracts) from
> ACS, CDC PLACES, and EPA FRS/TRI.
>
> The part I found genuinely interesting: the three pressures barely correlate
> (max |r| = 0.15). The arid Southwest and the Ogallala counties dominate
> water; the coal-heavy eastern Interconnection dominates grid; burden clusters
> in urban-industrial cores, the California Central Valley, and Puerto Rico.
> Almost no overlap. Which means any single-number "environmental score" for
> siting is throwing away most of the signal.
>
> Stack: Python/GeoPandas, everything keyless and reproducible, dashboard is
> dependency-free inline SVG (no tile server, no CDN). Tract centroid
> membership rather than polygon overlay is the main geographic approximation —
> documented.
>
> Live: https://cpchoudhary2024.github.io/wattershed/

---

## Notes on posting

- Post LinkedIn mid-week, morning US Eastern.
- Screenshot the **atlas water layer** for the image — it reads instantly
  (Southwest + High Plains light up).
- If anyone challenges the methodology in comments, engage with the specifics
  and concede real points. That exchange is more persuasive to a lurking
  hiring manager than the post itself.
- Do not claim it replaces due diligence or NEPA work. Screening-level, always.
