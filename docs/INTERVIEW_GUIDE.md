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

**"How do you know the tool is right?"**
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
