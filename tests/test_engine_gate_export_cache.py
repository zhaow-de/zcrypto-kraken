"""Tests for `_evaluate_journal`'s cache wiring and `gate-export --cache` (spec 00060 T2):
threading a cache_path back in place of a fresh `replay_cycle` call for unchanged cycles, while
`JournalCounts` is derived from the resulting `CycleOutcome` in one place regardless of whether it
came from cache or replay (the trap: incrementing counters only inside the replay branches would
silently stop counting cache hits). Journal fixtures mirror tests/test_engine_gate_export.py's
shapes (real, replayable records; concordance.build_crossfreq_system_fast is monkeypatched to a
fast deterministic stub -- no dataset access, no real strategy rebuild)."""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

import cli.engine.command as command
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine import concordance
from cli.engine.concordance import evaluate_gate
from cli.engine.gate_cache import load_cache, oldest_verification_age, replay_fingerprint, slice_of
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json, validate_record
from cli.ohlc.dataset import write_parquet

runner = CliRunner()

UTC = timezone.utc
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
PAIRS = ("BTC", "ETH")
TARGETS = {"BTC": 0.2, "ETH": 0.05}


def _patch_config(monkeypatch, tmp_path: Path) -> EngineConfig:
    """Point load_config (as cli.engine.command sees it) at tmp-dir engine paths."""
    cfg = AppConfig(
        data_dir=None,
        nfs_mount_dir=Path("/mnt/zhao-crypto"),
        fetch=FetchConfig(),
        engine=EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal"),
        data=DataConfig(),
    )
    monkeypatch.setattr(command, "load_config", lambda: cfg)
    return cfg.engine


# --- journal fixtures (real, replayable records -- the shapes run_cycle writes) --------------------


def _series(cycle_ts: datetime, interval: int, base: float) -> tuple[list[datetime], list[float]]:
    if interval == 240:
        last, step, n = cycle_ts - timedelta(hours=4), timedelta(hours=4), 6
    else:
        last, step, n = cycle_ts.replace(hour=0) - timedelta(days=1), timedelta(days=1), 4
    ts = [last - (n - 1 - i) * step for i in range(n)]
    return ts, [base + i for i in range(n)]


def _snapshot_frame(ts: list[datetime], closes: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"ts": ts, "close": closes}, schema={"ts": pl.Datetime("us", "UTC"), "close": pl.Float64})


def _write_success_record(
    journal_dir: Path,
    cycle_ts: datetime,
    targets: dict[str, float] = TARGETS,
    *,
    completed_at: datetime | None = None,
) -> Path:
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
    entries = []
    for interval in (1440, 240):
        for i, pair in enumerate(PAIRS):
            ts, closes = _series(cycle_ts, interval, 100.0 * (i + 1))
            rel_path = rel_dir / f"{pair}-{interval}.parquet"
            write_parquet(_snapshot_frame(ts, closes), journal_dir / rel_path)
            entries.append(
                SnapshotEntry(
                    pair=pair,
                    grid=str(interval),
                    n_bars=len(ts),
                    first_ts=ts[0],
                    last_ts=ts[-1],
                    content_hash=snapshot_content_hash(ts, closes),
                    path=rel_path.as_posix(),
                )
            )
    record = CycleRecord(
        schema_version=1,
        cycle_ts=cycle_ts,
        snapshots=tuple(entries),
        final_targets=dict(targets),
        started_at=cycle_ts + timedelta(seconds=95),
        completed_at=completed_at if completed_at is not None else cycle_ts + timedelta(minutes=3),
        code_version="test",
        builder_path="fast",
    )
    validate_record(record)
    path = journal_dir / f"{cycle_ts:%Y-%m-%d}" / f"cycle-{cycle_ts:%H}.json"
    path.write_text(to_json(record) + "\n")
    return path


def _fake_builder(targets: dict[str, float]):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods)

    return builder


def _prom(text: str) -> dict[str, float]:
    return {ln.split()[0]: float(ln.split()[1]) for ln in text.splitlines() if ln and not ln.startswith("#")}


def _counted_replay_cycle(monkeypatch, calls: list[datetime]):
    """Wrap the real command.replay_cycle to record which cycle_ts it was called for, so tests can
    assert exactly which cycles were actually replayed (vs served from cache)."""
    original = command.replay_cycle

    def wrapper(record, reader, *, path="fast"):
        calls.append(record.cycle_ts)
        return original(record, reader, path=path)

    monkeypatch.setattr(command, "replay_cycle", wrapper)


# --- D4 keystone: warm cache equals cold cache (THE TRAP pin) ---------------------------------------


def test_warm_cache_equals_cold_cache(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    _write_success_record(journal, CYCLE_TS + timedelta(hours=4))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    # hour=12 is neither cycle's rotation slice (CYCLE_TS -> 13, CYCLE_TS+4h -> 23), so this test's
    # warm/cold comparison isn't incidentally muddied by a forced reverification -- that's covered
    # by its own tests below.
    now = CYCLE_TS + timedelta(hours=4, minutes=10)

    cold_entries, cold_counts, cold_newest, cold_stats = command._evaluate_journal(journal, cache_path=None, now=now)

    cache_path = tmp_path / "gate-cache.json"
    cold_cache_entries, cold_cache_counts, cold_cache_newest, cold_cache_stats = command._evaluate_journal(
        journal, cache_path=cache_path, now=now
    )
    warm_entries, warm_counts, warm_newest, warm_stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)

    # Same CycleOutcome lists across no-cache, cold-with-cache, and warm.
    assert cold_cache_entries == cold_entries
    assert warm_entries == cold_entries

    # Same JournalCounts across all three -- the trap: a cache hit that stopped counting would
    # silently diverge here even though the entries themselves (and therefore the gate) look fine.
    assert cold_cache_counts == cold_counts
    assert warm_counts == cold_counts

    assert cold_cache_newest == cold_newest == warm_newest

    # Same evaluate_gate verdict across all three.
    cold_status = evaluate_gate(cold_entries, now=now)
    cold_cache_status = evaluate_gate(cold_cache_entries, now=now)
    warm_status = evaluate_gate(warm_entries, now=now)
    assert cold_cache_status == cold_status
    assert warm_status == cold_status

    # Cache stats sanity: cold-with-cache replayed everything, warm replayed nothing.
    assert cold_cache_stats.replayed == 2
    assert cold_cache_stats.from_cache == 0
    assert warm_stats.replayed == 0
    assert warm_stats.from_cache == 2


# --- only new cycles are replayed --------------------------------------------------------------------


def test_warm_cache_replays_only_the_new_cycle(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"
    # hour=8 is neither CYCLE_TS's (13) nor CYCLE_TS+4h's (23) rotation slice.
    now = CYCLE_TS + timedelta(minutes=10)

    calls: list[datetime] = []
    _counted_replay_cycle(monkeypatch, calls)

    command._evaluate_journal(journal, cache_path=cache_path, now=now)
    assert calls == [CYCLE_TS]

    calls.clear()
    command._evaluate_journal(journal, cache_path=cache_path, now=now)
    assert calls == []  # unchanged journal, warm cache -> zero replays

    _write_success_record(journal, CYCLE_TS + timedelta(hours=4))
    calls.clear()
    entries, counts, _, stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)
    assert calls == [CYCLE_TS + timedelta(hours=4)]  # exactly the new cycle, not the whole journal
    assert stats.replayed == 1
    assert stats.from_cache == 1


# --- tampered evidence misses the cache -----------------------------------------------------------


def test_tampered_record_misses_cache(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    record_path = _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"
    now = CYCLE_TS + timedelta(minutes=10)  # hour=8, not CYCLE_TS's rotation slice (13)

    command._evaluate_journal(journal, cache_path=cache_path, now=now)  # populate the cache

    payload = json.loads(record_path.read_text())
    payload["final_targets"] = {"BTC": 0.3, "ETH": 0.05}
    record_path.write_text(json.dumps(payload))

    calls: list[datetime] = []
    _counted_replay_cycle(monkeypatch, calls)

    entries, counts, _, stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)
    assert calls == [CYCLE_TS]  # tampered evidence forces a replay, not a stale cache hit
    assert stats.replayed == 1
    assert stats.from_cache == 0


# --- D3: a replay-code change invalidates the whole cache ---------------------------------------------


def test_replay_fingerprint_change_invalidates_everything(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    _write_success_record(journal, CYCLE_TS + timedelta(hours=4))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"
    # hour=8 is neither cycle's rotation slice (CYCLE_TS -> 13, CYCLE_TS+4h -> 23).
    now = CYCLE_TS + timedelta(minutes=10)

    monkeypatch.setattr(command, "replay_fingerprint", lambda **_: "fp-v1")
    command._evaluate_journal(journal, cache_path=cache_path, now=now)  # populate the cache under fp-v1

    calls: list[datetime] = []
    _counted_replay_cycle(monkeypatch, calls)
    monkeypatch.setattr(command, "replay_fingerprint", lambda **_: "fp-v2")

    entries, counts, _, stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)

    assert sorted(calls) == [CYCLE_TS, CYCLE_TS + timedelta(hours=4)]  # every cycle replayed
    assert stats.invalidated is True
    assert stats.replayed == 2
    assert stats.from_cache == 0


# --- a cached failure stays a failure ----------------------------------------------------------------


def test_cached_failure_stays_a_failure(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    # Corrupt the on-disk snapshot post-write (same metadata, shifted closes) -> a pure hash
    # mismatch, mirroring tests/test_engine_command.py's tampering pattern.
    ts, closes = _series(CYCLE_TS, 240, 100.0)
    write_parquet(
        _snapshot_frame(ts, [c + 1.0 for c in closes]),
        journal / f"{CYCLE_TS:%Y-%m-%d}" / "snapshots" / f"cycle-{CYCLE_TS:%H}" / "BTC-240.parquet",
    )
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"
    now = CYCLE_TS + timedelta(minutes=10)  # hour=8, not CYCLE_TS's rotation slice (13)

    cold_entries, cold_counts, _, cold_stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)
    assert cold_entries[0].mismatch is True
    assert cold_stats.replayed == 1

    warm_entries, warm_counts, _, warm_stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)
    assert warm_entries == cold_entries
    assert warm_entries[0].mismatch is True  # a cached failure must never come back as a pass
    assert warm_counts == cold_counts
    assert warm_stats.from_cache == 1
    assert warm_stats.replayed == 0


# --- D1: no --cache is byte-identical current behavior ------------------------------------------------


def test_no_cache_option_is_unchanged_behavior(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    entries, counts, newest_ts, stats = command._evaluate_journal(journal, cache_path=None, now=CYCLE_TS + timedelta(minutes=10))
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())

    assert after == before  # no cache file created anywhere
    assert counts.replayed_ok == 1
    assert stats.replayed == 1
    assert stats.from_cache == 0
    assert stats.invalidated is False


# --- the fingerprint layer stays inert without --cache, and degrades rather than aborts ----------------


def test_no_cache_path_never_touches_the_fingerprint_layer(tmp_path, monkeypatch):
    """`cache_path=None` must take the pre-`--cache` code path structurally, not just by outcome --
    neither fingerprint function may even be called. Pins D1: a bug in either fingerprint (e.g. the
    unguarded `module_path.read_bytes()` in replay_fingerprint) must never be able to touch `report`
    or any other no-cache caller."""
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    def _boom(*_args, **_kwargs):
        raise AssertionError("fingerprint layer must not run when cache_path is None")

    monkeypatch.setattr(command, "replay_fingerprint", _boom)
    monkeypatch.setattr(command, "evidence_fingerprint", _boom)

    entries, counts, newest_ts, stats = command._evaluate_journal(journal, cache_path=None, now=CYCLE_TS + timedelta(minutes=10))

    assert counts.replayed_ok == 1
    assert stats.replayed == 1
    assert stats.from_cache == 0
    assert stats.invalidated is False


def test_broken_replay_fingerprint_degrades_not_aborts(tmp_path, monkeypatch):
    """A cache is an optimization; gate evidence is not. `replay_fingerprint()` reads ten module
    files with no exception guard of its own -- an OSError there (an unreadable file, a bind-mount
    hiccup) must degrade this run to a full replay without a cache, never abort the whole gate-export
    run."""
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"

    def _boom(**_kwargs):
        raise OSError("simulated unreadable replay-code module")

    monkeypatch.setattr(command, "replay_fingerprint", _boom)

    entries, counts, newest_ts, stats = command._evaluate_journal(
        journal, cache_path=cache_path, now=CYCLE_TS + timedelta(minutes=10)
    )

    assert counts.replayed_ok == 1
    assert stats.replayed == 1
    assert stats.from_cache == 0  # degraded to no-cache for this run
    assert not cache_path.exists()  # no cache read or written this run


# --- D8: gate-export emits the cache metrics -----------------------------------------------------------


def test_gate_export_emits_cache_metrics(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_success_record(journal, CYCLE_TS)
    _write_success_record(journal, CYCLE_TS + timedelta(hours=4))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(hours=4, minutes=10))

    out = tmp_path / "gate.prom"
    cache_path = tmp_path / "gate-cache.json"

    result = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(journal),
            "--textfile",
            str(out),
            "--cache",
            str(cache_path),
        ],
    )
    assert result.exit_code == 0, result.output
    m = _prom(out.read_text())
    assert m["zcrypto_gate_cache_replayed"] + m["zcrypto_gate_cache_hits"] == 2
    assert m["zcrypto_gate_cache_replayed"] == 2  # cold: nothing cached yet
    assert m["zcrypto_gate_cache_invalidated"] == 0

    result2 = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(journal),
            "--textfile",
            str(out),
            "--cache",
            str(cache_path),
        ],
    )
    assert result2.exit_code == 0, result2.output
    m2 = _prom(out.read_text())
    assert m2["zcrypto_gate_cache_hits"] == 2
    assert m2["zcrypto_gate_cache_replayed"] == 0
    assert m2["zcrypto_gate_cache_invalidated"] == 0


def test_gate_export_no_cache_option_reports_zero_cached(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(minutes=10))

    out = tmp_path / "gate.prom"
    result = runner.invoke(app, ["engine", "gate-export", "--journal-dir", str(journal), "--textfile", str(out)])

    assert result.exit_code == 0, result.output
    m = _prom(out.read_text())
    assert m["zcrypto_gate_cache_replayed"] == 1
    assert m["zcrypto_gate_cache_hits"] == 0
    assert m["zcrypto_gate_cache_invalidated"] == 0


# --- spec 00062: rotating re-verification -------------------------------------------------------


def test_tampered_parquet_with_intact_record_is_caught_within_one_rotation(tmp_path, monkeypatch):
    """THE KEYSTONE (T0077/spec 00062). A cache hit skips replay_cycle entirely, which is the ONLY
    place a journaled snapshot's parquet bytes are re-hashed -- evidence_fingerprint digests the
    content_hash CLAIMED in the record, never a fresh read. So a snapshot altered on disk after its
    first replay, with the record left untouched, is an otherwise-permanent stale PASS. Rotation
    must force the cycle's own slice hour to replay despite the unchanged fingerprint, and a real
    replay must then discover the tamper via the parquet content-hash check
    (cli/engine/concordance.py:116). MUST FAIL if the eligibility test's `not reverify` clause is
    removed: without it, every hour below stays a cache hit and the tamper is never caught."""
    journal = tmp_path / "journal"
    parquet_path = journal / f"{CYCLE_TS:%Y-%m-%d}" / "snapshots" / f"cycle-{CYCLE_TS:%H}" / "BTC-240.parquet"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"
    own_slice = slice_of(CYCLE_TS)

    # Warm the cache with a genuine, untampered replay.
    warm_entries, _, _, warm_stats = command._evaluate_journal(journal, cache_path=cache_path, now=CYCLE_TS)
    assert warm_entries[0].mismatch is False
    assert warm_stats.replayed == 1

    # Tamper the parquet BYTES on disk -- same metadata, shifted closes -- leaving the record's
    # content_hash claim (and therefore evidence_fingerprint) untouched, so a cache hit would
    # otherwise serve this as a PASS forever.
    ts, closes = _series(CYCLE_TS, 240, 100.0)
    write_parquet(_snapshot_frame(ts, [c + 1.0 for c in closes]), parquet_path)

    caught = False
    for hour in range(24):
        now = CYCLE_TS.replace(hour=hour, minute=0)
        entries, counts, _, stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)
        if hour == own_slice:
            assert entries[0].mismatch is True, "the cycle's own rotation slice must force a replay that catches the tamper"
            assert counts.mismatches == 1
            assert stats.replayed == 1
            assert stats.from_cache == 0
            caught = True
        elif hour < own_slice:
            # Before its own slice comes up this rotation, the tampered snapshot is still served
            # from cache as a stale PASS -- exactly the exposure spec 00062 closes.
            assert entries[0].mismatch is False
            assert stats.from_cache == 1
        else:
            # After being caught, a cached failure stays a failure (D4 carry-forward).
            assert entries[0].mismatch is True
            assert stats.from_cache == 1

    assert caught, f"the cycle's own slice ({own_slice}) never came up across a full 24h sweep"


def test_rotation_is_bounded(tmp_path, monkeypatch):
    """Warm cache, no tampering: one run replays only the cycles whose slice matches the run's
    current hour (~n/24), the rest are served from cache -- rotation must not degrade to a full
    replay every run, which would defeat spec 00060's whole cost saving."""
    journal = tmp_path / "journal"
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"

    cycles = [CYCLE_TS + timedelta(hours=4 * i) for i in range(48)]
    for cycle_ts in cycles:
        _write_success_record(journal, cycle_ts)

    warm_now = cycles[-1] + timedelta(minutes=10)
    command._evaluate_journal(journal, cache_path=cache_path, now=warm_now)  # cold: fully populates the cache

    probe_now = cycles[-1] + timedelta(hours=1, minutes=10)
    expected_due = sum(1 for c in cycles if slice_of(c) == probe_now.hour % 24)

    calls: list[datetime] = []
    _counted_replay_cycle(monkeypatch, calls)
    entries, counts, _, stats = command._evaluate_journal(journal, cache_path=cache_path, now=probe_now)

    assert len(calls) == expected_due
    assert stats.replayed == expected_due
    assert stats.from_cache == len(cycles) - expected_due
    assert stats.replayed < len(cycles)  # bounded: not a full-journal replay


def test_warm_equals_cold_with_rotation_active(tmp_path, monkeypatch):
    """Spec 00060 D4 preserved under an active rotation: a cache hit's CycleOutcome and
    evaluate_gate's verdict must equal a fresh replay's, for every possible run hour -- including
    the hours where rotation forces a real replay on top of an otherwise-eligible cache hit."""
    journal = tmp_path / "journal"
    cycles = [CYCLE_TS + timedelta(hours=4 * i) for i in range(6)]
    for cycle_ts in cycles:
        _write_success_record(journal, cycle_ts)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"

    command._evaluate_journal(journal, cache_path=cache_path, now=cycles[-1] + timedelta(minutes=10))  # populate

    any_forced = False
    for hour in range(24):
        now = cycles[-1].replace(hour=hour, minute=10)
        cold_entries, cold_counts, cold_newest, _ = command._evaluate_journal(journal, cache_path=None, now=now)
        warm_entries, warm_counts, warm_newest, warm_stats = command._evaluate_journal(journal, cache_path=cache_path, now=now)

        assert warm_entries == cold_entries
        assert warm_counts == cold_counts
        assert warm_newest == cold_newest
        assert evaluate_gate(warm_entries, now=now) == evaluate_gate(cold_entries, now=now)
        if warm_stats.replayed > 0:
            any_forced = True

    assert any_forced, "rotation never forced a single replay across the 24h sweep -- test is vacuous"


def test_forced_reverification_failure_counts_as_replayed_and_moves_the_gate(tmp_path, monkeypatch):
    """D4: a forced re-verification that fails is a real gate failure, not a cache event -- it lands
    in JournalCounts.mismatches (the same tally a fresh replay's mismatch would) and is counted as
    `replayed`, never `from_cache`."""
    journal = tmp_path / "journal"
    parquet_path = journal / f"{CYCLE_TS:%Y-%m-%d}" / "snapshots" / f"cycle-{CYCLE_TS:%H}" / "BTC-240.parquet"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"

    command._evaluate_journal(journal, cache_path=cache_path, now=CYCLE_TS)  # warm, genuine pass

    ts, closes = _series(CYCLE_TS, 240, 100.0)
    write_parquet(_snapshot_frame(ts, [c + 1.0 for c in closes]), parquet_path)  # tamper post-cache

    forced_now = CYCLE_TS.replace(hour=slice_of(CYCLE_TS))
    entries, counts, _, stats = command._evaluate_journal(journal, cache_path=cache_path, now=forced_now)

    assert entries[0].mismatch is True
    assert counts.mismatches == 1
    assert stats.replayed == 1
    assert stats.from_cache == 0


def test_verified_at_carried_on_hit_stamped_on_replay(tmp_path, monkeypatch):
    """D5: verified_at is carried forward on a cache hit and stamped to `now` only on an actual
    replay (cold or forced); oldest_verification_age reflects the least-recently-replayed entry and
    falls below one rotation period (24h) once a full sweep has forced every slice at least once."""
    journal = tmp_path / "journal"
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    cache_path = tmp_path / "gate-cache.json"
    fp = replay_fingerprint(path=command._EVALUATE_JOURNAL_REPLAY_PATH)
    own_slice = slice_of(CYCLE_TS)

    now0 = CYCLE_TS  # a fresh (cold) replay -- stamps verified_at = now0
    command._evaluate_journal(journal, cache_path=cache_path, now=now0)
    assert load_cache(cache_path, fp).entries[CYCLE_TS][2] == now0

    # A cache hit (any hour other than the cycle's own slice) must carry verified_at FORWARD,
    # never bump it to the hit's own `now`.
    hit_hour = (own_slice + 1) % 24
    hit_now = CYCLE_TS.replace(hour=hit_hour, minute=30)
    _, _, _, hit_stats = command._evaluate_journal(journal, cache_path=cache_path, now=hit_now)
    assert hit_stats.from_cache == 1
    assert load_cache(cache_path, fp).entries[CYCLE_TS][2] == now0  # unchanged by the hit

    # A forced reverification (the cycle's own slice) stamps verified_at to the REPLAY time, not
    # carried forward from the prior entry.
    replay_now = CYCLE_TS.replace(hour=own_slice, minute=45)
    _, _, _, replay_stats = command._evaluate_journal(journal, cache_path=cache_path, now=replay_now)
    assert replay_stats.replayed == 1
    assert load_cache(cache_path, fp).entries[CYCLE_TS][2] == replay_now

    # After a full 24h sweep, the (only) entry's own slice must have come up exactly once, so its
    # age relative to the sweep's end is below one rotation period.
    for hour in range(24):
        command._evaluate_journal(journal, cache_path=cache_path, now=CYCLE_TS.replace(hour=hour))
    final_now = CYCLE_TS.replace(hour=23, minute=59)
    age = oldest_verification_age(load_cache(cache_path, fp), final_now)
    assert age is not None
    assert age < 24 * 3600


def test_metrics_renamed_and_new_ones_present(tmp_path, monkeypatch):
    """D7: no `_total`-suffixed cache gauge remains (`zcrypto_gate_cache_replayed`/`_hits` replace
    the old `_replayed_total`/`_hits_total`). D5/D8: `zcrypto_gate_cache_oldest_verification_age_seconds`
    and `zcrypto_gate_export_duration_seconds` appear with plausible (non-negative) values."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(minutes=10))

    out = tmp_path / "gate.prom"
    cache_path = tmp_path / "gate-cache.json"

    result = runner.invoke(
        app, ["engine", "gate-export", "--journal-dir", str(journal), "--textfile", str(out), "--cache", str(cache_path)]
    )
    assert result.exit_code == 0, result.output
    m = _prom(out.read_text())

    assert not any(key.startswith("zcrypto_gate_cache") and key.endswith("_total") for key in m)
    assert "zcrypto_gate_cache_replayed" in m
    assert "zcrypto_gate_cache_hits" in m
    assert "zcrypto_gate_export_duration_seconds" in m
    assert m["zcrypto_gate_export_duration_seconds"] >= 0.0

    # A second (warm) run: the cache is now populated, so the staleness age metric must appear.
    result2 = runner.invoke(
        app, ["engine", "gate-export", "--journal-dir", str(journal), "--textfile", str(out), "--cache", str(cache_path)]
    )
    assert result2.exit_code == 0, result2.output
    m2 = _prom(out.read_text())
    assert "zcrypto_gate_cache_oldest_verification_age_seconds" in m2
    assert m2["zcrypto_gate_cache_oldest_verification_age_seconds"] >= 0.0
