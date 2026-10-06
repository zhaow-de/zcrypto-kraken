from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cli.engine.accumledger import (
    accum_record_path,
    accum_records_since,
    read_accum_record,
    validate_accum_record,
    write_accum_record,
)
from cli.engine.errors import EngineJournalError

# The immunity case's day dir, `2026-11-09`, is this boundary's date: the records it writes land beside its cycle files.
CYCLE_TS = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

_RECORD_FIGURES = ("nav", "eur_total", "eur_free", "equity_eur", "hwm_eur", "drawdown_bps", "day_loss_bps")
_LEG_FIGURES = ("weight", "target_eur", "close", "held_qty", "cache_net", "delta_eur", "qty", "notional_eur")
_LEG_FIGURES_ALWAYS_SET = ("weight", "target_eur", "close", "held_qty", "cache_net", "delta_eur")


def _leg(symbol, *, weight, close, held_qty, delta_eur, outcome, side=None, qty=None, notional_eur=None, reason=""):
    return {
        "symbol": symbol,
        "weight": weight,
        "target_eur": weight * 1000.0,
        "close": close,
        "held_qty": held_qty,
        "cache_net": held_qty,
        "delta_eur": delta_eur,
        "outcome": outcome,
        "side": side,
        "qty": qty,
        "notional_eur": notional_eur,
        "reason": reason,
    }


def _ok_doc(cycle_ts):
    return {
        "schema_version": 1,
        "cycle_ts": cycle_ts.isoformat(),
        "drafted_at": (cycle_ts + timedelta(minutes=1)).isoformat(),
        "status": "ok",
        "nav": 1000.0,
        "eur_total": 1443.0,
        "eur_free": 1300.0,
        "equity_eur": 1630.0,
        "hwm_eur": 1650.0,
        "drawdown_bps": 200.0,
        "day_loss_bps": 50.0,
        "day_loss_hold": False,
        "plan_id": f"r3-{cycle_ts:%Y%m%d-%H}",
        "legs": [
            _leg(
                "BTC/EUR",
                weight=0.12,
                close=60000.0,
                held_qty=0.001,
                delta_eur=60.0,
                outcome="placed",
                side="buy",
                notional_eur=60.0,
            ),
            _leg("ETH/EUR", weight=0.05, close=2500.0, held_qty=0.032, delta_eur=-30.0, outcome="placed", side="sell", qty=0.012),
            _leg(
                "SOL/EUR",
                weight=0.03,
                close=150.0,
                held_qty=0.18,
                delta_eur=3.0,
                outcome="carried",
                reason="the delta is under the pair's ordermin; it carries to the next boundary",
            ),
            _leg("XRP/EUR", weight=0.02, close=2.0, held_qty=10.0, delta_eur=0.0, outcome="on-target"),
        ],
    }


def _no_cycle_doc(cycle_ts):
    doc = _ok_doc(cycle_ts)
    doc.update(dict.fromkeys(_RECORD_FIGURES), status="no-cycle", plan_id=None, legs=[])
    return doc


def test_the_record_lands_in_the_day_dir_named_for_the_hour(tmp_path):
    path = write_accum_record(tmp_path, CYCLE_TS, _ok_doc(CYCLE_TS))
    assert path == accum_record_path(tmp_path, CYCLE_TS) == tmp_path / "2026-11-09" / "accum-12.json"


def test_an_ok_record_round_trips_in_the_sibling_ledgers_spelling(tmp_path):
    doc = _ok_doc(CYCLE_TS)
    path = write_accum_record(tmp_path, CYCLE_TS, doc)
    assert read_accum_record(path) == doc
    assert path.read_text() == json.dumps(doc, indent=2, sort_keys=True)


def test_a_no_cycle_record_with_no_figures_and_no_legs_round_trips(tmp_path):
    doc = _no_cycle_doc(CYCLE_TS)
    assert read_accum_record(write_accum_record(tmp_path, CYCLE_TS, doc)) == doc


def test_a_schema_version_other_than_1_is_refused():
    doc = _ok_doc(CYCLE_TS)
    doc["schema_version"] = 2
    with pytest.raises(EngineJournalError, match="schema_version"):
        validate_accum_record(doc)


def test_a_record_missing_a_key_is_refused():
    doc = _ok_doc(CYCLE_TS)
    del doc["drafted_at"]
    with pytest.raises(EngineJournalError, match="accum record keys"):
        validate_accum_record(doc)


def test_a_record_carrying_a_stray_key_is_refused():
    doc = _ok_doc(CYCLE_TS)
    doc["note"] = "drafted by hand"
    with pytest.raises(EngineJournalError, match="accum record keys"):
        validate_accum_record(doc)


def test_a_status_outside_the_five_is_refused():
    doc = _ok_doc(CYCLE_TS)
    doc["status"] = "pending"
    with pytest.raises(EngineJournalError, match="status"):
        validate_accum_record(doc)


def test_legs_that_are_not_a_list_are_refused():
    doc = _ok_doc(CYCLE_TS)
    doc["legs"] = {leg["symbol"]: leg for leg in doc["legs"]}
    with pytest.raises(EngineJournalError, match="'legs' must be a list"):
        validate_accum_record(doc)


def test_a_leg_missing_a_key_is_refused():
    doc = _ok_doc(CYCLE_TS)
    for leg in doc["legs"]:
        del leg["reason"]
    with pytest.raises(EngineJournalError, match="accum leg keys"):
        validate_accum_record(doc)


def test_a_leg_carrying_a_stray_key_is_refused():
    doc = _ok_doc(CYCLE_TS)
    doc["legs"][0]["filled_qty"] = 0.0
    with pytest.raises(EngineJournalError, match="accum leg keys"):
        validate_accum_record(doc)


@pytest.mark.parametrize("field", _RECORD_FIGURES)
def test_a_non_finite_record_figure_is_refused(field):
    doc = _ok_doc(CYCLE_TS)
    doc[field] = float("nan")
    with pytest.raises(EngineJournalError, match=field):
        validate_accum_record(doc)


@pytest.mark.parametrize("field", _LEG_FIGURES)
def test_a_non_finite_leg_figure_is_refused(field):
    doc = _ok_doc(CYCLE_TS)
    doc["legs"][1][field] = float("inf")
    with pytest.raises(EngineJournalError, match=field):
        validate_accum_record(doc)


@pytest.mark.parametrize("field", _LEG_FIGURES_ALWAYS_SET)
def test_a_null_leg_figure_other_than_qty_and_notional_is_refused(field):
    doc = _ok_doc(CYCLE_TS)
    doc["legs"][0][field] = None
    with pytest.raises(EngineJournalError, match=field):
        validate_accum_record(doc)


@pytest.mark.parametrize("value", [None, 0])
def test_a_day_loss_hold_that_is_not_a_bool_is_refused(value):
    doc = _ok_doc(CYCLE_TS)
    doc["day_loss_hold"] = value
    with pytest.raises(EngineJournalError, match="day_loss_hold"):
        validate_accum_record(doc)


def test_a_malformed_record_never_lands_and_the_boundarys_record_stands(tmp_path):
    good = _ok_doc(CYCLE_TS)
    path = write_accum_record(tmp_path, CYCLE_TS, good)
    bad = _ok_doc(CYCLE_TS)
    bad["status"] = "pending"
    with pytest.raises(EngineJournalError):
        write_accum_record(tmp_path, CYCLE_TS, bad)
    assert read_accum_record(path) == good
    assert sorted(p.name for p in path.parent.iterdir()) == ["accum-12.json"]


def test_the_window_reader_returns_the_records_from_since_to_until_in_boundary_order(tmp_path):
    until = CYCLE_TS + timedelta(hours=20)
    boundaries = [CYCLE_TS + timedelta(hours=4 * i) for i in range(-4, 7)]  # 2026-11-08 20Z to 2026-11-10 12Z
    for boundary in reversed(boundaries):
        write_accum_record(tmp_path, boundary, _ok_doc(boundary))

    records = accum_records_since(tmp_path, CYCLE_TS, until)

    assert [datetime.fromisoformat(r["cycle_ts"]) for r in records] == [b for b in boundaries if CYCLE_TS <= b <= until]
    assert records[0] == _ok_doc(CYCLE_TS) and records[-1] == _ok_doc(until)


def test_a_day_dir_before_sinces_date_is_never_opened(tmp_path):
    day_before = tmp_path / f"{CYCLE_TS - timedelta(days=1):%Y-%m-%d}"
    day_before.mkdir(parents=True)
    (day_before / "accum-20.json").write_text("{not json")
    write_accum_record(tmp_path, CYCLE_TS, _ok_doc(CYCLE_TS))
    assert accum_records_since(tmp_path, CYCLE_TS, CYCLE_TS) == [_ok_doc(CYCLE_TS)]


def test_an_unreadable_record_in_the_window_makes_the_reader_raise(tmp_path):
    write_accum_record(tmp_path, CYCLE_TS, _ok_doc(CYCLE_TS))
    accum_record_path(tmp_path, CYCLE_TS + timedelta(hours=4)).write_text("{not json")
    with pytest.raises(EngineJournalError, match="accum-16.json"):
        accum_records_since(tmp_path, CYCLE_TS, CYCLE_TS + timedelta(hours=8))


def test_a_record_that_will_not_validate_makes_the_reader_raise(tmp_path):
    write_accum_record(tmp_path, CYCLE_TS, _ok_doc(CYCLE_TS))
    broken = _ok_doc(CYCLE_TS + timedelta(hours=4))
    broken["status"] = "pending"
    accum_record_path(tmp_path, CYCLE_TS + timedelta(hours=4)).write_text(json.dumps(broken))
    with pytest.raises(EngineJournalError, match="status"):
        accum_records_since(tmp_path, CYCLE_TS, CYCLE_TS + timedelta(hours=8))


def test_accum_records_leave_the_report_byte_identical(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import cli.engine.command as command
    from cli.__main__ import app

    day = tmp_path / "2026-11-09"
    day.mkdir(parents=True)
    for hh in (0, 4, 8, 12, 16, 20):
        (day / f"cycle-{hh:02d}.json").write_text("{not json")
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(days=1))
    runner = CliRunner()
    args = ["engine", "report", "--journal-dir", str(tmp_path)]
    without = runner.invoke(app, args)
    for hh in (0, 4, 8, 12, 16, 20):
        write_accum_record(tmp_path, CYCLE_TS.replace(hour=hh), _ok_doc(CYCLE_TS.replace(hour=hh)))
    with_records = runner.invoke(app, args)
    assert with_records.output == without.output and with_records.exit_code == without.exit_code
