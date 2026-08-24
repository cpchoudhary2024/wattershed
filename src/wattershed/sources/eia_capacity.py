# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""EIA v2 adapter — operating generator capacity, by balancing authority.

KEY-GATED BY DESIGN. Every other source in Wattershed is keyless, and
DATA_SOURCES.md states that as a property of the project: a fresh clone
screens any U.S. point with no registration. EIA v2 breaks that — an
unauthenticated request returns:

    {"error": {"code": "API_KEY_MISSING", ...}}

The key is free (no payment, no quota purchase) but it is still a
registration, so this adapter is OPTIONAL. With no key configured it reports
itself as skipped and the sync run succeeds; it never fails a build and never
becomes a prerequisite for screening. Set the EIA_API_KEY repository secret
to turn it on.

Scope note: this returns generator capacity, i.e. supply-side context for the
grid pillar. It is NOT the hourly balancing-authority operations feed
(EIA-930) that would be needed for marginal or time-matched emissions —
that remains a documented v2 item, and this adapter does not pretend to it.
"""

from __future__ import annotations

import logging

from .. import config
from .base import fetch_json

log = logging.getLogger("wattershed.eia")

BASE_URL = "https://api.eia.gov/v2/electricity/operating-generator-capacity/data/"


class EIAKeyMissing(RuntimeError):
    """Raised only when a caller explicitly demands EIA; the sync catches it."""


def available() -> bool:
    return bool(config.EIA_API_KEY)


def parse_rows(payload: dict) -> list[dict]:
    """Pure: EIA response envelope in, normalized capacity records out."""
    rows = ((payload or {}).get("response") or {}).get("data") or []
    out = []
    for r in rows:
        mw = r.get("nameplate-capacity-mw")
        try:
            mw = None if mw in (None, "") else float(mw)
        except (TypeError, ValueError):
            mw = None
        out.append(
            {
                "period": r.get("period", ""),
                "balancing_authority": r.get("balancing_authority_code", ""),
                "state": r.get("stateid", ""),
                "technology": r.get("technology", ""),
                "status": r.get("statusDescription", ""),
                "nameplate_mw": mw,
            }
        )
    return out


def fetch_capacity(length: int = 5000, timeout: int = 90) -> list[dict]:
    """Most recent monthly capacity listing. Raises EIAKeyMissing if unset."""
    if not available():
        raise EIAKeyMissing(
            "EIA_API_KEY is not set — EIA is optional; register free at "
            "https://www.eia.gov/opendata/register.php and add it as a repo secret."
        )
    payload = fetch_json(
        BASE_URL,
        params={
            "api_key": config.EIA_API_KEY,
            "frequency": "monthly",
            "data[0]": "nameplate-capacity-mw",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": length,
        },
        timeout=timeout,
    )
    recs = parse_rows(payload)
    log.info("eia: %d capacity rows", len(recs))
    return recs


__all__ = ["BASE_URL", "EIAKeyMissing", "available", "fetch_capacity", "parse_rows"]
