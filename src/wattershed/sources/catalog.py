# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Builds `data_catalog.json` — the machine-readable schema map.

One artifact, generated from `DataVersionController` + `provenance.SOURCES`,
so it can never drift from what the code actually ingests. Nothing here is
hand-maintained; regenerate with `wattershed build-catalog`.

Shape is normalized on purpose: source metadata (licence text, URL, provider)
appears once under `registries` and blocks reference it by id. Repeating a
CC-BY attribution string across fourteen blocks would triple the file for no
information gain — and this file is read by the report renderer and inlined
into every HTML memo, so bytes here are bytes in every deliverable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import __version__, config, provenance
from .versioning import ACTIVE, DECLARED_NOT_INGESTED, PILLAR_LABELS, controller

log = logging.getLogger("wattershed.catalog")

CATALOG_VERSION = "1.0"
CATALOG_PATH = config.REPO_ROOT / "data_catalog.json"

# Block fields that belong in the published catalog. Anything not listed is
# internal; keeping this explicit stops the artifact growing by accident.
_BLOCK_FIELDS = (
    "block_id",
    "source_id",
    "role",
    "ingestion_mode",
    "published",
    "describes",
    "spatial_unit",
    "spatial_note",
    "refresh_cadence",
    "status",
    "caveat",
)


def _block_record(resolved: dict) -> dict:
    rec = {k: resolved[k] for k in _BLOCK_FIELDS if resolved.get(k)}
    if resolved.get("observed_retrieval"):
        rec["observed_retrieval"] = resolved["observed_retrieval"]
    return rec


def build_catalog() -> dict:
    dvc = controller()
    used_source_ids: set[str] = set()

    pillars: dict[str, dict] = {}
    for pillar, label in PILLAR_LABELS.items():
        blocks = [dvc.resolve(b.block_id) for b in dvc.blocks_for_pillar(pillar)]
        used_source_ids.update(b["source_id"] for b in blocks)
        pillars[pillar] = {
            "label": label,
            "registries": sorted({b["provider"] for b in blocks}),
            "blocks": [_block_record(b) for b in blocks],
        }

    cross = [dvc.resolve(b.block_id) for b in dvc.blocks_for_pillar("cross-cutting")]
    used_source_ids.update(b["source_id"] for b in cross)

    # Ingested, current, and deliberately scoreless. Listed separately so a
    # reader can see at a glance what informs context vs what moves a number.
    context = [dvc.resolve(b.block_id) for b in dvc.blocks_for_pillar("context")]
    used_source_ids.update(b["source_id"] for b in context)

    not_ingested = []
    for b in dvc.uningested_declarations():
        r = dvc.resolve(b.block_id)
        used_source_ids.add(r["source_id"])
        not_ingested.append(
            {
                "block_id": r["block_id"],
                "expected_registry": r["role"].replace("NOT INGESTED — ", ""),
                "spatial_unit": r["spatial_unit"],
                "why_not": r["caveat"],
            }
        )

    registries = {
        sid: {
            "name": s.name,
            "provider": s.provider,
            "url": s.url,
            "vintage": s.vintage,
            "license": s.license,
            **({"notes": s.notes} if s.notes else {}),
        }
        for sid, s in provenance.SOURCES.items()
        if sid in used_source_ids
    }

    return {
        "catalog_version": CATALOG_VERSION,
        "tool_version": __version__,
        "generated_at": provenance.utc_now_iso(),
        "generated_by": "wattershed build-catalog (derived from sources/versioning.py)",
        "description": (
            "Schema map from each Wattershed score metric back to the official registry "
            "and ingestion endpoint that produces it, with publication timestamp and "
            "native spatial resolution per index block."
        ),
        "conventions": {
            "published": "When the PUBLISHER released the block. Granularity varies (YYYY, YYYY-MM, or 'rolling').",
            "describes": "The period the data describes — distinct from 'published' and from retrieval.",
            "observed_retrieval": "When THIS checkout actually fetched the file (from data/cache/*.meta.json).",
            "spatial_unit": "Native geometry a value resolves to. A point score is only as sharp as its coarsest input.",
            "ingestion_mode": {
                "static_snapshot": "Bulk file pinned at reference-build time.",
                "periodic_bulk": "Bulk file refreshed on a cadence.",
                "api_live": "Queried per screening run; retrieval stamped in the run ledger.",
                "transcribed_constant": "Constants hand-copied from a cited publication.",
            },
            "status": {
                ACTIVE: "Ingested and feeding a score.",
                DECLARED_NOT_INGESTED: "Listed only to state plainly that it is NOT read by this tool.",
            },
        },
        "pillars": pillars,
        "cross_cutting": [_block_record(b) for b in cross],
        "context_layers": {
            "note": "Refreshed automatically; feeds no pillar score by design.",
            "blocks": [_block_record(b) for b in context],
        },
        "not_ingested": not_ingested,
        "registries": registries,
    }


def write_catalog(path: Path | None = None) -> Path:
    dest = Path(path) if path else CATALOG_PATH
    catalog = build_catalog()
    dest.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    n_blocks = sum(len(p["blocks"]) for p in catalog["pillars"].values())
    log.info("catalog: %d blocks, %d registries, %d declared-not-ingested → %s",
             n_blocks, len(catalog["registries"]), len(catalog["not_ingested"]), dest)
    return dest


def declarative_view(catalog: dict) -> dict:
    """The catalog with per-checkout observed state stripped.

    `generated_at` and `observed_retrieval` describe THIS working copy, not the
    schema: pulling a fresh USDM map legitimately changes them. Drift checks
    compare this view so CI fails on an actual schema change and not on a
    cache refresh.
    """
    out = json.loads(json.dumps(catalog))  # cheap deep copy; catalogs are small
    out.pop("generated_at", None)
    for pillar in out.get("pillars", {}).values():
        for b in pillar.get("blocks", []):
            b.pop("observed_retrieval", None)
    for b in out.get("cross_cutting", []):
        b.pop("observed_retrieval", None)
    for b in (out.get("context_layers") or {}).get("blocks", []):
        b.pop("observed_retrieval", None)
    return out


def load_catalog(path: Path | None = None) -> dict:
    """Read the committed catalog; falls back to building it in-memory if the
    artifact is absent so rendering never hard-fails on a fresh checkout."""
    src = Path(path) if path else CATALOG_PATH
    if src.exists():
        return json.loads(src.read_text())
    log.warning("catalog: %s missing — building in memory (run `wattershed build-catalog`)", src)
    return build_catalog()


__all__ = [
    "CATALOG_PATH",
    "CATALOG_VERSION",
    "build_catalog",
    "declarative_view",
    "load_catalog",
    "write_catalog",
]
