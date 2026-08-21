"""Integrity tests for the ingestion/versioning layer and the published catalog."""

import json

import pytest

from wattershed.provenance import SOURCES
from wattershed.sources.catalog import CATALOG_PATH, build_catalog, declarative_view
from wattershed.sources.versioning import (
    ACTIVE,
    BLOCKS,
    PILLAR_LABELS,
    controller,
)


def test_every_block_maps_to_a_registered_source():
    for bid, b in BLOCKS.items():
        assert b.source_id in SOURCES, f"{bid} → unregistered source {b.source_id}"


def test_every_block_declares_version_and_resolution():
    for bid, b in BLOCKS.items():
        assert b.published, f"{bid} missing publication timestamp"
        assert b.spatial_unit, f"{bid} missing spatial resolution"
        assert b.ingestion_mode, f"{bid} missing ingestion mode"
        assert b.role, f"{bid} missing role"


def test_uningested_blocks_carry_no_pillar_weight():
    """A registry we do not read must never be attributed to a score."""
    for b in controller().uningested_declarations():
        assert b.pillar == "none", f"{b.block_id} is not ingested but claims pillar {b.pillar}"
        assert b.caveat, f"{b.block_id} must explain why it is absent"


def test_each_scoring_pillar_has_active_blocks():
    dvc = controller()
    for pillar in PILLAR_LABELS:
        active = [b for b in dvc.blocks_for_pillar(pillar) if b.status == ACTIVE]
        assert active, f"pillar {pillar} has no ingested blocks"


def test_block_ids_are_pillar_prefixed():
    for bid, b in BLOCKS.items():
        assert bid.split(".", 1)[0] in {"water", "grid", "burden", "geo", "infra"}, bid


def test_controller_is_a_cached_singleton():
    assert controller() is controller()


def test_resolve_joins_source_metadata():
    r = controller().resolve("grid.emissions_factors")
    assert r["provider"] == "U.S. EPA"
    assert r["spatial_unit"] == "eGRID subregion"
    assert r["published"] == "2025-06"


def test_committed_catalog_is_current():
    """`data_catalog.json` is generated — a stale copy is a provenance defect."""
    if not CATALOG_PATH.exists():
        pytest.skip("catalog not built in this checkout")
    live = declarative_view(build_catalog())
    committed = declarative_view(json.loads(CATALOG_PATH.read_text()))
    assert live == committed, "run `wattershed build-catalog`"


def test_catalog_registries_are_referenced():
    cat = build_catalog()
    referenced = {b["source_id"] for p in cat["pillars"].values() for b in p["blocks"]}
    referenced |= {b["source_id"] for b in cat["cross_cutting"]}
    assert referenced <= set(cat["registries"]), "block references a registry the catalog omits"


def test_catalog_names_the_uningested_registries():
    """The two registries most likely to be assumed present must say so."""
    ids = {b["block_id"] for b in build_catalog()["not_ingested"]}
    assert "grid.eia_hourly_ba" in ids
    assert "water.usgs_realtime_hydrology" in ids


def test_report_provenance_payload_cannot_break_out_of_its_script_tag():
    from pathlib import Path

    from wattershed.models import Screening
    from wattershed.report.render import render_report

    results = sorted(Path("out").glob("*.json"))
    if not results:
        pytest.skip("no screening results to render")
    html = render_report(Screening.model_validate_json(results[0].read_text()))
    payload = html.split('id="prov-data">', 1)[1].split("</script>", 1)[0]
    json.loads(payload)
    assert "<" not in payload
    assert html.count('data-prov="') == 2 * len(PILLAR_LABELS)  # tile + section flag per pillar
