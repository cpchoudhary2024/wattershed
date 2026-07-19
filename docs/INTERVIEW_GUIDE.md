# Presenting Wattershed — defense guide

How to present this project to a technical reviewer at an environmental
consulting firm, and how to answer the questions they will actually ask.
(This is a personal prep document; everything here is drawn from the
methodology and limitations docs — nothing is spin.)

## The 30-second version

> "Data center siting is the most contested environmental-review category in
> the U.S. right now, and the two federal screening tools that covered part
> of it were taken offline in 2025. I built an open replacement that goes
> further: it screens any U.S. location on water stress, grid strain and
> carbon, and cumulative community burden — three pillars, deliberately not
> averaged — with every number traceable to a public source, vintage, and
> retrieval date. It ships with a ten-site analysis of real contested
> projects, and a national atlas of all 3,100 counties that shows the three
> pressures are statistically independent — which is the empirical argument
> against single-score siting indices."

## The live demo (5 minutes, in order)

1. Dashboard → flagship view → click **xAI Memphis**: "burden 91, water 9 —
   the tool says the Boxtown fight is about cumulative burden, not water,
   and here are the P97 asthma and P99 unemployment values behind that."
2. Toggle **National atlas** → water layer → point at the Southwest/Ogallala:
   "every county, from the same reproducible build."
3. Terminal: `wattershed screen --address "<any address>" --mw 200 --cooling air`
   — "any address in America, live keyless data, ~30 seconds."
4. Terminal: `wattershed doctor` — "the tool audits its own data freshness."
5. Open a memo → scroll to the provenance ledger — "every value, sourced and
   dated. This is the property I'd want in anything with my firm's name on it."

## The questions they will ask, and the answers

### The three they will actually probe — say these almost verbatim

**"Why 50/30/20 on the water pillar, and what did you try instead?"**

> "The weights encode time horizon. Structural scarcity gets 50 because
> Aqueduct's baseline demand-to-supply ratio is the only input that describes
> the condition over an asset's 20–30 year life — that's the siting question.
> Chronic drought gets 30: it's the five-year DSCI climatology, which catches
> recurring pressure the Aqueduct baseline vintage misses. Current drought gets
> only 20, deliberately — it's this week's map, it's what triggers the news
> story, but a single wet week shouldn't move a siting decision.
>
> I did test alternatives. I ran equal weighting and a structural-dominant
> 70/20/10, and the sensitivity table in METHODOLOGY.md §6 has the numbers:
> across the flagship set no site changed tier under either variant. That's
> the honest answer — the weights are defensible but the result isn't
> especially sensitive to them, because the pillar is mostly driven by whether
> the sub-basin is structurally stressed at all. Where I'd expect weighting to
> matter is a site with high current drought but low structural stress, and I'd
> want more validation cases before claiming precision there."

Key move: name the alternatives you tested, then volunteer the limitation.

**"Your grid strain comes from NERC assessment areas but your carbon comes
from eGRID subregions. Those aren't the same geography — how do you handle
that?"**

> "They're not, and that's the weakest join in the tool. eGRID subregions are
> emissions-accounting boundaries; NERC assessment areas are reliability
> footprints. I maintain an explicit crosswalk table with a confidence flag on
> every row — high where the mapping is effectively one-to-one, like ERCOT to
> ERCT, and medium where a subregion spans more than one assessment area, like
> the SERC subregions. The confidence flag propagates into the output, so a
> medium-confidence mapping is visible on the report rather than buried.
>
> The honest limitation is that for a site near a boundary, the strain
> component could be attributed to the wrong footprint. The fix is
> balancing-authority-level assignment from EIA-861 service territories, which
> is on the v2 list. For screening, I judged a flagged approximation better
> than dropping resource adequacy entirely — NERC's adequacy finding is often
> the single most decision-relevant fact for a large load."

**"You have demographic data. Why isn't race in the score?"** *(finish this
sentence confidently — hesitation here reads as not having thought it through)*

> "It's a deliberate design choice, and I follow the CEJST precedent. The index
> scores on environmental burden and socioeconomic vulnerability — pollution
> exposure, income, unemployment, education, health outcomes. Race is computed,
> reported on every output, and shown in the memo, but it does not enter the
> arithmetic.
>
> Two reasons. First, legal durability: tools used in permitting contexts face
> challenge, and an index that scores on race directly is more vulnerable than
> one that scores on burden and vulnerability — that's exactly why CEJST was
> built race-neutral in its scoring. Second, it isn't needed for sensitivity:
> Memphis surfaces at the 91st percentile on pollution and socioeconomic
> indicators alone, in a tract that's 97% people of color. The screen finds
> the community without scoring race.
>
> I'll also say what's uncomfortable about that choice, because it's a real
> debate: CalEnviroScreen made the same call and critics argue it understates
> explicitly racialized siting patterns, since redlining's effects don't fully
> reduce to income. That's a legitimate critique. My answer is to report race
> prominently so the user sees it, rather than either scoring it or hiding it —
> but if a client's mandate required a race-inclusive index, the architecture
> supports adding it as a fourth domain, and I'd want that to be an explicit,
> documented decision rather than a silent default."

---

**"Why no single composite score?"**
Because the three harms are incommensurable, and a weighted average lets a
good grid score silently buy down a severe community-burden score — the
masking failure the cumulative-impact literature (and EPA's own EJScreen
design) warns about. Empirically, my national atlas shows the three pillars
correlate at |r| ≤ 0.16 — averaging them would destroy nearly all the
information. Instead I use transparent trigger rules, like CEJST's
threshold logic, and publish the thresholds so they're testable.

**"Why is race reported but not scored?"**
I follow CEJST's approach: the index scores on environmental and
socioeconomic measures, which is both the legally robust choice for
tools used in permitting contexts and sufficient — burden and demographics
correlate strongly enough that the screen still surfaces EJ communities
(Memphis: 98% people of color, found via pollution + income + health).
But I report the demographics on every output, because hiding them would
be its own editorial choice. I can argue both sides of this design
decision — CalEnviroScreen made the same call; critics note it can
understate racialized siting patterns.

**"Average or marginal emissions?"**
Average (eGRID location-based), disclosed as such. Marginal is the better
measure of incremental impact but no freely redistributable marginal
surface exists, and a screening tool that silently mixes licensing-
restricted data isn't reproducible. The limitation is documented, it
systematically *understates* impact on gas-margin grids, and marginal is
the #1 roadmap item.

**"Your water denominators are from 2015. Isn't that disqualifying?"**
It's the most recent complete county water-use census that exists — USGS
discontinued the compilation. I use it only as unscored context, flagged
MEDIUM confidence, and the memo prints the vintage beside the number. The
alternative — silently interpolating — is worse. Sub-county groundwater
data is on the roadmap.

**"How do you know the numbers are right?"** *(different from "is the tool
valid" — this one is about arithmetic correctness, and you have a real answer)*

> "I hand-verified three pillar scores against the raw sources, independently
> of the tool's own code — recomputing the grid pillar from the eGRID workbook
> and the NERC table, the water pillar from the Aqueduct polygon and the USDM
> county history, and the burden pillar from the tract parquet. All three match
> to two decimals. Then I froze those checks as regression tests
> (`tests/test_ground_truth.py`) so a silent join error or a shifted source
> column fails CI instead of shipping.
>
> That verification also caught a real defect: on the Memphis site the burden
> score rests on a single populated tract, because the parcel sits in an
> unpopulated industrial tract and the 5 km neighborhood only picks up one
> residential tract. The arithmetic was correct but the report was displaying a
> tract count that overstated the basis. I fixed the count, made the output
> state the basis explicitly, and added an automatic robustness check — at
> 10 km it's twelve tracts and 43,811 residents and the score moves from 91 to
> 92, so the finding holds. That's now printed on the memo itself."

Volunteering a defect you found and fixed is the single strongest credibility
move available to you. Use it.

**"How do you know the tool is valid?"**
I know precisely how far it's validated, which is different: the flagship
set shows tiers tracking real outcomes where the driver was environmental
(Tucson's water rejection, Memphis's burden fight, the FERC adequacy
dispute at Susquehanna) and *not* tracking outcomes driven by out-of-scope
factors (a battlefield-heritage lawsuit; parcel-scale well interference —
which I document as a named blind spot). Full validation against a few
hundred permitting outcomes is the roadmap's biggest item, and I'd love to
do it with your data.

**"What would you do differently at a firm?"**
QA/QC sign-off chain, a second reviewer on the crosswalk tables,
client-configurable weights with the sensitivity table auto-generated per
engagement, and marginal emissions under a proper license. The
architecture anticipates all four.

## What never to say

- Don't claim it replaces due diligence, NEPA work, or hydro studies — the
  tool's own footer disclaims this, and so should you.
- Don't call the curated registry "a database of U.S. data centers" — it's
  ten hand-verified case studies.
- Don't present modeled demand as measurement. The word is "modeled,"
  every time.
