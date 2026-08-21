"""Utility / balancing-authority context for large-load concentration.

WHAT THIS DELIBERATELY IS NOT
------------------------------
It is not a ratepayer price forecast. Wattershed holds no rate data: no
tariffs, no rate-case filings, no cost-allocation records, no EIA-861 revenue
series. Producing a "price volatility risk" number from data-centre counts
would be an econometric claim with no econometric input — the kind of figure
that reads as analysis and is actually invention, and it would be the first
thing a utility economist asked to see the inputs for.

What IS supportable from committed data is the physical quantity underneath
the rate debate: how much large load is concentrating in a balancing
authority relative to the generation already there. eGRID gives subregion
annual net generation; the facility registry gives observed data-centre
locations. Their ratio is a concentration indicator, reported as such.

Interpreting it: high concentration is where interconnection queues lengthen,
where capacity costs get allocated, and where rate cases about large-load
cost causation are actually being fought. It indicates WHERE to look. It does
not forecast a price.

Pure module: lookups and arithmetic, no I/O.
"""

from __future__ import annotations

import csv
import logging
from functools import lru_cache

from .. import config
from .normalize import clamp, is_number

log = logging.getLogger("wattershed.utility")

SUBREGION_MAP = config.REFERENCE_DIR / "egrid_subregion_map.csv"

# Assumed campus draw used to express concentration in energy terms. A
# screening-grade stand-in, stated rather than hidden: the registry carries
# locations, not nameplate capacity, so per-site MW is unknown.
ASSUMED_CAMPUS_MW = 60.0
ASSUMED_UTILIZATION = 0.80
HOURS_PER_YEAR = 8760

# Share of a subregion's annual net generation implied by the observed
# campuses in it. 1% is where a single subregion's large-load growth starts
# being a planning topic; 5% is where it dominates the interconnection queue.
CONCENTRATION_NOTABLE = 1.0
CONCENTRATION_HIGH = 5.0


@lru_cache(maxsize=1)
def subregion_to_rto() -> dict[str, dict]:
    """eGRID subregion -> RTO/ISO label and NERC area. Committed, hand-checked."""
    if not SUBREGION_MAP.exists():
        log.warning("utility: %s missing — RTO lookup unavailable", SUBREGION_MAP.name)
        return {}
    out = {}
    with SUBREGION_MAP.open() as fh:
        for row in csv.DictReader(fh):
            out[row["subrgn"]] = {
                "rto": (row.get("rto_label") or "").strip(),
                "nerc_area": (row.get("nerc_area") or "").strip(),
                "map_confidence": (row.get("map_confidence") or "").strip(),
            }
    return out


def operator_for_subregion(subrgn: str) -> dict:
    """Market operator context for a subregion. Pure (reads a cached table).

    Note the resolution honestly: this identifies the RTO/ISO or non-RTO
    market region, NOT the retail utility serving a parcel. Retail service
    territory would require EIA-861, which is not ingested.
    """
    rec = subregion_to_rto().get(str(subrgn or "").strip(), {})
    return {
        "subregion": subrgn,
        "rto": rec.get("rto", ""),
        "nerc_area": rec.get("nerc_area", ""),
        "map_confidence": rec.get("map_confidence", ""),
        "resolution": "RTO/ISO market region — not a retail service territory",
    }


def load_concentration(facility_count, net_gen_mwh,
                       campus_mw: float = ASSUMED_CAMPUS_MW,
                       utilization: float = ASSUMED_UTILIZATION) -> dict:
    """Observed campuses in a subregion as a share of its annual net generation.

    Pure. Returns `share_pct=None` when either input is unusable, never 0 —
    an unknown denominator is not the same as no concentration.
    """
    if not is_number(facility_count) or not is_number(net_gen_mwh) or float(net_gen_mwh) <= 0:
        return {
            "facility_count": int(facility_count) if is_number(facility_count) else None,
            "implied_load_mwh_yr": None, "share_pct": None, "band": "insufficient data",
            "assumed_campus_mw": campus_mw,
        }
    n = int(facility_count)
    implied = n * float(campus_mw) * float(utilization) * HOURS_PER_YEAR
    share = clamp(100.0 * implied / float(net_gen_mwh), 0.0, 1000.0)
    if share is None:
        band = "insufficient data"
    elif share >= CONCENTRATION_HIGH:
        band = "high"
    elif share >= CONCENTRATION_NOTABLE:
        band = "notable"
    else:
        band = "low"
    return {
        "facility_count": n,
        "implied_load_mwh_yr": round(implied),
        "share_pct": round(share, 2),
        "band": band,
        "assumed_campus_mw": campus_mw,
        "basis": (
            f"{n} observed campuses x {campus_mw:.0f} MW assumed x "
            f"{utilization:.0%} utilization, against subregion annual net generation. "
            "Screening-grade: per-site capacity is not in the registry."
        ),
    }


def context(subrgn: str, facility_count=None, net_gen_mwh=None) -> dict:
    """Operator identity + load concentration for a subregion. Pure."""
    out = operator_for_subregion(subrgn)
    out["concentration"] = load_concentration(facility_count, net_gen_mwh)
    out["not_modelled"] = (
        "Retail rates, tariffs and cost allocation are not modelled. No rate data "
        "is ingested; this indicates where large-load growth is concentrated, not "
        "what any ratepayer will be charged."
    )
    return out


__all__ = [
    "ASSUMED_CAMPUS_MW",
    "CONCENTRATION_HIGH",
    "CONCENTRATION_NOTABLE",
    "SUBREGION_MAP",
    "context",
    "load_concentration",
    "operator_for_subregion",
    "subregion_to_rto",
]
