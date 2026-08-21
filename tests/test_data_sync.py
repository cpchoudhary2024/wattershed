"""Bi-weekly sync pipeline: parsing, spatial reconciliation, and the
architectural boundaries that keep an unattended job from moving a score.
"""

import json

import numpy as np
import pytest

from wattershed.pipelines import data_sync, infra_density
from wattershed.sources import eia_capacity, news, osm_facilities

# --- news: parsing, dedupe, and the retention cap ---------------------------

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Hyperscale campus announced in Memphis</title>
      <link>https://example.com/a?utm=1</link>
      <pubDate>Tue, 18 Aug 2026 17:35:28 GMT</pubDate>
      <source url="https://x.com">WTTW</source></item>
<item><title>Permit approved for &lt;b&gt;new&lt;/b&gt; data center</title>
      <link>https://example.com/b</link>
      <pubDate>Mon, 17 Aug 2026 09:00:00 GMT</pubDate></item>
<item><title>No link here</title></item>
</channel></rss>"""


def test_news_parses_items_and_drops_incomplete_ones():
    items = news.parse_feed(RSS, "q")
    assert len(items) == 2
    assert items[0]["published"] == "2026-08-18T17:35:28Z"
    assert items[0]["source"] == "WTTW"


def test_news_strips_markup_from_titles():
    assert "<b>" not in news.parse_feed(RSS, "q")[1]["title"]


def test_news_items_are_always_flagged_unverified():
    """Headlines are secondary reporting; nothing here may claim verification."""
    assert all(i["verified"] is False for i in news.parse_feed(RSS, "q"))


def test_news_survives_malformed_xml():
    assert news.parse_feed("<not xml", "q") == []
    assert news.parse_feed("", "q") == []


def test_news_dedupes_on_stable_id_ignoring_tracking_params():
    a = news.parse_feed(RSS, "q1")
    b = news.parse_feed(RSS.replace("?utm=1", "?utm=99"), "q2")
    assert len(news.merge(a, b)) == 2


def test_news_merge_caps_retention_newest_first():
    items = [{"id": str(i), "published": f"2026-01-{i:02d}T00:00:00Z"} for i in range(1, 21)]
    kept = news.merge([], items, max_items=5)
    assert len(kept) == 5
    assert kept[0]["published"].startswith("2026-01-20")


# --- OSM / Overpass ---------------------------------------------------------

def test_osm_parses_nodes_and_way_centroids():
    recs = osm_facilities.parse_elements({"elements": [
        {"type": "node", "id": 1, "lat": 35.0, "lon": -90.0, "tags": {"name": "A"}},
        {"type": "way", "id": 2, "center": {"lat": 36.0, "lon": -86.0}, "tags": {"name": "B"}},
    ]})
    assert [r["osm_id"] for r in recs] == ["node/1", "way/2"]


def test_osm_drops_elements_without_coordinates_rather_than_defaulting():
    recs = osm_facilities.parse_elements({"elements": [{"type": "node", "id": 3, "tags": {}}]})
    assert recs == []


@pytest.mark.parametrize("payload", [{}, None, {"elements": None}])
def test_osm_parse_is_empty_safe(payload):
    assert osm_facilities.parse_elements(payload) == []


def test_osm_query_covers_both_the_current_and_deprecated_tag():
    q = osm_facilities.build_query()
    assert 'telecom"="data_center' in q and 'man_made"="data_center' in q


def test_osm_declares_more_than_one_mirror():
    """A single congested endpoint must not be able to stall the whole job."""
    assert len(osm_facilities.MIRRORS) >= 2


# --- EIA: optional and key-gated -------------------------------------------

def test_eia_is_gated_when_no_key_is_configured(monkeypatch):
    monkeypatch.setattr(eia_capacity.config, "EIA_API_KEY", None)
    assert eia_capacity.available() is False
    with pytest.raises(eia_capacity.EIAKeyMissing):
        eia_capacity.fetch_capacity()


def test_eia_parses_rows_and_tolerates_missing_capacity():
    rows = eia_capacity.parse_rows({"response": {"data": [
        {"period": "2026-05", "balancing_authority_code": "MISO", "nameplate-capacity-mw": "12.5"},
        {"period": "2026-05", "nameplate-capacity-mw": None},
        {"period": "2026-05", "nameplate-capacity-mw": "not-a-number"},
    ]}})
    assert [r["nameplate_mw"] for r in rows] == [12.5, None, None]


# --- density: pure spatial maths --------------------------------------------

def test_haversine_matches_known_distances():
    d = infra_density.haversine_km(35.0, -90.0, np.array([35.0, 36.0]), np.array([-90.0, -90.0]))
    assert d[0] == pytest.approx(0.0, abs=1e-9)
    assert d[1] == pytest.approx(111.2, rel=0.01)


def test_neighbourhood_counts_respect_the_radius():
    lats, lons = np.array([35.0]), np.array([-90.0])
    near = [{"lat": 35.01, "lon": -90.0}]      # ~1.1 km
    far = [{"lat": 36.0, "lon": -90.0}]        # ~111 km
    assert infra_density.neighbourhood_counts(lats, lons, near, 5.0)[0] == 1
    assert infra_density.neighbourhood_counts(lats, lons, far, 5.0)[0] == 0


def test_density_modifier_is_monotonic_and_bounded():
    idm = infra_density.modifier_from_counts(
        np.array([0, 0, 1, 2, 5, 50]), np.array([0, 1, 2, 4, 9, 99]))
    assert np.all((idm >= 0) & (idm <= 100))
    assert np.all(np.diff(idm) >= 0), "more facilities must never lower the index"


def test_hosting_a_facility_outweighs_merely_being_near_one():
    host = infra_density.modifier_from_counts(np.array([1]), np.array([1]))[0]
    near = infra_density.modifier_from_counts(np.array([0]), np.array([1]))[0]
    assert host > near


def test_density_modifier_ignores_facility_free_tracts():
    assert infra_density.modifier_from_counts(np.array([0]), np.array([0]))[0] == 0.0


# --- reconciliation: delta-only geocoding -----------------------------------

def _fac(i, lat=35.0, lon=-90.0):
    return {"osm_id": f"node/{i}", "name": f"F{i}", "operator": "", "lat": lat, "lon": lon}


def test_reconcile_geocodes_only_new_facilities(monkeypatch):
    calls = []

    def fake(lat, lon, timeout=25):
        calls.append((lat, lon))
        return "47157022220", "47157"

    monkeypatch.setattr(data_sync, "assign_tract", fake)
    existing = [dict(_fac(1), tract_geoid="47157000100", county_fips="47157")]
    _registry, added = data_sync.reconcile_facilities(existing, [_fac(1), _fac(2)])
    assert added == 1
    assert len(calls) == 1, "an already-resolved facility must not be re-geocoded"


def test_reconcile_preserves_the_cached_tract_assignment(monkeypatch):
    monkeypatch.setattr(data_sync, "assign_tract", lambda *a, **k: ("99999999999", "99999"))
    existing = [dict(_fac(1), tract_geoid="47157000100", county_fips="47157")]
    registry, _ = data_sync.reconcile_facilities(existing, [_fac(1)])
    assert registry[0]["tract_geoid"] == "47157000100"


def test_reconcile_refreshes_mutable_tags_on_known_facilities(monkeypatch):
    monkeypatch.setattr(data_sync, "assign_tract", lambda *a, **k: ("", ""))
    existing = [dict(_fac(1), name="old", tract_geoid="47157000100", county_fips="47157")]
    registry, _ = data_sync.reconcile_facilities(existing, [dict(_fac(1), name="Renamed")])
    assert registry[0]["name"] == "Renamed"


def test_reconcile_caps_geocodes_per_run(monkeypatch):
    calls = []
    monkeypatch.setattr(data_sync, "assign_tract",
                        lambda lat, lon, timeout=25: (calls.append(1), ("", ""))[1])
    data_sync.reconcile_facilities([], [_fac(i) for i in range(50)], max_geocodes=10)
    assert len(calls) == 10


def test_failed_geocode_leaves_the_facility_for_the_next_cycle(monkeypatch):
    monkeypatch.setattr(data_sync, "assign_tract", lambda *a, **k: ("", ""))
    registry, _ = data_sync.reconcile_facilities([], [_fac(1)])
    assert registry[0]["tract_geoid"] == ""


# --- state partitioning -----------------------------------------------------

def test_partition_splits_by_state_fips():
    facs = [dict(_fac(1), tract_geoid="47157022220"), dict(_fac(2), tract_geoid="06037101110")]
    chunks = data_sync.partition_by_state(facs, [])
    assert set(chunks) == {"47", "06"}


def test_partition_attaches_density_to_its_tract():
    facs = [dict(_fac(1), tract_geoid="47157022220")]
    dens = [{"geoid": "47157022220", "density_modifier": 61.2}]
    assert data_sync.partition_by_state(facs, dens)["47"]["density"]["47157022220"] == 61.2


def test_partition_skips_facilities_without_a_resolved_tract():
    assert data_sync.partition_by_state([dict(_fac(1), tract_geoid="")], []) == {}


# --- idempotence & artifact bounds ------------------------------------------

def test_write_is_skipped_when_content_is_unchanged(tmp_path):
    report = data_sync.SyncReport()
    p = tmp_path / "x.json"
    assert data_sync._write_json_if_changed(p, {"a": 1}, report) is True
    assert data_sync._write_json_if_changed(p, {"a": 1}, report) is False, \
        "an unchanged cycle must not manufacture a commit"
    assert data_sync._write_json_if_changed(p, {"a": 2}, report) is True


def test_unreadable_artifact_falls_back_instead_of_crashing(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json")
    assert data_sync._read_json(p, []) == []


def test_news_retention_cap_is_bounded():
    """This file is committed twice a month; an unbounded append is repo bloat."""
    assert news.MAX_ITEMS <= 1000


# --- architectural boundary: context must never reach a score ---------------

SCORING_MODULES = ["water", "grid", "burden", "tiers", "reference", "mitigation", "normalize"]


@pytest.mark.parametrize("mod", SCORING_MODULES)
def test_no_scoring_module_imports_the_density_or_sync_layer(mod):
    """The load-bearing guarantee of this pipeline.

    If a pillar ever imported infra_density, a screening result could change
    because a volunteer edited OpenStreetMap — with no reviewer and no
    changelog — and the siting-equity study would become circular, since it
    asks whether data centres cluster in burdened tracts.
    """
    from pathlib import Path

    import wattershed.scoring as pkg

    src = (Path(pkg.__file__).parent / f"{mod}.py").read_text()
    assert "infra_density" not in src, f"scoring.{mod} imports the density layer"
    assert "data_sync" not in src, f"scoring.{mod} imports the sync pipeline"
    assert "news" not in src, f"scoring.{mod} references the news layer"


def test_density_blocks_are_catalogued_as_scoreless_context():
    from wattershed.sources.versioning import BLOCKS

    for bid in ("infra.facility_registry", "infra.announcement_leads", "infra.eia_capacity"):
        assert BLOCKS[bid].pillar == "context", f"{bid} must not claim a pillar"


def test_context_layers_appear_in_the_published_catalog():
    from wattershed.sources.catalog import build_catalog

    ctx = build_catalog()["context_layers"]
    assert {b["block_id"] for b in ctx["blocks"]} == {
        "infra.facility_registry", "infra.announcement_leads", "infra.eia_capacity"}
    assert "no pillar score" in ctx["note"]


def test_news_records_never_carry_a_score_field():
    for item in news.parse_feed(RSS, "q"):
        assert not any(k in item for k in ("score", "band", "percentile", "pillar"))


# --- committed artifacts stay valid JSON ------------------------------------

def test_committed_news_file_is_wellformed_if_present():
    if not data_sync.NEWS_PATH.exists():
        pytest.skip("no news file in this checkout")
    items = json.loads(data_sync.NEWS_PATH.read_text())
    assert isinstance(items, list)
    assert len(items) <= news.MAX_ITEMS
    assert all(i.get("verified") is False for i in items)


# --- operational status: extraction, overlay, and honest defaults -----------

def test_osm_lifecycle_tags_map_to_status_buckets():
    f = osm_facilities.status_from_tags
    assert f({"building": "construction"})[0] == "construction"
    assert f({"construction:telecom": "data_center"})[0] == "construction"
    assert f({"landuse": "construction"})[0] == "construction"
    assert f({"proposed:telecom": "data_center"})[0] == "planned"
    assert f({"disused:telecom": "data_center"})[0] == "disused"


def test_untagged_facility_is_operational_but_marked_as_an_assumption():
    """OSM convention says a mapped feature exists, but 'the building exists'
    is not 'the data centre is in service'. The default must be traceable."""
    status, how = osm_facilities.status_from_tags({"telecom": "data_center"})
    assert status == "operational"
    assert how == "osm-default", "an assumed status must not look like an observation"


def test_explicit_lifecycle_status_is_marked_as_observed():
    assert osm_facilities.status_from_tags({"building": "construction"})[1] == "osm-lifecycle"


def test_construction_no_is_not_treated_as_under_construction():
    assert osm_facilities.status_from_tags({"construction": "no"})[0] == "operational"


def test_parsed_facilities_carry_status_and_its_provenance():
    rec = osm_facilities.parse_elements({"elements": [
        {"type": "node", "id": 1, "lat": 35.0, "lon": -90.0,
         "tags": {"telecom": "data_center", "building": "construction"}},
    ]})[0]
    assert rec["status"] == "construction"
    assert rec["status_source"] == "osm-lifecycle"


def test_curated_status_overrides_the_crowdsourced_guess():
    reg = [{"name": "osm", "lat": 35.0, "lon": -90.0,
            "status": "operational", "status_source": "osm-default"}]
    cur = [{"name": "curated", "lat": 35.001, "lon": -90.001,
            "status": "construction", "curated_status": "construction"}]
    assert data_sync.apply_curated_status(reg, cur) == 1
    assert reg[0]["status"] == "construction"
    assert reg[0]["status_source"] == "curated"


def test_curated_overlay_does_not_reach_a_distant_facility():
    reg = [{"name": "far", "lat": 40.0, "lon": -80.0,
            "status": "operational", "status_source": "osm-default"}]
    cur = [{"name": "c", "lat": 35.0, "lon": -90.0, "status": "construction"}]
    assert data_sync.apply_curated_status(reg, cur) == 0
    assert reg[0]["status_source"] == "osm-default"


def test_curated_registry_statuses_load_and_fold_to_map_buckets():
    got = data_sync.curated_statuses()
    if not got:
        pytest.skip("no curated registry in this checkout")
    assert {g["status"] for g in got} <= {"operational", "construction", "planned"}


def test_map_layer_is_prejected_and_counts_assumptions():
    facs = [
        {"name": "a", "lat": 35.0, "lon": -90.0, "status": "operational", "status_source": "osm-default"},
        {"name": "b", "lat": 36.0, "lon": -86.0, "status": "construction", "status_source": "curated"},
    ]
    layer = data_sync.build_map_layer(facs)
    assert layer["counts"] == {"operational": 1, "construction": 1}
    assert layer["assumed_operational"] == 1
    assert all(isinstance(p["x"], float) and isinstance(p["y"], float) for p in layer["points"])
    assert {p["s"] for p in layer["points"]} == {"o", "c"}
    assert [p["a"] for p in layer["points"] if p["n"] == "b"] == [1]


def test_map_layer_skips_facilities_without_coordinates():
    assert data_sync.build_map_layer([{"name": "x", "lat": None, "lon": None}])["points"] == []


def test_state_chunks_carry_status_for_local_filtering():
    facs = [{"osm_id": "n/1", "name": "a", "lat": 35.0, "lon": -90.0,
             "tract_geoid": "47157022220", "status": "planned", "status_source": "curated"}]
    chunk = data_sync.partition_by_state(facs, [])["47"]
    assert chunk["facilities"][0]["status"] == "planned"
    assert chunk["facilities"][0]["status_source"] == "curated"


def test_committed_map_layer_is_wellformed_if_present():
    if not data_sync.MAP_LAYER_PATH.exists():
        pytest.skip("map layer not built in this checkout")
    layer = json.loads(data_sync.MAP_LAYER_PATH.read_text())
    assert layer["points"], "an empty layer would blank the map"
    assert set(layer["counts"]) <= {"operational", "construction", "planned", "disused"}
    assert layer["assumed_operational"] <= layer["counts"].get("operational", 0)
    assert all(set(p) == {"n", "s", "a", "x", "y"} for p in layer["points"])


# --- declared ingestion boundaries ------------------------------------------

def test_boundaries_are_announced_every_run(caplog):
    """A silent absence is indistinguishable from an oversight."""
    import logging

    with caplog.at_level(logging.WARNING, logger="wattershed.sync"):
        got = data_sync.log_ingestion_boundaries()
    ids = {b["block_id"] for b in got}
    assert "water.usgs_realtime_hydrology" in ids
    assert "grid.eia_hourly_ba" in ids
    assert "structurally excluded" in caplog.text
    assert "contribute to NO score" in caplog.text


def test_every_boundary_states_a_reason():
    for b in data_sync.log_ingestion_boundaries():
        assert b["reason"], f"{b['block_id']} excluded without an explanation"
        assert b["stream"]


def test_boundary_log_reads_the_catalog_rather_than_restating_it():
    """If these drifted apart the log would become a second, stale truth."""
    from wattershed.sources.versioning import controller

    declared = {b.block_id for b in controller().uningested_declarations()}
    assert {b["block_id"] for b in data_sync.log_ingestion_boundaries()} == declared


def test_context_layers_are_named_as_scoreless_in_the_same_breath(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="wattershed.sync"):
        data_sync.log_ingestion_boundaries()
    assert "excluded from every pillar score by design" in caplog.text


def test_manifest_publishes_the_exclusions():
    """The exclusion must be a committed artifact, not just a CI log line."""
    report = data_sync.SyncReport()
    report.boundaries = data_sync.log_ingestion_boundaries()
    assert report.to_dict()["structurally_excluded"]


# --- masthead profile configuration -----------------------------------------

def test_configured_profile_renders_a_real_anchor():
    """Default is now the author's live profile, not the homepage placeholder."""
    from wattershed import config as cfg
    from wattershed.dashboard.build import _linkedin_anchor

    out = _linkedin_anchor()
    assert f'href="{cfg.LINKEDIN_URL}"' in out
    assert "/in/" in cfg.LINKEDIN_URL, "masthead must link a profile, not linkedin.com"


def test_reverting_to_the_homepage_placeholder_still_warns(caplog, monkeypatch):
    """The guard is retained so a regression to a homepage-only link is caught."""
    import logging

    from wattershed import config as cfg
    from wattershed.dashboard.build import _linkedin_anchor

    monkeypatch.setattr(cfg, "LINKEDIN_URL", cfg.LINKEDIN_PLACEHOLDER)
    with caplog.at_level(logging.WARNING, logger="wattershed.dashboard"):
        _linkedin_anchor()
    assert "placeholder" in caplog.text.lower()


def test_a_real_profile_url_is_embedded_without_warning(caplog, monkeypatch):
    import logging

    from wattershed import config as cfg
    from wattershed.dashboard.build import _linkedin_anchor

    monkeypatch.setattr(cfg, "LINKEDIN_URL", "https://www.linkedin.com/in/example/")
    with caplog.at_level(logging.WARNING, logger="wattershed.dashboard"):
        out = _linkedin_anchor()
    assert 'href="https://www.linkedin.com/in/example/"' in out
    assert "placeholder" not in caplog.text.lower()


def test_profile_url_is_html_escaped(monkeypatch):
    from wattershed import config as cfg
    from wattershed.dashboard.build import _linkedin_anchor

    monkeypatch.setattr(cfg, "LINKEDIN_URL", 'https://x.com/"><script>alert(1)</script>')
    out = _linkedin_anchor()
    assert "<script>" not in out


def test_empty_profile_url_omits_the_anchor_entirely(monkeypatch):
    from wattershed import config as cfg
    from wattershed.dashboard.build import _linkedin_anchor

    monkeypatch.setattr(cfg, "LINKEDIN_URL", "")
    assert _linkedin_anchor() == ""


# --- idempotence: no artifact may carry a wall-clock stamp ------------------

def test_map_layer_is_byte_stable_across_runs():
    """Regression: the layer embedded utc_now_iso(), so every sync rewrote it
    and manufactured a commit each cycle even when no upstream data moved."""
    facs = [{"name": "a", "lat": 35.0, "lon": -90.0,
             "status": "operational", "status_source": "osm-default"}]
    first = json.dumps(data_sync.build_map_layer(facs), sort_keys=True)
    second = json.dumps(data_sync.build_map_layer(facs), sort_keys=True)
    assert first == second
    assert "generated_at" not in first


def test_no_committed_sync_artifact_embeds_a_timestamp():
    """The run time belongs in the manifest — which is only written when
    something else actually changed — not in every artifact."""
    for path in (data_sync.MAP_LAYER_PATH, data_sync.STATE_CHUNK_DIR / "index.json"):
        if not path.exists():
            continue
        assert "generated_at" not in path.read_text(), (
            f"{path.name} carries a wall-clock stamp; it will differ on every "
            f"run and defeat change detection"
        )
