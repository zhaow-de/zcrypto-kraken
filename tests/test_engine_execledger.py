from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.execgate import GateLevel, GateVerdict
from cli.engine.execledger import (
    EXEC_SCHEMA_VERSION,
    append_plan_entry,
    append_submitted_row,
    exec_record_path,
    ledgered_intent_keys,
    ledgered_plan_ids,
    open_submitted_rows,
    read_exec_record,
    update_plan_intent,
    update_submitted_row,
    validate_exec_record,
    write_exec_record,
)
from cli.engine.venueledger import write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState

CYCLE_TS = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _verdict():
    return GateVerdict(
        level=GateLevel.NONE,
        reasons=("arm_file_absent", "restart_hold"),
        inputs={"armed_in_config": False, "venue_status": "online"},
    )


def _row(*, plan_id="plan-1", intent_index=0, client_order_id="coid-1", state="submitting"):
    return {
        "plan_id": plan_id,
        "intent_index": intent_index,
        "client_order_id": client_order_id,
        "intent": {},
        "order": {
            "side": "buy",
            "qty": 0.001,
            "price": 50000.0,
            "time_in_force": "GTC",
            "post_only": False,
            "reduce_only": False,
            "leverage": None,
        },
        "state": state,
        "filled_qty": 0.0,
        "events": [],
    }


def _v1_doc():
    return {
        "schema_version": 1,
        "cycle_ts": CYCLE_TS.isoformat(),
        "evaluated_at": CYCLE_TS.isoformat(),
        "level": "none",
        "reasons": [],
        "inputs": {},
        "submitted": [],
    }


def _v2_doc():
    doc = _v1_doc()
    doc["schema_version"] = 2
    doc["plans"] = []
    return doc


def _refused_plan_entry(*, plan_id="plan-2"):
    return {
        "plan_id": plan_id,
        "received_at": CYCLE_TS.isoformat(),
        "disposition": "refused",
        "reasons": ["some_reason"],
        "plan": {},
        "intents": [],
    }


def _venue_state():
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


def _write_exec_record(journal_dir, cycle_ts):
    return write_exec_record(journal_dir, cycle_ts, _verdict(), evaluated_at=cycle_ts)


def _write_venue_record(journal_dir, cycle_ts):
    return write_venue_record(
        journal_dir, cycle_ts, state=_venue_state(), concordance=ConcordanceVerdict(ok=True, failures=()), code_version="test"
    )


# Both journaled-outcome ledgers (exec: spec 00088, venue: spec 00089) share the same
# gate-invisibility property and the same reason it holds -- parametrized here rather than
# duplicated in a second fixture.
_LEDGER_PREFIXES = pytest.mark.parametrize("prefix,write_record", [("exec", _write_exec_record), ("venue", _write_venue_record)])


def test_the_record_lands_beside_the_cycle_record_and_is_named_for_the_hour(tmp_path):
    p = write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    assert p == tmp_path / "2026-08-11" / "exec-12.json"
    assert p.exists()


def test_the_record_carries_the_verdict_its_reasons_and_an_empty_submission_list(tmp_path):
    p = write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    doc = json.loads(p.read_text())
    assert doc["schema_version"] == EXEC_SCHEMA_VERSION
    assert doc["level"] == "none"
    assert doc["reasons"] == ["arm_file_absent", "restart_hold"]
    assert doc["submitted"] == []  # by construction in this spec: nothing can submit
    assert doc["inputs"]["venue_status"] == "online"


def test_round_trips(tmp_path):
    p = write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    assert read_exec_record(p)["level"] == "none"


@_LEDGER_PREFIXES
def test_exec_records_are_invisible_to_every_journal_glob(tmp_path, prefix, write_record):
    """The load-bearing invariant of this whole spec, tested where it actually lives.

    `evaluate_gate` takes a list of CycleOutcome objects, NOT a directory -- it never globs at all,
    so testing it directly would prove nothing. The globbing is `cli/engine/command.py`'s
    `_journal_artifacts`, and it derives the hour from `path.stem.rsplit("-", 1)[-1]`: `exec-12`
    yields "12", a perfectly valid boundary. The ONLY thing keeping an exec/venue record out of the
    concordance universe is that every call site globs `cycle-*.json` / `failed-cycle-*.json` and
    neither prefix is that. This test is what keeps that true, for both ledgers (spec 00088's exec,
    spec 00089's venue).

    (There are eight `_journal_artifacts` call sites -- seven in `cli/engine/command.py`, one in
    `cli/engine/soak.py` -- plus `cli/engine/cycle.py`'s own direct `*/cycle-*.json` back-search.
    Verify by grep rather than trusting this count, which rots.)
    """
    from cli.engine.command import _journal_artifacts

    day = tmp_path / "2026-08-11"
    day.mkdir(parents=True)
    for hh in (0, 4, 8, 12, 16, 20):
        (day / f"cycle-{hh:02d}.json").write_text("{}")
        write_record(tmp_path, CYCLE_TS.replace(hour=hh))

    # Non-vacuity first: the fixture really did write records next to the cycle records.
    assert len(list(day.glob(f"{prefix}-*.json"))) == 6

    records = _journal_artifacts(tmp_path, "*", "cycle-*.json")
    sidecars = _journal_artifacts(tmp_path, "*", "failed-cycle-*.json")
    assert len(records) == 6
    assert sidecars == []
    assert all(prefix not in p.name for _, p in records)


@_LEDGER_PREFIXES
def test_the_exec_prefix_would_be_swept_up_by_a_looser_glob(tmp_path, prefix, write_record):
    """Guards the reason the test above passes, so a future `*.json` glob fails loudly here
    rather than silently resetting the streak. If this test ever needs changing, the change is a
    decision about the concordance universe -- not a test fix."""
    from cli.engine.command import _journal_artifacts

    day = tmp_path / "2026-08-11"
    day.mkdir(parents=True)
    write_record(tmp_path, CYCLE_TS)
    swept = _journal_artifacts(tmp_path, "*", "*.json")
    assert len(swept) == 1  # a loose glob DOES pick it up, with a parsed boundary
    assert swept[0][0].hour == 12


# --- schema 2: write-ahead rows, merge-never-clobber, schema-aware validation -----------------------


def test_the_sink_merge_never_clobbers_submitted_rows(tmp_path):
    """D5's merge-never-clobber, byte-for-byte: a per-cycle verdict write over a record already
    carrying submitted rows and plan entries preserves both lists exactly."""
    write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    row = _row()  # helper: one submitting-state row with the exact key set
    append_submitted_row(tmp_path, CYCLE_TS, row, verdict=_verdict(), evaluated_at=CYCLE_TS)
    before = read_exec_record(exec_record_path(tmp_path, CYCLE_TS))
    write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS + timedelta(minutes=5))
    after = read_exec_record(exec_record_path(tmp_path, CYCLE_TS))
    assert after["submitted"] == before["submitted"]
    assert after["plans"] == before["plans"]
    assert after["evaluated_at"] == (CYCLE_TS + timedelta(minutes=5)).isoformat()


def test_a_v1_record_with_a_populated_submitted_list_is_refused():
    doc = _v1_doc()  # the 7 exact v1 keys, submitted=[]
    doc["submitted"] = [_row()]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_v2_record_without_the_plans_key_is_refused():
    doc = _v2_doc()
    del doc["plans"]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_v1_record_validates_in_its_own_shape():
    validate_exec_record(_v1_doc())  # must not raise


def test_unknown_schema_is_refused():
    doc = _v2_doc()
    doc["schema_version"] = 3
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_v2_record_with_a_populated_plans_list_validates():
    doc = _v2_doc()
    doc["plans"] = [_refused_plan_entry()]
    validate_exec_record(doc)  # must not raise


def test_a_submitted_row_with_a_missing_key_is_refused():
    doc = _v2_doc()
    row = _row()
    del row["events"]
    doc["submitted"] = [row]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_plan_entry_with_an_extra_key_is_refused():
    doc = _v2_doc()
    entry = _refused_plan_entry()
    entry["extra"] = True
    doc["plans"] = [entry]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_non_list_events_on_a_row_is_refused():
    doc = _v2_doc()
    row = _row()
    row["events"] = "not-a-list"
    doc["submitted"] = [row]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_non_list_reasons_on_the_doc_is_refused():
    doc = _v2_doc()
    doc["reasons"] = "not-a-list"
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_merge_over_a_v1_on_disk_record_upgrades_to_v2(tmp_path):
    path = exec_record_path(tmp_path, CYCLE_TS)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_v1_doc()))
    write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    doc = read_exec_record(path)
    assert doc["schema_version"] == 2
    assert doc["plans"] == []
    assert doc["submitted"] == []


def test_an_unparseable_existing_file_makes_write_exec_record_raise_and_leaves_bytes_untouched(tmp_path):
    path = exec_record_path(tmp_path, CYCLE_TS)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    with pytest.raises(EngineError):
        write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    assert path.read_text() == "{not json"


def test_update_submitted_row_appends_event_sets_state_and_adds_filled_qty(tmp_path):
    row = _row()
    append_submitted_row(tmp_path, CYCLE_TS, row, verdict=_verdict(), evaluated_at=CYCLE_TS)
    event = {"type": "fill", "qty": 0.0005}
    update_submitted_row(tmp_path, CYCLE_TS, row["client_order_id"], state="filled", event=event, add_filled_qty=0.0005)
    doc = read_exec_record(exec_record_path(tmp_path, CYCLE_TS))
    updated = doc["submitted"][0]
    assert updated["state"] == "filled"
    assert updated["events"] == [event]
    assert updated["filled_qty"] == 0.0005


def test_update_submitted_row_raises_on_an_unknown_client_order_id(tmp_path):
    append_submitted_row(tmp_path, CYCLE_TS, _row(), verdict=_verdict(), evaluated_at=CYCLE_TS)
    with pytest.raises(EngineError):
        update_submitted_row(tmp_path, CYCLE_TS, "does-not-exist", state="filled")


def test_update_submitted_row_raises_when_the_record_is_absent(tmp_path):
    with pytest.raises(EngineError):
        update_submitted_row(tmp_path, CYCLE_TS, "coid-1", state="filled")


def test_append_plan_entry_and_update_plan_intent(tmp_path):
    entry = _refused_plan_entry()
    entry["intents"] = [{"index": 0, "outcome": "pending", "reasons": [], "filled_qty": 0.0}]
    append_plan_entry(tmp_path, CYCLE_TS, entry, verdict=_verdict(), evaluated_at=CYCLE_TS)
    update_plan_intent(tmp_path, CYCLE_TS, entry["plan_id"], 0, outcome="filled", reasons=("ok",), filled_qty=0.001)
    doc = read_exec_record(exec_record_path(tmp_path, CYCLE_TS))
    intent = doc["plans"][0]["intents"][0]
    assert intent["outcome"] == "filled"
    assert intent["reasons"] == ["ok"]
    assert intent["filled_qty"] == 0.001


def test_update_plan_intent_raises_on_an_unknown_plan_id(tmp_path):
    append_plan_entry(tmp_path, CYCLE_TS, _refused_plan_entry(), verdict=_verdict(), evaluated_at=CYCLE_TS)
    with pytest.raises(EngineError):
        update_plan_intent(tmp_path, CYCLE_TS, "does-not-exist", 0, outcome="filled")


def test_update_plan_intent_raises_on_an_unknown_index(tmp_path):
    entry = _refused_plan_entry()
    entry["intents"] = [{"index": 0, "outcome": "pending", "reasons": [], "filled_qty": 0.0}]
    append_plan_entry(tmp_path, CYCLE_TS, entry, verdict=_verdict(), evaluated_at=CYCLE_TS)
    with pytest.raises(EngineError):
        update_plan_intent(tmp_path, CYCLE_TS, entry["plan_id"], 7, outcome="filled")


def test_ledger_scans_include_yesterday_and_exclude_the_day_before(tmp_path):
    """`ledgered_plan_ids`/`ledgered_intent_keys`/`open_submitted_rows` all window over the current
    and previous UTC day only."""
    now = CYCLE_TS + timedelta(days=1)
    today_ts, yesterday_ts, day_before_ts = now, CYCLE_TS, CYCLE_TS - timedelta(days=1)

    append_submitted_row(
        tmp_path,
        today_ts,
        _row(plan_id="today-plan", intent_index=0, client_order_id="coid-today"),
        verdict=_verdict(),
        evaluated_at=today_ts,
    )
    append_submitted_row(
        tmp_path,
        yesterday_ts,
        _row(plan_id="yesterday-plan", intent_index=1, client_order_id="coid-yesterday"),
        verdict=_verdict(),
        evaluated_at=yesterday_ts,
    )
    append_submitted_row(
        tmp_path,
        day_before_ts,
        _row(plan_id="day-before-plan", intent_index=2, client_order_id="coid-day-before"),
        verdict=_verdict(),
        evaluated_at=day_before_ts,
    )
    append_plan_entry(tmp_path, today_ts, _refused_plan_entry(plan_id="today-refused"), verdict=_verdict(), evaluated_at=today_ts)

    plan_ids = ledgered_plan_ids(tmp_path, now)
    assert plan_ids == {"today-plan", "today-refused", "yesterday-plan"}

    intent_keys = ledgered_intent_keys(tmp_path, now)
    assert intent_keys == {("today-plan", 0), ("yesterday-plan", 1)}

    open_coids = {row["client_order_id"] for _, row in open_submitted_rows(tmp_path, now)}
    assert open_coids == {"coid-today", "coid-yesterday"}


def test_a_corrupt_exec_record_makes_the_ledger_scan_raise(tmp_path):
    day = tmp_path / f"{CYCLE_TS:%Y-%m-%d}"
    day.mkdir(parents=True)
    (day / "exec-00.json").write_text("{not json")
    with pytest.raises(EngineError):
        ledgered_plan_ids(tmp_path, CYCLE_TS)


def test_populated_exec_records_leave_the_report_byte_identical(tmp_path, monkeypatch):
    """A synthetic day of cycle records scores IDENTICALLY with and without exec records that
    carry submitted rows, plan entries and refusals -- through cli.engine.command's real
    _evaluate_journal/report path, never a hand-called evaluate_gate."""
    from typer.testing import CliRunner

    import cli.engine.command as command
    from cli.__main__ import app

    day = tmp_path / "2026-08-11"
    day.mkdir(parents=True)
    for hh in (0, 4, 8, 12, 16, 20):
        (day / f"cycle-{hh:02d}.json").write_text("{not json")  # classifies validation_failed -- deterministic
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(days=1))
    runner = CliRunner()
    args = ["engine", "report", "--journal-dir", str(tmp_path)]
    without = runner.invoke(app, args)
    for hh in (0, 4, 8, 12, 16, 20):
        p = append_submitted_row(tmp_path, CYCLE_TS.replace(hour=hh), _row(), verdict=_verdict(), evaluated_at=CYCLE_TS)
        append_plan_entry(tmp_path, CYCLE_TS.replace(hour=hh), _refused_plan_entry(), verdict=_verdict(), evaluated_at=CYCLE_TS)
        assert p.exists()
    with_records = runner.invoke(app, args)
    assert with_records.output == without.output
    assert with_records.exit_code == without.exit_code
