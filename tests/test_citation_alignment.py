"""Citation alignment: one verified edition, cited identically everywhere.

Background: the NERC assessment was simultaneously documented as "published
Dec 2025" (provenance.py) and "pub. Jan 2026" (DATA_SOURCES.md, nerc.py,
cli.py), with two different horizons (2026-2035 vs a "2026-2030 window").
Verified 2026-08-21: the PDF is titled "Long-Term Reliability Assessment,
January 2026", released 2026-01-29, and the transcribed risk table in
data/reference/nerc_ltra.csv carries designations through 2035 — so January
2026 and 2026-2035 are correct, and the other variants were wrong.

The structural fix is provenance.NERC_LTRA_*: declared once, imported by every
consumer. These tests fail the build if a stray literal reappears, which is
what let the two versions diverge in the first place.
"""

from pathlib import Path

import pytest

from wattershed import provenance
from wattershed.provenance import (
    NERC_LTRA_HORIZON,
    NERC_LTRA_PUBLISHED,
    NERC_LTRA_PUBLISHED_ISO,
    NERC_LTRA_URL,
    NERC_LTRA_VINTAGE,
)

REPO = Path(__file__).resolve().parent.parent
SCANNED = sorted(
    [p for p in (REPO / "src").rglob("*.py")]
    + [p for p in (REPO / "docs").glob("*.md")]
    + [REPO / "README.md"]
)

# Claims that contradict the verified citation. Each maps to why it is wrong.
SUPERSEDED = {
    "Dec 2025": "LTRA was published January 2026, not December 2025",
    "December 2025": "LTRA was published January 2026, not December 2025",
    "2026–2030": "the assessment horizon is 2026-2035; the transcribed table runs to 2035",
    "2026-2030": "the assessment horizon is 2026-2035; the transcribed table runs to 2035",
}

NON_CANONICAL_URL = "nerc.com/pa/RAPA"


def test_canonical_constants_are_internally_consistent():
    assert NERC_LTRA_PUBLISHED_ISO == "2026-01"
    assert NERC_LTRA_PUBLISHED == "January 2026"
    assert NERC_LTRA_HORIZON == "2026–2035"
    assert NERC_LTRA_PUBLISHED in NERC_LTRA_VINTAGE
    assert NERC_LTRA_HORIZON in NERC_LTRA_VINTAGE


def test_the_registered_source_uses_the_canonical_constants():
    src = provenance.SOURCES["nerc_ltra_2025"]
    assert src.vintage == NERC_LTRA_VINTAGE
    assert src.url == NERC_LTRA_URL


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: str(p.relative_to(REPO)))
def test_no_file_repeats_a_superseded_nerc_claim(path):
    """Any file mentioning the LTRA must not carry a contradicting date."""
    text = path.read_text(encoding="utf-8")
    if "LTRA" not in text and "NERC" not in text:
        return
    for bad, why in SUPERSEDED.items():
        # This test file quotes the superseded strings deliberately.
        if path.name == "test_citation_alignment.py":
            continue
        assert bad not in text, f"{path.relative_to(REPO)} still claims {bad!r} — {why}"


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: str(p.relative_to(REPO)))
def test_no_file_uses_the_non_canonical_nerc_url(path):
    text = path.read_text(encoding="utf-8")
    assert NON_CANONICAL_URL not in text, (
        f"{path.relative_to(REPO)} uses the legacy /pa/RAPA/ URL; both resolve, "
        f"but citations must point at one canonical location"
    )


def test_the_scorer_stamps_the_canonical_vintage_on_its_indicator():
    from wattershed.scoring.grid import score_grid

    g = score_grid(
        egrid_stats=None,
        nerc_risk={"score": 90.0, "area": "MISO", "category": "high",
                   "first_high_year": 2028, "map_confidence": "high"},
        load_share_pct=None,
    )
    ind = next(i for i in g.indicators if i.id == "nerc_ltra_risk")
    assert ind.vintage == NERC_LTRA_VINTAGE


def test_the_catalog_publishes_the_canonical_publication_date():
    from wattershed.sources.catalog import build_catalog

    blocks = build_catalog()["pillars"]["grid"]["blocks"]
    nerc = next(b for b in blocks if b["block_id"] == "grid.resource_adequacy")
    assert nerc["published"] == NERC_LTRA_PUBLISHED_ISO
    assert NERC_LTRA_HORIZON in nerc["describes"]


def test_docs_row_agrees_with_the_registry():
    doc = (REPO / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
    row = next(ln for ln in doc.splitlines() if "NERC 2025 Long-Term" in ln)
    assert NERC_LTRA_HORIZON in row, "docs horizon disagrees with the registry"
    assert "Jan 2026" in row or NERC_LTRA_PUBLISHED in row
    assert NERC_LTRA_URL in row
