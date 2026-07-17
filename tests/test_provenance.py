import pytest

from wattershed.provenance import SOURCES, Ledger


def test_every_source_fully_documented():
    for sid, s in SOURCES.items():
        assert s.name and s.provider and s.url, sid
        assert s.vintage, f"{sid} missing vintage"
        assert s.license, f"{sid} missing license"


def test_ledger_rejects_unknown_source():
    with pytest.raises(KeyError):
        Ledger().touch("not-a-source")


def test_ledger_records():
    led = Ledger()
    led.touch("egrid2023")
    recs = led.to_records()
    assert len(recs) == 1
    assert recs[0]["provider"] == "U.S. EPA"
    assert recs[0]["retrieved"]
