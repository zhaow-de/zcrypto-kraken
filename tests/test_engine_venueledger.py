from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cli.engine.errors import EngineJournalError
from cli.engine.venueledger import read_venue_record, validate_venue_record, venue_record_path, write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState

CYCLE_TS = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _state():
    return VenueState(
        snapshot_at=CYCLE_TS,
        instruments={
            "BTC/EUR": InstrumentConstraints(
                symbol="BTC/EUR",
                instrument_id="BTC/EUR.KRAKEN",
                ordermin=0.0001,
                costmin=0.5,
                costmin_quote="EUR",
                lot_step=0.00000001,
                tick_size=0.1,
            )
        },
        positions={"BTC/EUR": 0.0},
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
    validate_venue_record(doc)  # the writer's own output must validate under its declared schema
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
    validate_venue_record(doc)  # the writer's own output must validate under its declared schema
    assert doc["status"] == "error"
    assert doc["error"] == "cache read failed: BTC instrument not found"
    assert "state" not in doc
    assert "concordance" not in doc  # nothing to disagree with when there's no snapshot


def test_state_none_with_no_error_is_a_programming_error(tmp_path):
    with pytest.raises(ValueError):
        write_venue_record(tmp_path, CYCLE_TS, state=None, concordance=None, code_version="abc123")


def _v1_doc():
    """A schema_version 1 venue record, hand-built: base-keyed instruments/positions, entries
    carrying "base" (not "symbol") and no `costmin_quote` -- the shape written by code that predates
    spec 00094's key widening. No writer produces this shape any more (`write_venue_record` always
    stamps the current `VENUE_SCHEMA_VERSION`), so it is built directly here."""
    return {
        "schema_version": 1,
        "cycle_ts": CYCLE_TS.isoformat(),
        "code_version": "abc123",
        "status": "ok",
        "state": {
            "snapshot_at": CYCLE_TS.isoformat(),
            "instruments": {
                "BTC": {
                    "base": "BTC",
                    "instrument_id": "BTC/EUR.KRAKEN",
                    "ordermin": 0.0001,
                    "costmin": 0.5,
                    "lot_step": 0.00000001,
                    "tick_size": 0.1,
                    "costmin_source": "snapshot-constant",
                }
            },
            "positions": {"BTC": 0.0},
            "balances": {"EUR": 1000.0},
        },
        "concordance": {"ok": True, "failures": []},
    }


def test_a_schema2_record_with_base_keys_is_refused(tmp_path):
    p = write_venue_record(tmp_path, CYCLE_TS, state=_state(), concordance=_concordance(), code_version="abc123")
    doc = read_venue_record(p)
    doc["state"]["instruments"] = {"BTC": doc["state"]["instruments"]["BTC/EUR"]}
    doc["state"]["positions"] = {"BTC": 0.0}
    with pytest.raises(EngineJournalError):
        validate_venue_record(doc)


def test_a_v1_record_validates_in_its_own_shape():
    doc = _v1_doc()  # helper: schema_version 1, base-keyed, entries carry "base", no costmin_quote
    validate_venue_record(doc)  # must not raise
    doc["state"]["instruments"]["BTC"]["costmin_quote"] = "EUR"
    with pytest.raises(EngineJournalError):
        validate_venue_record(doc)


def test_unknown_schema_is_refused():
    doc = _v1_doc()
    doc["schema_version"] = 3
    with pytest.raises(EngineJournalError):
        validate_venue_record(doc)
