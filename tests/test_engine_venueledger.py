from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cli.engine.venueledger import VENUE_SCHEMA_VERSION, read_venue_record, venue_record_path, write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState

CYCLE_TS = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _state():
    return VenueState(
        snapshot_at=CYCLE_TS,
        instruments={
            "BTC": InstrumentConstraints(
                base="BTC",
                instrument_id="XBTEUR.KRAKEN",
                ordermin=0.0001,
                costmin=0.5,
                lot_step=0.00000001,
                tick_size=0.1,
            )
        },
        positions={"BTC": 0.0},
        balances={"EUR": 1000.0},
    )


def _concordance():
    return ConcordanceVerdict(ok=True, failures=())


def test_the_record_lands_beside_the_cycle_record_and_is_named_for_the_hour(tmp_path):
    p = write_venue_record(tmp_path, CYCLE_TS, state=_state(), concordance=_concordance(), code_version="abc123")
    assert p == venue_record_path(tmp_path, CYCLE_TS) == tmp_path / "2026-08-11" / "venue-12.json"
    assert p.exists()


def test_a_success_record_round_trips_state_and_concordance(tmp_path):
    p = write_venue_record(tmp_path, CYCLE_TS, state=_state(), concordance=_concordance(), code_version="abc123")
    doc = read_venue_record(p)
    assert doc["schema_version"] == VENUE_SCHEMA_VERSION
    assert doc["cycle_ts"] == CYCLE_TS.isoformat()
    assert doc["code_version"] == "abc123"
    assert doc["status"] == "ok"
    assert doc["state"] == _state().to_payload()
    assert doc["concordance"] == {"ok": True, "failures": []}


def test_an_error_record_carries_the_reason_and_no_state_key(tmp_path):
    p = write_venue_record(
        tmp_path,
        CYCLE_TS,
        state=None,
        concordance=None,
        code_version="abc123",
        error="cache read failed: BTC instrument not found",
    )
    doc = read_venue_record(p)
    assert doc["schema_version"] == VENUE_SCHEMA_VERSION
    assert doc["status"] == "error"
    assert doc["error"] == "cache read failed: BTC instrument not found"
    assert "state" not in doc
    assert "concordance" not in doc  # nothing to disagree with when there's no snapshot


def test_state_none_with_no_error_is_a_programming_error(tmp_path):
    with pytest.raises(ValueError):
        write_venue_record(tmp_path, CYCLE_TS, state=None, concordance=None, code_version="abc123")
