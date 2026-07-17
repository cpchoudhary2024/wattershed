# Flagship analysis — ten real U.S. data center sites

Screened 2026-07-17 against live data (USDM map of 2026-07-14; eGRID2023
rev.2; NERC 2025 LTRA; ACS 2019–2023; reference build of 2026-07-16). Every
number below is reproducible: `wattershed screen-all` regenerates the JSON,
`out/reports/<slug>.html` holds each site's full memo with provenance.
Site facts come from `data/curated/sites.yaml` (each fact cited; registry
access date 2026-07-16).

## Results

| Site | State | Status | Water | Grid | Burden | Tier |
|---|---|---|---:|---:|---:|---|
| xAI Colossus 1 | TN | operating | 9 | 40 | **91** | **High** |
| Stargate Site 1 (Abilene) | TX | operating | 55 | 56 | 2 | **High** |
| AWS Project Rainier | IN | operating | 41 | **76** | 48 | **High** |
| Project Blue (Tucson) | AZ | contested | **70** | 22 | 23 | Elevated |
| Google The Dalles | OR | operating | 26 | 52 | **73** | Elevated |
| Google Council Bluffs | IA | operating | 15 | **78** | 42 | Elevated |
| Meta Hyperion | LA | construction | 38 | 58 | 15 | Elevated |
| PW Digital Gateway | VA | rejected (2026-07) | 55 | 47 | 3 | Elevated |
| AWS Susquehanna | PA | operating | 6 | 49 | 1 | Elevated |
| Meta Newton County | GA | operating | 36 | 31 | 26 | Moderate |

## The headline finding

**No two of these fights are the same fight.** The three pillars pull apart
almost perfectly across the set: Memphis is a community-burden case with no
water problem at all (water 9); Abilene is a water-and-grid case with almost
no residents nearby (burden 2); Rainier is a grid case on a coal-heavy,
NERC-High-risk interconnection. A single-number "environmental risk score"
would have flattened exactly the differences that determine what mitigation
is even relevant — which is the empirical justification for the no-composite
design (METHODOLOGY §2).

## Site notes

**xAI Colossus 1 (Memphis) — High, driven by burden 91.** The site parcel is
an unpopulated industrial tract, so the tool scores the 5 km population-
weighted neighborhood (~4,200 residents, 98% people of color, 54%
low-income): combined burden P91, with unemployment P99, adult asthma P97,
RSEI-modeled toxic air releases P95, RMP proximity P92, Superfund proximity
P88, and 23 TRI facilities within 5 km — the live FRS query returns
Electrolux (the site's own former occupant), Nucor Steel, and the Valero
refinery among the neighbors. This is the Boxtown controversy rendered in
percentiles, computed from public data with no editorial input. Notably,
water — the object of most data-center coverage — is a non-issue here
(9/100), while grid strain is moderate (SERC-Central is LTRA-Normal). The
screen says what residents said: the issue is cumulative burden on an
already-overburdened neighborhood.

**Stargate Abilene — High via escalators.** Moderate-looking pillars (55/56)
plus two demand couplings: 1.2 GW ≈ 2.1% of ERCOT-subregion 2023 net
generation on a grid NERC rates High-risk from 2029, in a sub-basin already
at High baseline water stress with severe recent drought climatology. Its
air-cooled design is the mitigating fact — the scenario table shows the
water delta that design choice buys (0.6 vs 21 MGD at evaporative).

**AWS Project Rainier — High on grid.** RFCW's coal-heavy 2023 mix puts the
carbon component at P~67 nationally, and PJM is LTRA-High from 2029; the
2.2 GW load equals ~3.7% of the subregion's current net generation. Burden
(48) is the sleeper: New Carlisle's surrounding tracts are not high-burden,
but the wetlands enforcement history in the curated notes is a reminder that
screening pillars don't exhaust the environmental questions.

**Project Blue (Tucson) — the water case.** Sub-basin "Extremely high"
baseline stress scores 85 under the arid-and-low-water-use rule
(METHODOLOGY §3) plus chronic Southwestern drought → water 70 with **no**
demand model at all (reported load figures conflict, so the registry leaves
MW null — the tool screens on location alone). The 2025–26 history (county
approval, unanimous city rejection, Amazon's exit, revised air-cooled
proposal on ~31 Mgal/yr groundwater permits) is the strongest external
validation in the set: the political system and the screen identified the
same pillar.

**Google The Dalles — the transparency case.** Burden 73 surprises people
who know The Dalles only as "Google's hydro town": the mid-Columbia tract
carries real pollution-proximity and socioeconomic load. Water scores 26 —
the Columbia is not the Southwest — yet this is the site with the most
famous water fight in the industry (a records lawsuit, not a scarcity
crisis; 2025 usage ≈ 40% of city consumption). Screening catches structural
scarcity; it cannot catch institutional opacity. That distinction is stated
rather than hidden.

**Google Council Bluffs — the accounting case.** The set's most instructive
"good site with an asterisk": excellent water position, but grid 78 — 
MISO-West's physical 2023 mix is still coal-heavy and MISO is LTRA-High from
2028. Google's large wind PPAs are real; location-based screening
deliberately doesn't net them (LIMITATIONS §8). Both facts belong in front
of a reviewer at once.

**Meta Hyperion — the scale case.** 5 GW against a small subregion: the
modeled load equals a double-digit share of current SRMV net generation,
which is precisely why ten Meta-funded gas plants are being built. Burden is
low-percentile — Richland Parish's poverty is severe but the *pollution*
domain is thin — a useful demonstration that the multiplicative index
doesn't equate rural poverty with cumulative environmental burden.

**PW Digital Gateway — the counterfactual.** Screened as if proposed:
Elevated (water 55 from Potomac-basin stress + 2025–26 drought history, grid
47 from PJM-High), before any consideration of the battlefield-adjacency
issue that actually killed it in court in July 2026. A useful calibration:
the tool flags real pressure but land-use conflict is out of scope.

**AWS Susquehanna — the contrast case.** Near-floor water and burden, carbon
at nuclear-colocation levels; Elevated rests solely on PJM's adequacy
strain plus the 960 MW load share — which is exactly what the FERC
interconnection fight was about. The screen agrees with FERC's concern, not
with the marketing on either side.

**Meta Newton County — the blind-spot case.** Moderate — the lowest tier in
the set — for the site whose neighbors' wells ran dry. The gap is
instructive and documented: construction-phase groundwater disruption at
parcel scale is invisible to tract-level screening with 2015 county
denominators, and capacity is undisclosed so no demand escalator can fire.
This is the analysis' honest failure exhibit, and it motivates two v2 items
(sub-county groundwater data; construction-phase indicators).

## What the set demonstrates

1. Screening tiers track the real-world outcomes where the outcome had an
   environmental driver (Tucson, Memphis, Susquehanna/FERC), and correctly
   *fail to track* outcomes driven by factors outside scope (PW Gateway's
   procedural/heritage defeat; Newton County's parcel-scale hydrology) — 
   and the tool says which is which.
2. The pillar that dominates coverage (water) is the primary driver at only
   two of ten sites. Grid adequacy — the least-covered pillar — is the most
   frequent driver (four sites). That inversion is the analysis' most
   decision-relevant output.
3. Demand escalators matter: two of three High tiers exist because modeled
   load couples to local context, not because any static pillar crossed 80.
   Screening location without load understates gigawatt-class projects.
