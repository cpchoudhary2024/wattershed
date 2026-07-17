# Limitations

Read this before quoting any number. Every item below also surfaces in the
tool's own output where it applies — a limitation that only lives in
documentation is a limitation half-disclosed.

## Spatial

1. **Tracts describe areas, not parcels.** A screening point inherits its
   containing census tract's profile; a site near a tract boundary can read
   differently than the parcel next door. Curated sites carry a
   `coord_precision` field (address / parcel-adjacent / locality) and
   locality-precision sites get an extra caveat injected into their reports.
2. **Neighborhood membership is centroid-based.** The 5 km "neighborhood"
   aggregates tracts whose *population-weighted centroid* falls in the
   radius — an approximation of true buffer intersection that avoids shipping
   national tract polygons. Dense urban rings are represented well; one large
   rural tract whose centroid falls just outside is not.
3. **Unpopulated industrial tracts** are scored via that neighborhood (the
   mean of percentiles is not itself a true national percentile — flagged in
   output wherever used).

## Temporal

4. **County water-supply denominators are 2015.** That is the most recent
   complete USGS county compilation. Fast-growing counties (several flagship
   counties among them) have materially different withdrawals today; the
   "% of county public supply" line is context, flagged MEDIUM confidence,
   never a scored input.
5. **Five+ pollution indicators are frozen at EJScreen 2.32** (2024 release;
   AirToxScreen 2020 chemistry) because EPA withdrew the tool in Feb 2025.
   They no longer update. Their vintage is printed beside every value.
6. **Aqueduct's baseline is 1979–2019.** Post-2019 aridification (notably in
   the Southwest) is captured only through the USDM components.

## Conceptual

7. **eGRID rates are annual averages, not marginal emissions.** A new load's
   true incremental emissions depend on dispatch order, hour of day, and
   contracted supply; average intensity is the defensible screening proxy and
   systematically *understates* the marginal impact of load added to
   gas-on-the-margin grids. Marginal surfaces (e.g. WattTime-class models)
   are not freely redistributable, so the choice is documented rather than
   silently made.
8. **Market instruments are not netted against the carbon score.** A site
   with firm 24/7 clean PPAs and a site with unbundled RECs read the same in
   this pillar; the difference belongs to due diligence, not screening. The
   report text carries the nuance (see Council Bluffs, Susquehanna).
9. **NERC risk categories are themselves forecasts** built on mid-2025
   industry submissions, and NERC's LTRA has been criticized (e.g. by Grid
   Strategies, 2026) as conservative about supply-side response. We take the
   published category at face value and cite it; we do not re-litigate it.
10. **Announced MW ≠ built MW.** Demand modeling uses announced figures with
    a fixed 0.80 utilization assumption; projects get cancelled, phased, and
    re-scoped (two flagship sites changed announced capacity during this
    project's development window). Announced values carry their citation and
    date in `sites.yaml`.
11. **TRI linkage is a proxy for industrial burden**, not a measure of harm:
    TRI reporters are facilities above reporting thresholds in covered
    sectors. Count-within-5-km treats a small electroplater and a smelter
    identically; RSEI-weighted values (which do weight by toxicity and fate)
    partially compensate inside the pollution domain.
12. **The curated registry is ten sites**, hand-compiled, biased toward
    prominent and contested projects — useful as demonstration and regression
    baseline, meaningless as a census of the industry. Nothing in the
    scoring depends on it; any U.S. point screens identically.

## Operational

13. **Percentiles are computed against all populated U.S. tracts** at
    reference-build time; a rebuild after upstream updates will shift values
    slightly. The committed build's manifest records its date and coverage.
14. **Coordinate geocoding uses the current Census benchmark**; tract
    definitions are 2020-vintage. If Census revises tract geometry
    mid-decade, geocoder and reference table could briefly disagree (the
    tool then reports the gap rather than guessing).
15. **The subregion-rate percentile is unweighted** (each of the 27 eGRID
    subregions counts once, CAMX equal to AKMS). Generation-weighting would
    hide small dirty regions; the choice is documented and one line to
    change.
