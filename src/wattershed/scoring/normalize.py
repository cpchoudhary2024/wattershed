"""Pure normalization primitives shared by all three pillars.

Every pillar independently reimplemented `band()` and the weighted blend, so
the 0–100 contract was asserted in three places and enforced in none. This
module is the single definition. Everything here is a pure function: no I/O,
no globals mutated, no caching — same inputs, same outputs, safe to call from
any thread or process.

The contract a score must satisfy before it reaches a template or a JSON file:

  * a real, finite float in [0, 100], or
  * None, meaning "insufficient data" — rendered as such, never imputed.

NaN is explicitly NOT a valid score. It propagates silently through arithmetic,
compares False against every threshold (so `band(nan)` would read "low"), and
serializes as the bare token `NaN`, which is invalid JSON — a downstream
`JSON.parse` in the dashboard throws and the widget dies mid-render. Every
entry point here collapses NaN and ±inf to None instead.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

SCORE_MIN = 0.0
SCORE_MAX = 100.0

# Single band ladder. Pillar modules re-export `band` rather than redefining
# thresholds; the dashboard mirrors these cut points in JS.
BAND_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (75.0, "severe"),
    (55.0, "high"),
    (35.0, "moderate"),
    (0.0, "low"),
)
BAND_INSUFFICIENT = "insufficient data"

# The burden pillar's score IS a national percentile, not a weighted 0–100
# blend, so it reads against a deliberately different ladder: "severe" means
# top decile of U.S. tracts, not "≥75 on a constructed index". Both ladders
# live here so the divergence is a visible decision rather than three files
# that quietly disagree.
PERCENTILE_BAND_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (90.0, "severe"),
    (75.0, "high"),
    (50.0, "moderate"),
    (0.0, "low"),
)


def is_number(v: Any) -> bool:
    """True only for a real, finite number. Rejects None, NaN, ±inf, bools
    (bool is an int subclass — `True` must never be scored as 1.0), strings,
    and anything else that would blow up or silently coerce downstream."""
    if v is None or isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    return math.isfinite(float(v))


def clamp(v: Any, lo: float = SCORE_MIN, hi: float = SCORE_MAX) -> float | None:
    """Constrain to [lo, hi]. Non-numbers become None rather than an exception:
    a screening should degrade to an honest data gap, not a stack trace."""
    if not is_number(v):
        return None
    return float(min(max(float(v), lo), hi))


def to_score(v: Any) -> float | None:
    """Coerce anything to a valid 0–100 score or None. The single funnel every
    value passes through before it can be called a score."""
    return clamp(v)


def band(score: Any, ladder: tuple[tuple[float, str], ...] = BAND_THRESHOLDS) -> str:
    """Qualitative band for a score. Anything not a valid score reads as
    'insufficient data' — never as 'low', which is what a NaN or None would
    silently become under a bare chain of `>=` comparisons."""
    s = to_score(score)
    if s is None:
        return BAND_INSUFFICIENT
    for threshold, label in ladder:
        if s >= threshold:
            return label
    return ladder[-1][1]


def percentile_band(score: Any) -> str:
    """Band for a score that is itself a national percentile (burden pillar)."""
    return band(score, PERCENTILE_BAND_THRESHOLDS)


def blend(
    components: Mapping[str, Any],
    weights: Mapping[str, float],
    *,
    min_weight_share: float = 0.0,
) -> float | None:
    """Weighted mean over the components that are actually present, with the
    weights renormalized to what survived.

    Defensive behaviours, each a bug this replaced:
      * a component that is None/NaN/inf is dropped, not propagated;
      * every surviving component is clamped to [0,100] BEFORE weighting, so a
        single out-of-range input cannot push the blend outside the contract;
      * a component with no declared weight is ignored (it would otherwise
        raise KeyError mid-screening);
      * non-positive or non-finite weights are ignored;
      * if the surviving weights carry less than `min_weight_share` of the
        total declared weight, the result is None — better an explicit data
        gap than a confident score resting on one minor signal;
      * a zero total weight returns None instead of dividing by zero.
    """
    usable: list[tuple[float, float]] = []
    for key, raw in components.items():
        w = weights.get(key)
        if w is None or not is_number(w) or w <= 0:
            continue
        v = to_score(raw)
        if v is None:
            continue
        usable.append((float(w), v))

    if not usable:
        return None
    wsum = math.fsum(w for w, _ in usable)
    if wsum <= 0:
        return None

    declared = math.fsum(w for w in weights.values() if is_number(w) and w > 0)
    if min_weight_share > 0 and declared > 0 and (wsum / declared) < min_weight_share:
        return None

    return clamp(math.fsum(w * v for w, v in usable) / wsum)


def mean_or_none(values: Iterable[Any], *, minimum: int = 1) -> float | None:
    """Mean of the usable values, or None if fewer than `minimum` are usable.
    Enforces the coverage floors the burden domains rely on."""
    have = [float(v) for v in values if is_number(v)]
    if len(have) < max(1, minimum):
        return None
    return math.fsum(have) / len(have)


def percentile_of(value: Any, population: Iterable[Any]) -> float | None:
    """Mid-rank percentile (ties split) of `value` within `population`.

    Mid-rank keeps the maximum from reading as 'higher than 100%' and stops a
    heavily-tied category from being overstated — matching the convention the
    reference table and the dashboard already use.
    """
    if not is_number(value):
        return None
    v = float(value)
    below = equal = n = 0
    for x in population:
        if not is_number(x):
            continue
        n += 1
        if float(x) < v:
            below += 1
        elif float(x) == v:
            equal += 1
    if n == 0:
        return None
    return clamp(100.0 * (below + 0.5 * equal) / n)


# --- coordinate validation --------------------------------------------------

# Disjoint bounding boxes over U.S. tract coverage. A single continental box
# spanning Puerto Rico to Alaska necessarily swallows northern Mexico, Cuba and
# much of Canada; separate boxes per region reject those while still admitting
# every place Wattershed can actually screen. Still only a cheap pre-filter —
# the authoritative answer is whether the geocoder returns a tract — but it
# stops obviously-foreign input before a network call or a haversine that
# would return nonsense.
US_REGION_BOXES: tuple[tuple[float, float, float, float, str], ...] = (
    (24.396, 49.385, -125.001, -66.934, "CONUS"),
    (51.000, 71.500, -179.999, -129.000, "Alaska"),
    (51.000, 54.000, 172.000, 180.000, "Aleutian (west of the antimeridian)"),
    (18.865, 22.300, -160.300, -154.750, "Hawaii"),
    (17.600, 18.600, -67.300, -64.500, "Puerto Rico / U.S. Virgin Islands"),
)


def us_region(lat: float, lon: float) -> str | None:
    """Name of the U.S. region box containing the point, or None. Pure."""
    for lat_lo, lat_hi, lon_lo, lon_hi, name in US_REGION_BOXES:
        if lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi:
            return name
    return None


def validate_coordinates(lat: Any, lon: Any) -> tuple[bool, str]:
    """(is_usable, reason). Never raises — callers decide how to degrade."""
    if not is_number(lat) or not is_number(lon):
        return False, "Coordinates must be finite numbers."
    lat_f, lon_f = float(lat), float(lon)
    if not (-90.0 <= lat_f <= 90.0):
        return False, f"Latitude {lat_f} is outside the valid range [-90, 90]."
    if not (-180.0 <= lon_f <= 180.0):
        return False, f"Longitude {lon_f} is outside the valid range [-180, 180]."
    if us_region(lat_f, lon_f) is None:
        return False, (
            f"({lat_f:.4f}, {lon_f:.4f}) lies outside U.S. census-tract coverage — "
            "Wattershed screens U.S. locations only."
        )
    return True, ""


__all__ = [
    "SCORE_MIN",
    "SCORE_MAX",
    "BAND_THRESHOLDS",
    "PERCENTILE_BAND_THRESHOLDS",
    "BAND_INSUFFICIENT",
    "is_number",
    "clamp",
    "to_score",
    "band",
    "percentile_band",
    "blend",
    "mean_or_none",
    "percentile_of",
    "validate_coordinates",
    "us_region",
    "US_REGION_BOXES",
]
