# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Per-site HTML report renderer — a print-ready screening memo.

Design: light, print-first document (consulting deliverable). All CSS inline;
no external assets; charts are pure HTML/CSS (percentile bars, score meters,
mix bar) so the file works offline and in print. Colors follow the validated
reference palette (docs in the dataviz method): status colors carry tier/band
STATE and always ship with a text label; sequential blue carries magnitude.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Screening
from ..sources.catalog import load_catalog
from ..sources.versioning import ACTIVE, PILLAR_LABELS

log = logging.getLogger("wattershed.report")

_TEMPLATES = Path(__file__).parent / "templates"

TIER_STYLE = {
    "Low": ("#0ca30c", "#eaf6ea"),
    "Moderate": ("#8a6d00", "#fdf3d7"),
    "Elevated": ("#a34f13", "#fde8dc"),
    "High": ("#d03b3b", "#fbe4e4"),
}

BAND_COLOR = {
    "low": "#0ca30c",
    "moderate": "#8a6d00",
    "high": "#a34f13",
    "severe": "#d03b3b",
    "insufficient data": "#898781",
}

# Fuel mix folded to five fixed groups (categorical slots 1–5, fixed order).
MIX_GROUPS = [
    ("Fossil", ["coal", "oil", "gas", "other_fossil"], "#2a78d6"),
    ("Nuclear", ["nuclear"], "#008300"),
    ("Hydro", ["hydro"], "#e87ba4"),
    ("Wind + Solar", ["wind", "solar"], "#eda100"),
    ("Other", ["biomass", "geothermal", "other"], "#1baf7a"),
]


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["fmt_num"] = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else v
    env.filters["fmt0"] = lambda v: f"{v:.0f}" if isinstance(v, (int, float)) else "—"
    env.filters["fmt1"] = lambda v: f"{v:.1f}" if isinstance(v, (int, float)) else "—"
    return env


def _mix_groups(screening: Screening) -> list[dict]:
    mix_ind = next((i for i in screening.grid.indicators if i.id == "egrid_mix"), None)
    if mix_ind is None:
        return []
    # recover mix from the demand/grid stats attached at screen time
    stats_mix = screening.neighborhood.get("_grid_mix") or {}
    if not stats_mix:
        return []
    out = []
    for label, fuels, color in MIX_GROUPS:
        share = 100 * sum(stats_mix.get(f, 0.0) for f in fuels)
        if share > 0.05:
            out.append({"label": label, "pct": round(share, 1), "color": color})
    return out


# Fields carried into the report's provenance modal. Deliberately narrower
# than the catalog: licence text and cross-cutting geography blocks already
# appear in the report's source table, and this JSON is inlined into every
# memo, so anything repeated here is paid for once per file.
_MODAL_FIELDS = (
    "role",
    "ingestion_mode",
    "published",
    "describes",
    "spatial_unit",
    "spatial_note",
    "refresh_cadence",
    "caveat",
)


@lru_cache(maxsize=1)
def _catalog_lineage() -> dict:
    """Pillar → ordered pipeline lineage, read from data_catalog.json once per
    process (a batch run renders ~10 memos from a single read)."""
    cat = load_catalog()
    registries = cat.get("registries", {})
    out: dict[str, list[dict]] = {}
    for pillar, block in cat.get("pillars", {}).items():
        rows = []
        for b in block.get("blocks", []):
            reg = registries.get(b.get("source_id"), {})
            row = {k: b[k] for k in _MODAL_FIELDS if b.get(k)}
            row.update(
                {
                    "source_id": b.get("source_id", ""),
                    "status": b.get("status", ACTIVE),
                    "registry": reg.get("name", ""),
                    "provider": reg.get("provider", ""),
                    "url": reg.get("url", ""),
                    "catalog_retrieval": b.get("observed_retrieval", ""),
                }
            )
            rows.append(row)
        out[pillar] = rows
    log.debug("lineage: %s", {k: len(v) for k, v in out.items()})
    return out


def _provenance(screening: Screening) -> dict:
    """Join catalog lineage to THIS run's ledger so the flag shows the date the
    data was actually collected for this screening, not a build-time default."""
    ledger = {r["source_id"]: r.get("retrieved", "") for r in screening.sources}
    ctx: dict[str, dict] = {}
    for pillar in PILLAR_LABELS:
        rows, dates = [], []
        for row in _catalog_lineage().get(pillar, []):
            r = dict(row)
            r["retrieved"] = ledger.get(r["source_id"]) or r.get("catalog_retrieval", "")
            r.pop("catalog_retrieval", None)
            if r["retrieved"] and r["status"] == ACTIVE:
                dates.append(r["retrieved"])
            rows.append(r)
        ctx[pillar] = {
            "label": PILLAR_LABELS[pillar],
            "collected": max(dates)[:10] if dates else "",
            "oldest": min(dates)[:10] if dates else "",
            "blocks": rows,
        }
    return ctx


def render_report(screening: Screening) -> str:
    env = _env()
    tpl = env.get_template("report.html.j2")
    tier_fg, tier_bg = TIER_STYLE[screening.tier.value]
    prov = _provenance(screening)
    cat = load_catalog()
    return tpl.render(
        s=screening,
        tier_fg=tier_fg,
        tier_bg=tier_bg,
        band_color=BAND_COLOR,
        mix_groups=_mix_groups(screening),
        prov=prov,
        # `</script>` can never appear in the inlined JSON, so the payload
        # cannot break out of its script element regardless of catalog text.
        prov_json=json.dumps(prov, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c"),
        catalog_version=cat.get("catalog_version", ""),
        not_ingested=cat.get("not_ingested", []),
    )
