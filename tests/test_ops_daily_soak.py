"""TDD for the soak verdict: `infra/scripts/ops_daily.py`'s scheduled reader of `zcrypto engine soak-check`,
the journal-derived store it hands that command, and the runner that produces the payload. Split out of
`tests/test_ops_daily.py`, which still names both scripts for `tests/test_scripts_have_tests.py` and still holds
the payload builders, because three of its own report cases stub `soak_run` with them.

The autouse refusal comes with them: imported, not copied, so the refusal every test in both files gets has one
definition to narrow."""

from __future__ import annotations

import dataclasses
import inspect
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_ops_daily import (
    _SOAK_METRICS,
    _SOAK_NOW,
    _a_current_soak_payload,
    _host_answering,
    _report,
    _soak_answering,
    _soak_payload,
    live_soak_run,  # noqa: F401 -- autouse: this import is what registers it in this module
    ops_daily,
)


def test_one_metric_outside_is_the_count_chance_expects_and_passes():
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload()))
    assert check.ok, check.value
    assert check.value == (
        "1 of 7 outside band (~0.7 expected by chance at 90%); L=424 to 2026-09-19T08:00:00+00:00, "
        "window_bound=journal; self-test ok/ok/ok; outside: governor_engagement (one construction); "
        "no-book bars 0 of 424; hhi consistent"
    )


def test_a_metric_judged_under_one_null_alone_carries_no_dual_and_is_still_read():
    """`soak-check` writes a `None` dual for every metric under a single-null run, and for the two internals
    metrics whenever the rebuild is unavailable. The row reads that metric's own verdict as the one
    construction it was; a reduction that subscripted the dual would read the whole payload as unreadable."""
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload(no_dual=("governor_engagement",))))
    assert check.ok, check.value
    assert "outside: governor_engagement (one construction)" in check.value


def test_the_row_fails_at_the_provisional_count_and_not_one_below_it():
    assert ops_daily.SOAK_OUTSIDE_FAILS_AT == 3
    two = _soak_payload(outside=("governor_engagement",), both=("hhi",))
    three = _soak_payload(outside=("governor_engagement",), both=("hhi", "gross"))
    passed = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(two))
    assert passed.ok and "hhi (both constructions)" in passed.value, passed.value
    failed = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(three))
    assert not failed.ok and not failed.value.startswith("unreadable:")
    assert "gross (both constructions)" in failed.value and "hhi inconsistent" in failed.value


def test_a_panel_the_instrument_could_not_decide_names_it_and_stops_reading_as_better_than_chance():
    """A metric whose two null constructions gave OPPOSITE verdicts reconciles to a fourth label that counts
    toward the panel's metric count and never toward its outside count -- so a row keyed on the outside count
    alone reads better the more the instrument disagrees with itself, and past four of seven it can no longer
    reach the threshold at all. The row names the disagreement, and a panel too fragile to reach the threshold
    is not a pass."""
    five = _soak_payload(outside=(), indeterminate=("gross", "net", "active_frac", "turnover", "governor_engagement"))
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(five))
    assert not check.ok and not check.value.startswith("unreadable:"), check.value
    assert "5 of 7 indeterminate" in check.value
    one = _soak_payload(outside=(), indeterminate=("gross",))
    still_passes = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(one))
    assert still_passes.ok and "1 of 7 indeterminate" in still_passes.value, still_passes.value


def test_a_panel_with_exactly_three_decided_metrics_reaches_the_threshold_and_passes():
    """The floor is `decided >= SOAK_OUTSIDE_FAILS_AT`, read on both sides like its sibling arms: three decided
    is the minimum panel that CAN reach the threshold, so a `>` in place of `>=` would fail the minimum panel
    that can still be judged -- `>=` is what lets it pass."""
    at_the_floor = _soak_payload(outside=(), undiscriminating=_SOAK_METRICS[:4])
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(at_the_floor))
    assert check.ok, check.value
    assert "only" not in check.value, check.value


def test_a_panel_that_judged_nothing_is_not_an_all_clear():
    """`0 of 0 outside band` is the panel of a run where no metric discriminated, and keyed on the outside
    count alone it reads as the best verdict the row can give. A metric no band could judge is dropped from
    `n_metrics` rather than counted as indeterminate, so on this route the panel's own two lines say nothing
    about why the row failed and the value has to name the floor itself."""
    nothing = _soak_payload(outside=(), undiscriminating=_SOAK_METRICS)
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(nothing))
    assert not check.ok and not check.value.startswith("unreadable:"), check.value
    assert "0 of 0 outside band" in check.value and "only 0 metrics decided" in check.value, check.value
    # Five of seven undiscriminating is the ordinary shape of this arm, and the one the panel cannot show:
    # `n_indeterminate` is 0, so the indeterminate line is empty and the floor is the value's only trace.
    thin = _soak_payload(outside=(), undiscriminating=_SOAK_METRICS[:5])
    reading = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(thin))
    assert not reading.ok and "only 2 metrics decided" in reading.value, reading.value
    assert "indeterminate" not in reading.value, reading.value
    lone = _soak_payload(outside=(), undiscriminating=_SOAK_METRICS[:6])
    assert "only 1 metric decided" in ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(lone)).value


def test_a_self_test_that_never_ran_is_spelled_skipped_and_fails_the_row():
    """A self-test flag voids the run only when it RAN and FAILED; `None` is a check that was SKIPPED -- no
    cycle could be replayed, no pair was compared -- and puts nothing in `void_reasons`, so the void arm above
    never sees it. The panel beneath an unrun proof is a verdict nothing vouched for, so the row fails on it
    and the value still names which of the three was skipped."""
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload(self_test=(True, None, True))))
    assert not check.ok and not check.value.startswith("unreadable:"), check.value
    assert "self-test ok/skipped/ok" in check.value
    all_three = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload()))
    assert all_three.ok and "self-test ok/ok/ok" in all_three.value, all_three.value


def test_a_void_run_fails_on_its_reasons_and_never_reads_the_verdicts_beside_them():
    """A reader that looked at the panel first would pass a run whose instrument failed its own self-test; the
    reduction's order is what this pins."""
    payload = _soak_payload(outside=(), void=("self-test VOID: identity_ok=False",))
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(payload))
    assert not check.ok
    assert check.value == "void: self-test VOID: identity_ok=False"


def test_a_void_run_whose_analysis_never_ran_still_names_its_reason():
    payload = {"void_reasons": ["no journaled cycles found"], "panel": None, "provenance": None, "gating_verdicts": None}
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(payload))
    assert not check.ok and check.value == "void: no journaled cycles found"


def test_no_canonical_dataset_is_a_source_the_pass_could_not_read():
    """The arm that splits `unreadable:` from `void:` matches a SUBSTRING of a reason `soak-check` produces, and
    nothing else joins the two spellings: rename the producer's and every canonical-absent morning silently
    becomes a verdict about the book. The reason here is the producer's own constant, and the substring is held
    against it."""
    from cli.engine import soak

    assert ops_daily._SOAK_CANONICAL_ABSENT in soak.CANONICAL_ABSENT_VOID, soak.CANONICAL_ABSENT_VOID
    payload = _soak_payload(void=(soak.CANONICAL_ABSENT_VOID,))
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(payload))
    assert not check.ok and check.value == f"unreadable: {soak.CANONICAL_ABSENT_VOID}"


@pytest.mark.parametrize(
    "fault",
    [
        FileNotFoundError("no cycle record under /mnt/zhao-crypto/engine-journal"),
        # The journal is a mount: an outage answers with an error, not with a record.
        OSError(5, "Input/output error", "/mnt/zhao-crypto/engine-journal"),
        subprocess.TimeoutExpired(cmd="uv", timeout=900),
        RuntimeError("soak-check exited 1 and wrote no payload: read_store_series: cannot read x"),
        json.JSONDecodeError("Expecting value", "", 0),
    ],
)
def test_a_run_that_produced_no_payload_is_unreadable_and_never_a_verdict_on_the_book(fault):
    def refuse(journal_dir):
        raise fault

    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=refuse)
    assert not check.ok and check.value.startswith("unreadable:"), check.value


def test_a_payload_missing_a_field_the_reduction_reads_is_unreadable():
    payload = _soak_payload()
    del payload["panel"]
    check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(payload))
    assert not check.ok and check.value.startswith("unreadable:"), check.value


def test_the_soak_reader_takes_its_runner_and_never_defaults_one():
    for name in ("runner", "now"):
        taken = inspect.signature(ops_daily.read_soak_verdict).parameters[name]
        assert taken.kind is inspect.Parameter.KEYWORD_ONLY and taken.default is inspect.Parameter.empty, name
    with pytest.raises(TypeError):
        ops_daily.read_soak_verdict(now=_SOAK_NOW)


def test_a_window_that_stopped_days_ago_is_not_a_pass():
    """`soak-check` scores the longest contiguous run of cycles, so one failed boundary leaves it scoring the run
    BEFORE the gap with empty `void_reasons`: every panel count is healthy and the book of the last days was
    never judged. The bound is read on both sides, and the value says how far behind the last scored cycle is."""
    at_the_bound = _soak_payload(ended=_SOAK_NOW - ops_daily.SOAK_WINDOW_STALE_AFTER)
    assert ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(at_the_bound)).ok
    past_it = _soak_payload(ended=_SOAK_NOW - ops_daily.SOAK_WINDOW_STALE_AFTER - timedelta(hours=4))
    stopped = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(past_it))
    assert not stopped.ok and not stopped.value.startswith("unreadable:")
    assert "window_bound=journal; NOT CURRENT -- the last scored cycle is 16.0 h before this pass; self-test" in stopped.value


def test_a_window_the_store_cut_short_is_not_a_pass():
    """The instrument's own payload comment says a machine consumer gates on `window_bound == "store"`: the
    newest cycles went unscored for want of a close, however fresh the stamp the window ends at."""
    cut = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload(window_bound="store")))
    assert not cut.ok
    assert "window_bound=store; NOT CURRENT -- the store, not the journal, ends the scored window; self-test" in cut.value
    clocked = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload(window_bound="clock")))
    assert not clocked.ok and "NOT CURRENT -- the clock, not the journal, ends the scored window" in clocked.value


def test_the_label_the_row_counts_is_the_one_soak_check_spells():
    """The reduction counts a bare token, and `soak-check`'s vocabulary is DERIVED from its own severity
    order -- rename the label there and the closed set moves with it, so a membership pin over the payload
    still holds while this row's count silently goes to zero. This assertion is what goes red instead."""
    from cli.engine import soak

    assert ops_daily.SOAK_OUTSIDE_LABEL in soak._VERDICT_LABELS


def _journal_a_cycle_from(store_dir: Path, journal_dir: Path, cycle_ts: datetime) -> None:
    """One success record written the way `run_cycle` writes it: the store is read, union-aligned and journaled
    by the engine's own functions, so the snapshots are what a real cycle leaves, not a test's idea of them."""
    from cli.engine.cycle import _journal_snapshots, _union_align
    from cli.engine.journal import CycleRecord, to_json
    from cli.engine.store import GRID_INTERVALS, PAIR_KEYS, read_store_series

    raw = {
        (symbol, interval): read_store_series(store_dir, symbol, interval) for symbol in PAIR_KEYS for interval in GRID_INTERVALS
    }
    entries = _journal_snapshots(journal_dir, cycle_ts, {interval: _union_align(raw, interval) for interval in GRID_INTERVALS})
    record = CycleRecord(
        schema_version=2,
        cycle_ts=cycle_ts,
        snapshots=entries,
        final_targets=dict.fromkeys(PAIR_KEYS, 0.0),
        started_at=cycle_ts,
        completed_at=cycle_ts + timedelta(minutes=1),
        code_version="test",
        builder_path="fast",
    )
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"cycle-{cycle_ts:%H}.json").write_text(to_json(record) + "\n")


def _a_twelve_leg_store(store_dir: Path, last: datetime, *, short_leg: str) -> None:
    """Both grids for every basket pair, closes distinct per leg and per bar; `short_leg`'s 240 series lacks the
    stamp before `last`, so the union-aligned snapshot carries a `None` there."""
    from cli.engine.store import GRID_INTERVALS, PAIR_KEYS
    from cli.ohlc.dataset import to_frame, write_parquet

    for k, symbol in enumerate(PAIR_KEYS):
        base, quote = symbol.split("/")
        for interval in GRID_INTERVALS:
            step = timedelta(minutes=interval)
            stamps = [last - step * n for n in range(5, -1, -1)]
            if symbol == short_leg and interval == 240:
                stamps.remove(last - step)
            rows = [[int(t.timestamp()), *[str(100.0 + k + n / 7)] * 5, "1.0", 1] for n, t in enumerate(stamps)]
            (store_dir / base / quote).mkdir(parents=True, exist_ok=True)
            write_parquet(to_frame(rows), store_dir / base / quote / f"{interval}.parquet")


def test_the_journal_derived_store_carries_every_close_the_real_store_does(tmp_path):
    """The claim the soak row rests on. A snapshot differs from its store leg only by a `None` close at a stamp
    the leg lacks and another leg has, and `realized_series` skips a `None` close exactly as it skips an absent
    stamp -- so the comparison drops them and demands equality on the rest, leg by leg."""
    from cli.engine.store import PAIR_KEYS, read_store_series

    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))

    derived = ops_daily.derive_soak_store(journal, tmp_path / "scratch")

    assert derived == tmp_path / "scratch" / "store"
    for symbol in PAIR_KEYS:
        real = dict(zip(*read_store_series(store, symbol, 240)))
        copy = dict(zip(*read_store_series(derived, symbol, 240)))
        assert {t: c for t, c in copy.items() if c is not None} == real, symbol
    padded = dict(zip(*read_store_series(derived, "SOL/EUR", 240)))
    assert padded[last - timedelta(hours=4)] is None, "the fixture no longer exercises the union's None"
    assert not list(derived.rglob("1440.parquet")), "only the 240 grid is read by soak-check"


def test_the_derived_store_is_the_newest_success_records_and_a_failed_cycle_is_not_a_record(tmp_path):
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last - timedelta(hours=4), short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last)
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    # Sorts after every `cycle-*.json` of its day, and carries no snapshots: the glob must not take it.
    (journal / "2026-09-19" / "failed-cycle-20.json").write_text('{"reason": "stale_pair"}\n')

    from cli.engine.store import read_store_series

    derived = ops_daily.derive_soak_store(journal, tmp_path / "scratch")
    assert read_store_series(derived, "BTC/EUR", 240)[0][-1] == last


def test_a_record_journaling_two_240_snapshots_for_one_pair_still_derives(tmp_path):
    """Nothing in the record format says a pair gets one 240 entry, and the derivation made each pair's
    directory as if it did: a second entry raised `FileExistsError`, which the row reports as `unreadable:`
    -- the pass declaring it could not read a record it could. The later entry is the pair's leg."""
    from cli.engine.store import read_store_series

    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    record_path = next(journal.glob("*/cycle-*.json"))
    record = json.loads(record_path.read_text())
    legs = {e["pair"]: e for e in record["snapshots"] if e["grid"] == "240"}
    # ETH's whole entry under BTC's name: the duplicate names a file whose own journaled metadata it carries,
    # so what this case drives is the second `mkdir` and nothing else.
    record["snapshots"].append({**legs["ETH/EUR"], "pair": "BTC/EUR"})
    record_path.write_text(json.dumps(record))

    derived = ops_daily.derive_soak_store(journal, tmp_path / "scratch")

    assert read_store_series(derived, "BTC/EUR", 240) == read_store_series(store, "ETH/EUR", 240)


def test_a_leg_disagreeing_with_its_journaled_metadata_is_refused_and_reads_unreadable(tmp_path):
    """The journal reaches this host over an rsync pull, so a leg can differ from the record that describes it
    with nothing on the page to say so -- and copied in unchecked it becomes a book `soak-check` judges and
    nobody can reproduce. Both of the engine's own checks are driven: the content hash, and the metadata the
    engine compares beside it. Each refusal reaches the row as `unreadable:`, a source the pass could not
    read, never a verdict."""
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    record_path = next(journal.glob("*/cycle-*.json"))
    record = json.loads(record_path.read_text())
    legs = {e["pair"]: e for e in record["snapshots"] if e["grid"] == "240"}

    # A leg replaced by another pair's, which shares its calendar: only the hash can tell them apart.
    (journal / legs["BTC/EUR"]["path"]).write_bytes((journal / legs["ETH/EUR"]["path"]).read_bytes())
    with pytest.raises(ValueError, match="content hash mismatch for pair='BTC/EUR'") as corrupt:
        ops_daily.derive_soak_store(journal, tmp_path / "scratch-a")

    # Every leg rewritten, so only the record moves this time: a bar count that no longer describes its file.
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    record = json.loads(record_path.read_text())
    for entry in record["snapshots"]:
        if entry["pair"] == "BTC/EUR" and entry["grid"] == "240":
            entry["n_bars"] += 1
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="read data disagrees with its own journaled metadata") as short:
        ops_daily.derive_soak_store(journal, tmp_path / "scratch-b")

    for raised in (corrupt, short):

        def refuse(journal_dir, exc=raised.value):
            raise exc

        check = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=refuse)
        assert not check.ok and check.value.startswith("unreadable:"), check.value


def test_a_journal_with_no_record_and_a_record_with_no_240_snapshot_both_refuse(tmp_path):
    with pytest.raises(FileNotFoundError, match="no cycle record"):
        ops_daily.derive_soak_store(tmp_path, tmp_path / "scratch")
    day = tmp_path / "2026-09-19"
    day.mkdir()
    (day / "cycle-16.json").write_text(json.dumps({"snapshots": [{"grid": "1440", "pair": "BTC/EUR", "path": "x"}]}))
    with pytest.raises(ValueError, match="no 240 snapshot"):
        ops_daily.derive_soak_store(tmp_path, tmp_path / "scratch")


def test_the_soak_run_hands_soak_check_the_derived_store_and_returns_what_it_wrote(tmp_path, monkeypatch, live_soak_run):
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"], seen["kwargs"] = command, kwargs
        handed = Path(command[command.index("--store-dir") + 1])
        seen["legs"] = sorted(p.relative_to(handed).as_posix() for p in handed.rglob("*.parquet"))
        Path(command[command.index("--json") + 1]).write_text('{"void_reasons": []}')
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.delenv(ops_daily.SOAK_CANONICAL_ENV, raising=False)
    monkeypatch.setattr(ops_daily.subprocess, "run", fake_run)
    assert live_soak_run(journal) == {"void_reasons": []}
    assert seen["command"][:8] == ("uv", "run", "--no-sync", "zcrypto", "engine", "soak-check", "--journal-dir", str(journal))
    assert seen["command"][8:10] == ("--canonical-dir", str(ops_daily.SOAK_CANONICAL)), seen["command"]
    assert ops_daily.SOAK_CANONICAL.is_absolute(), ops_daily.SOAK_CANONICAL
    # `capture_output`/`text` beside the other two: without them the abort line the no-payload arm raises goes
    # to the pass's own stderr as bytes, and the row's `unreadable:` value carries `no output` instead.
    assert seen["kwargs"]["cwd"] == ops_daily.REPO_ROOT and seen["kwargs"]["timeout"] == 900
    assert seen["kwargs"]["capture_output"] is True and seen["kwargs"]["text"] is True, seen["kwargs"]
    assert len(seen["legs"]) == 12 and "BTC/EUR/240.parquet" in seen["legs"]
    assert not Path(seen["command"][seen["command"].index("--store-dir") + 1]).exists(), "the scratch store outlived the run"


def test_the_canonical_dataset_is_the_environments_where_it_names_one_and_the_constant_otherwise(
    tmp_path, monkeypatch, live_soak_run
):
    """The constant is one operator's checkout path; a second host keeps the dataset elsewhere. The variable is
    read where the command is BUILT, not at import, so this case can set it on a module the suite imported once,
    and an empty value is no value -- an exported-but-blank variable must not point the run at the filesystem
    root."""
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command[command.index("--canonical-dir") + 1])
        Path(command[command.index("--json") + 1]).write_text('{"void_reasons": []}')
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ops_daily.subprocess, "run", fake_run)
    monkeypatch.setenv(ops_daily.SOAK_CANONICAL_ENV, str(tmp_path / "elsewhere"))
    live_soak_run(journal)
    monkeypatch.setenv(ops_daily.SOAK_CANONICAL_ENV, "")
    live_soak_run(journal)
    monkeypatch.delenv(ops_daily.SOAK_CANONICAL_ENV)
    live_soak_run(journal)
    assert seen == [str(tmp_path / "elsewhere"), str(ops_daily.SOAK_CANONICAL), str(ops_daily.SOAK_CANONICAL)], seen


def test_a_soak_check_that_wrote_no_payload_raises_its_last_line(tmp_path, monkeypatch, live_soak_run):
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    aborted = lambda command, **kwargs: subprocess.CompletedProcess(
        command,
        1,
        # Both streams are a live abort's: the CLI's console handler logs to stdout, and `uv run` puts its own
        # notices on stderr -- under `--no-sync` the environment it declines to repair, rather than the sync.
        stdout="warming up\n2026-09-19 12:00:04 ERROR zcrypto.engine.command [command.py:86] - read_store_series: cannot read x\n",
        stderr="warning: `VIRTUAL_ENV=.venv` does not match the project environment path `.venv`\n",
    )
    monkeypatch.setattr(ops_daily.subprocess, "run", aborted)
    with pytest.raises(RuntimeError, match=r"exited 1 and wrote no payload: .* ERROR .* - read_store_series: cannot read x"):
        live_soak_run(journal)


def test_the_soak_row_reaches_the_verdict_the_pass_prints(monkeypatch, capsys):
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name: "tok")
    monkeypatch.setattr(ops_daily, "read_alerts", lambda *a, **k: ops_daily.AlertsRead())
    monkeypatch.setattr(ops_daily, "read_logs", lambda *a, **k: ops_daily.LogsRead())
    monkeypatch.setattr(ops_daily, "read_deadmen", lambda *a, **k: ops_daily.DeadmenRead(via_prometheus=0.0))
    monkeypatch.setattr(ops_daily, "read_verdict", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_deploys", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_reminders", lambda *a, **k: ops_daily.RemindersRead())
    monkeypatch.setattr(ops_daily, "ssh_read", _host_answering(StampEpoch=str(int(datetime.now(timezone.utc).timestamp()))))
    monkeypatch.setattr(ops_daily, "soak_run", _soak_answering(_a_current_soak_payload()))
    assert ops_daily.main(["report"]) == 0
    assert f"- PASS {ops_daily.SOAK_CHECK}: 1 of 7 outside band" in capsys.readouterr().out

    monkeypatch.setattr(ops_daily, "soak_run", _soak_answering(_soak_payload(void=("cap-breach inconsistent",))))
    assert ops_daily.main(["report"]) == 1
    assert f"- FAIL {ops_daily.SOAK_CHECK}: void: cap-breach inconsistent" in capsys.readouterr().out

    def unmounted(journal_dir):
        raise FileNotFoundError(f"no cycle record under {journal_dir}")

    monkeypatch.setattr(ops_daily, "soak_run", unmounted)
    assert ops_daily.main(["report"]) == 2
    assert f"- {ops_daily.SOAK_CHECK} could not be read: no cycle record under {ops_daily.SOAK_JOURNAL}" in capsys.readouterr().out


def test_the_journal_paragraph_carries_the_soak_rows_value_on_a_passing_day():
    row = ops_daily.read_soak_verdict(now=_SOAK_NOW, runner=_soak_answering(_soak_payload()))
    assert row.ok
    para = dataclasses.replace(_report(), verdict=[row]).journal_paragraph()
    assert f"· checks all pass · soak {row.value} · logs" in para, para
    assert "soak" not in _report().journal_paragraph(), "no soak row, no soak clause"


def test_the_suites_refusing_soak_run_is_the_one_every_test_gets(tmp_path):
    """Every other test that reaches `soak_run` stubs it itself, so without this reader and the one below it
    the refusal could be narrowed away with nothing going red. An empty directory stands in for the journal --
    the real runner refuses it for want of a record, before it starts a subprocess or reads a mount."""
    with pytest.raises(AssertionError, match="must stub it"):
        ops_daily.soak_run(tmp_path)


def test_a_report_that_forgets_its_soak_stub_meets_the_refusal(tmp_path, monkeypatch):
    """`main` resolves `soak_run` off the module when it runs, which is the attribute the fixture replaces:
    every other reader stubbed and the runner left alone, the refusal surfaces through `main` itself. The
    journal is pointed at an empty directory, so a refusal that went missing meets no mount either."""
    monkeypatch.setattr(ops_daily, "SOAK_JOURNAL", tmp_path)
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name: "tok")
    monkeypatch.setattr(ops_daily, "read_alerts", lambda *a, **k: ops_daily.AlertsRead())
    monkeypatch.setattr(ops_daily, "read_logs", lambda *a, **k: ops_daily.LogsRead())
    monkeypatch.setattr(ops_daily, "read_deadmen", lambda *a, **k: ops_daily.DeadmenRead(via_prometheus=0.0))
    monkeypatch.setattr(ops_daily, "read_verdict", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_deploys", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_reminders", lambda *a, **k: ops_daily.RemindersRead())
    monkeypatch.setattr(ops_daily, "ssh_read", _host_answering(StampEpoch=str(int(datetime.now(timezone.utc).timestamp()))))
    with pytest.raises(AssertionError, match="must stub it"):
        ops_daily.main(["report"])
