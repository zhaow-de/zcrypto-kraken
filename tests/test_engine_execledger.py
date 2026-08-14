from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from cli.engine.execgate import GateLevel, GateVerdict
from cli.engine.execledger import EXEC_SCHEMA_VERSION, read_exec_record, write_exec_record
from cli.engine.venueledger import write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState

CYCLE_TS = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _verdict():
    return GateVerdict(
        level=GateLevel.NONE,
        reasons=("arm_file_absent", "restart_hold"),
        inputs={"armed_in_config": False, "venue_status": "online"},
    )


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
