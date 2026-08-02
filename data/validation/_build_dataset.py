"""One-time builder: geocode the labeled validation sites via OpenStreetMap
Nominatim and write a STATIC csv with coordinates committed, so the validation
is fully reproducible without any geocoding dependency at analysis time.

Labels follow data/validation/RUBRIC.md and were assigned from the public
sources cited per row, BEFORE any site was scored by Wattershed.
"""
import csv
import time
from pathlib import Path

import requests

OUT = Path(__file__).parent / "sites_labeled.csv"

# (name, operator, "City, State", label, outcome, source)
# contested = documented environmental/land-use opposition (lawsuit, denial,
# withdrawal under pressure, or sustained organized opposition citing impact)
SITES = [
    # ---- contested ----
    ("Diode Ventures — Harper Road", "Diode Ventures", "Peculiar, MO", "contested", "rejected by city council 2024", "jaredwatkins.com/research/datacenter-opposition"),
    ("Provident Realty DC", "Provident Realty", "Chesterton, IN", "contested", "developer withdrew 2024", "jaredwatkins.com/research/datacenter-opposition"),
    ("Roundhouse Digital", "Roundhouse", "Cascade Locks, OR", "contested", "project abandoned", "jaredwatkins.com/research/datacenter-opposition"),
    ("DC Blox Richmond", "DC Blox", "Richmond, VA", "contested", "permit denied", "jaredwatkins.com/research/datacenter-opposition"),
    ("Culpeper Acquisitions DC", "Culpeper Acquisitions", "Culpeper, VA", "contested", "planning commission denial 2024", "jaredwatkins.com/research/datacenter-opposition"),
    ("Amazon Warrenton", "Amazon", "Warrenton, VA", "contested", "litigation since 2023", "jaredwatkins.com/research/datacenter-opposition"),
    ("PW Digital Gateway", "QTS/Compass", "Gainesville, VA", "contested", "rezoning voided; project ended 2026", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Meta Beaver Dam", "Meta", "Beaver Dam, WI", "contested", "transparency lawsuit Dec 2025", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Vantage Port Washington", "Vantage/OpenAI", "Port Washington, WI", "contested", "rate/transparency litigation", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Meta Ida County", "Meta", "Ida Grove, IA", "contested", "water permitting; unpermitted wells fine", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Stokes County DC", "Eagle Rock", "Walnut Cove, NC", "contested", "zoning litigation ongoing", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("DTE Saline Township", "DTE", "Saline, MI", "contested", "NRDC water/air litigation", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("xAI Colossus", "xAI", "Memphis, TN", "contested", "NAACP/SELC air-permit lawsuit", "earthjustice.org/case/xai-illegal-gas-power-plant-data-center-colossus"),
    ("Boulder City DC", "n/a", "Boulder City, NV", "contested", "2,600-signature petition; stalled", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Apex DC", "n/a", "Apex, NC", "contested", "withdrawn by developer", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Project Hutto", "Zydeco", "Hutto, TX", "contested", "rezoning withdrawn 2026", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Project Hazelnut", "n/a", "Hazleton, PA", "contested", "blocked Nov 2025", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Project Taurus", "Raeden", "Colorado Springs, CO", "contested", "fierce backlash; pending", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Stratos", "O'Leary Digital", "Brigham City, UT", "contested", "water permits; scaled back 75%", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Clearbrook DC", "n/a", "Winchester, VA", "contested", "denied 10-0 2026", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("San Marcos Campus", "n/a", "San Marcos, TX", "contested", "zoning denied 5-2 2026", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("New Brunswick DC", "n/a", "New Brunswick, NJ", "contested", "withdrawn; became park 2026", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("Project Sail", "Prologis/Atlas", "Newnan, GA", "contested", "approved 3-2; lawsuit May 2026", "en.wikipedia.org/wiki/Opposition_to_AI_data_centers"),
    ("San Antonio DCs", "Microsoft/others", "San Antonio, TX", "contested", "Clean Air Act challenge 2026", "tpr.org/podcast/the-source/2026-07-27"),
    ("Project Jupiter", "n/a", "Santa Teresa, NM", "contested", "lawsuit over tax rebates", "insideclimatenews.org/news/22072026"),
    ("Imperial Valley DC", "n/a", "El Centro, CA", "contested", "Colorado River water lawsuit", "kpbs.org/news/environment/2026/06/15"),
    ("Project Blue", "Beale Infrastructure", "Tucson, AZ", "contested", "council rejected; Amazon exited", "kjzz.org/the-show/2025-12-09"),
    ("Rock Creek East", "n/a", "Fort Worth, TX", "contested", "tax break withdrawn 2026", "jaredwatkins.com/research/datacenter-opposition"),
    ("St. Albans Township DC", "Vantage", "New Albany, OH", "contested", "township zoning ban", "jaredwatkins.com/research/datacenter-opposition"),
    ("Tract Goodyear", "Tract", "Goodyear, AZ", "contested", "rezoning blocked 2024", "jaredwatkins.com/research/datacenter-opposition"),

    # ---- quiet controls: established campuses (pre-2020), no environmental
    # litigation found in good-faith search. See RUBRIC.md on why absence of
    # coverage biases toward the null, i.e. is conservative. ----
    ("Google Council Bluffs", "Google", "Council Bluffs, IA", "quiet", "operating since 2007", "datacenters.google/locations/iowa"),
    ("Meta Prineville", "Meta", "Prineville, OR", "quiet", "operating since 2011", "datacenterknowledge.com"),
    ("Apple Maiden", "Apple", "Maiden, NC", "quiet", "operating since 2012", "datacenterknowledge.com"),
    ("Meta Forest City", "Meta", "Forest City, NC", "quiet", "operating since 2012", "datacenterknowledge.com"),
    ("Google Lenoir", "Google", "Lenoir, NC", "quiet", "operating since 2009", "datacenterknowledge.com"),
    ("Microsoft Boydton", "Microsoft", "Boydton, VA", "quiet", "operating since 2010", "datacenterknowledge.com"),
    ("Meta Altoona", "Meta", "Altoona, IA", "quiet", "operating since 2014", "datacenterknowledge.com"),
    ("Google Pryor", "Google", "Pryor, OK", "quiet", "operating since 2011", "datacenters.google/locations/oklahoma"),
    ("Meta Los Lunas", "Meta", "Los Lunas, NM", "quiet", "operating since 2018", "datacenterknowledge.com"),
    ("Google Moncks Corner", "Google", "Moncks Corner, SC", "quiet", "operating since 2008", "datacenters.google/locations/south-carolina"),
    ("Microsoft Cheyenne", "Microsoft", "Cheyenne, WY", "quiet", "operating since 2012", "datacenterknowledge.com"),
    ("Meta Papillion", "Meta", "Papillion, NE", "quiet", "operating since 2020", "datacenterknowledge.com"),
    ("Meta Eagle Mountain", "Meta", "Eagle Mountain, UT", "quiet", "operating since 2021", "datacenterknowledge.com"),
    ("Microsoft Mount Pleasant", "Microsoft", "Mount Pleasant, WI", "quiet", "operating since 2023", "datacenterknowledge.com"),
    ("Microsoft West Des Moines", "Microsoft", "West Des Moines, IA", "quiet", "operating since 2014", "datacenterknowledge.com"),
    ("Meta Sandston (Henrico)", "Meta", "Sandston, VA", "quiet", "operating since 2018", "datacenterknowledge.com"),
    ("Meta New Albany", "Meta", "New Albany, OH", "quiet", "operating since 2017 (Meta campus)", "datacenterknowledge.com"),
    ("Google Berkeley County", "Google", "Moncks Corner, SC", "quiet", "operating; dup-guard", "datacenters.google/locations/south-carolina"),
]


def geocode(q: str) -> tuple[float, float]:
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{q}, USA", "format": "json", "limit": 1},
        headers={"User-Agent": "wattershed-validation/0.1 (research)"},
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    if not j:
        raise ValueError(f"no match: {q}")
    return float(j[0]["lat"]), float(j[0]["lon"])


def main():
    seen = set()
    rows = []
    for name, op, loc, label, outcome, src in SITES:
        key = (name, loc)
        if key in seen:
            continue
        seen.add(key)
        try:
            lat, lon = geocode(loc)
            rows.append([name, op, loc, f"{lat:.5f}", f"{lon:.5f}", label, outcome, src])
            print(f"OK  {name:28s} {loc:24s} {lat:.4f},{lon:.4f}  [{label}]")
        except Exception as e:
            print(f"!!  {name:28s} {loc:24s} FAILED: {e}")
        time.sleep(1.1)  # Nominatim courtesy limit
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "operator", "location", "lat", "lon", "label", "outcome", "source"])
        w.writerows(rows)
    n_c = sum(1 for r in rows if r[5] == "contested")
    print(f"\nwrote {len(rows)} sites -> {OUT}  ({n_c} contested, {len(rows)-n_c} quiet)")


if __name__ == "__main__":
    main()
