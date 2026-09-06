"""`verify_replay_incremental` — the incremental orchestrator (spec 00078)."""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.archive import replay as replay_module
from cli.archive.checkpoint import CheckpointRow, load_checkpoint, save_checkpoint
from cli.archive.replay import EvictionRefusedError, verify_replay, verify_replay_incremental
from cli.capture.segment_writer import BOOK_SCHEMA

H = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)


def _coherent_messages() -> list[dict]:
    """One snapshot then three coherent updates — a replayable hour."""
    return [
        {
            "offset": 0,
            "type": "snapshot",
            "bids": [(100.0, 1.0), (99.0, 2.0)],
            "asks": [(101.0, 1.0), (102.0, 2.0)],
            "checksum": 11,
        },
        {"offset": 10, "type": "update", "bids": [(100.0, 0.5)], "asks": [], "checksum": 12},
        {"offset": 20, "type": "update", "bids": [], "asks": [(101.0, 0.0)], "checksum": 13},
        {"offset": 30, "type": "update", "bids": [(98.0, 3.0)], "asks": [(103.0, 1.5)], "checksum": 14},
    ]


def _explode(pair: str, hour: datetime, messages: list[dict]) -> pl.DataFrame:
    """Fan each WS-shaped message out into one row per price level, exactly as the capture writer does."""
    rows = []
    for msg in messages:
        ts = hour + timedelta(seconds=msg["offset"])
        for side, levels in (("bid", msg.get("bids", [])), ("ask", msg.get("asks", []))):
            for price, qty in levels:
                rows.append(
                    {
                        "ts": ts,
                        "symbol": pair,
                        "type": msg["type"],
                        "side": side,
                        "price": price,
                        "qty": qty,
                        "checksum": msg.get("checksum", 1),
                    }
                )
    return pl.DataFrame(rows, schema=BOOK_SCHEMA)


def _write_final(path: Path, frame: pl.DataFrame, *, sidecar: bool = True) -> None:
    """Write a committed canonical final, and (unless suppressed) its correct `.sha256` sidecar in
    `verify_manifest`'s token format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path, compression="zstd")
    if sidecar:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")


@dataclasses.dataclass
class Tree:
    """A synthetic canonical archive plus the mutations these tests need."""

    primary: Path
    pairs: list[str]
    hours: int

    def hour(self, index: int) -> datetime:
        return H + timedelta(hours=index)

    def final(self, pair: str, index: int) -> Path:
        base, quote = pair.split("/")
        h = self.hour(index)
        return self.primary / base / quote / "book" / f"{h:%Y}" / f"{h:%m}" / f"{h:%d}" / f"{h:%H}.parquet"

    def sidecar(self, pair: str, index: int) -> Path:
        final = self.final(pair, index)
        return final.with_name(final.name + ".sha256")

    def keys(self) -> list[tuple[str, datetime]]:
        return sorted((pair, self.hour(index)) for pair in self.pairs for index in range(self.hours))

    def write_hour(self, pair: str, index: int, *, snapshot: bool = False) -> None:
        messages = _coherent_messages() if snapshot else _coherent_messages()[1:]
        _write_final(self.final(pair, index), _explode(pair, self.hour(index), messages))
        self.hours = max(self.hours, index + 1)

    def corrupt_hour(self, pair: str, index: int) -> None:
        """Rewrite final AND sidecar to garbage — the "the bytes changed and they are bad" shape."""
        self.final(pair, index).write_bytes(b"not a parquet file")
        self.sidecar(pair, index).write_text("garbage  01.parquet\n")

    def delete_hour(self, pair: str, index: int) -> None:
        self.final(pair, index).unlink()
        self.sidecar(pair, index).unlink()

    def rewrite_final_only(self, pair: str, index: int) -> None:
        """New, still-readable bytes under the OLD sidecar — the manifest-mismatch shape."""
        _write_final(self.final(pair, index), _explode(pair, self.hour(index), _coherent_messages()[:2]), sidecar=False)

    def rewrite_hour_shorter(self, pair: str, index: int) -> None:
        """Fewer messages, with a MATCHING new sidecar — a legitimately rewritten hour (the
        reconciler splicing secondary data in). Stale by hash, and its fresh raw tuple differs from
        the cached one, so an audit that wrongly sampled it while it waits in the drain would report
        a mismatch."""
        _write_final(self.final(pair, index), _explode(pair, self.hour(index), _coherent_messages()[1:3]))

    def write_unordered_hour(self, pair: str, index: int) -> None:
        """An hour whose `ts` runs BACKWARDS, with a CORRECT sidecar — an honestly broken hour. It
        verifies as `ts_ordered=False` the first time; doctoring that one fact green in the checkpoint
        then makes it cache-trusted forever, since a green row matches its (untouched) sidecar."""
        messages = [dict(msg, offset=offset) for msg, offset in zip(_coherent_messages()[1:], (30, 20, 10), strict=True)]
        _write_final(self.final(pair, index), _explode(pair, self.hour(index), messages))


def make_tree(tmp_path: Path, pairs: list[str], hours: int, *, snapshot_first_hour: bool = True) -> Tree:
    """`pairs` × `hours` contiguous canonical book hours. Hour 0 opens with a snapshot (so the whole
    run chain-anchors); every later hour opens with an update, like most real hours."""
    tree = Tree(primary=tmp_path / "primary", pairs=list(pairs), hours=0)
    for pair in pairs:
        for index in range(hours):
            tree.write_hour(pair, index, snapshot=index == 0 and snapshot_first_hour)
    return tree


# --- D1: raw facts are cached, the chain verdict is refolded every run ------------------------------


def test_equivalence_full_vs_warm_incremental(tmp_path: Path) -> None:
    """Spec D1: a warm no-change incremental run equals the full replay field-for-field."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR", "ETH/EUR"], hours=6)
    full = verify_replay(tree.primary, None, depth=10)
    state = tmp_path / "state"

    first, c1 = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10)
    assert first == full and c1.replayed == 12 and c1.reused == 0

    second, c2 = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    assert second == full and c2.replayed == 0 and c2.reused == 12


def test_d1_sequence_chain_verdict_is_never_cached(tmp_path: Path) -> None:
    """Caching `_chain_anchor`'s OUTPUT instead of the raw `opens_with_snapshot` fact makes anchoring
    irrevocable (`True OR anything = True`) — hour 2 would stay green forever while its predecessor
    is broken, and `failed_hours` would read 0."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)  # hour0 snapshot; hours 1,2 chained
    state = tmp_path / "state"

    first, _ = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    assert all(r.anchored for r in first)

    tree.corrupt_hour("BTC/EUR", 1)
    second, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    by_hour = {r.hour: r for r in second}
    assert census.replayed == 1  # only hour 1 — hour 2 was NOT re-replayed
    assert by_hour[tree.hour(1)].error is not None  # replayed (hash changed), fails
    assert not by_hour[tree.hour(2)].anchored  # NOT re-replayed, but the refold must flip it
    assert by_hour[tree.hour(0)].anchored  # its own raw snapshot fact is untouched


# --- D4: mandatory new hours, then an oldest-first drain under the budget ---------------------------


def test_new_hours_are_mandatory_even_at_zero_budget(tmp_path: Path) -> None:
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    tree.sidecar("BTC/EUR", 0).unlink()  # an OLD hour goes stale: drainable, never mandatory
    tree.write_hour("BTC/EUR", 3)  # a NEW hour: mandatory at any budget

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0, drain_budget_s=0.0)

    assert census.replayed == 1 and census.pending == 1 and census.reused == 2
    assert {r.hour for r in results} == {tree.hour(i) for i in range(4)}  # hours_total grew
    # the deferred hour is not re-verified, so its last-known verdict still stands — that backlog is
    # what `pending` announces, and it is why the drain must not silently swallow new hours
    assert {r.hour: r for r in results}[tree.hour(0)].error is None


def test_version_bump_drains_oldest_first_within_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A version bump makes every hour stale; the budget lets only the oldest through, and the
    undrained rows keep their OLD version so the next night resumes where this one stopped."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR", "ETH/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    monkeypatch.setattr(replay_module, "VERIFIER_VERSION", replay_module.VERIFIER_VERSION + 1)
    ticks = itertools.count()  # a controlled clock: 1 s per reading, so the budget is deterministic
    monkeypatch.setattr(replay_module, "_monotonic", lambda: float(next(ticks)))

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0, drain_budget_s=3.5)

    assert 0 < census.replayed < 6 and census.pending == 6 - census.replayed
    updated = load_checkpoint(state)
    assert updated is not None
    bumped = sorted((key for key, row in updated.items() if row.verifier_version == 2), key=lambda k: (k[1], k[0]))
    kept = [key for key, row in updated.items() if row.verifier_version == 1]
    assert len(bumped) == census.replayed and len(kept) == census.pending
    # oldest-first, `(hour, pair)`-sorted: the drained set is exactly the head of that order
    assert bumped == sorted(tree.keys(), key=lambda k: (k[1], k[0]))[: census.replayed]


def test_reverify_all_marks_every_hour_stale_without_making_it_mandatory(tmp_path: Path) -> None:
    """`--reverify-all` is the operator's only escape hatch for a deliberate full re-verification, and
    it must go through the DRAIN, not the mandatory path: a full re-verification that ignored the
    budget would run the whole archive in one night, which is the runtime this spec exists to bound."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=4)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    _, whole = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0, reverify_all=True)
    assert (whole.replayed, whole.reused, whole.pending) == (4, 0, 0)

    results, budgeted = verify_replay_incremental(
        tree.primary, None, state_dir=state, depth=10, audit_k=0, reverify_all=True, drain_budget_s=0.0
    )
    # stale, but not NEW: at zero budget every hour defers instead of replaying
    assert (budgeted.replayed, budgeted.reused, budgeted.pending) == (0, 0, 4)
    assert len(results) == 4  # the whole archive still gets a verdict, from cache


# --- D2/D3: failures and manifest violations are never trusted from cache ---------------------------


def test_cached_failure_is_always_replayed_and_heals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient failure (the `ro,soft` NFS EIO shape) is cached against the CORRECT byte hash, so
    only the cached-failure clause can re-replay it — and the next run must heal it unaided."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=2)
    state = tmp_path / "state"
    target = tree.final("BTC/EUR", 1)
    real_replay_segment = replay_module.replay_segment

    def flaky(path: Path, symbol: str, depth: int):
        result = real_replay_segment(path, symbol, depth)
        if path == target:
            return dataclasses.replace(result, replay_ok=False, error="OSError: [Errno 5] Input/output error")
        return result

    monkeypatch.setattr(replay_module, "replay_segment", flaky)
    first, c1 = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    assert c1.replayed == 2 and {r.hour: r for r in first}[tree.hour(1)].error is not None

    monkeypatch.undo()
    cached = load_checkpoint(state)
    assert cached is not None
    # the bytes never changed: hash and version both match, so ONLY "cached verdict is a failure" is left
    assert cached[("BTC/EUR", tree.hour(1))].byte_hash == hashlib.sha256(target.read_bytes()).hexdigest()

    second, c2 = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert c2.replayed == 1 and c2.reused == 1
    healed = {r.hour: r for r in second}[tree.hour(1)]
    assert healed.error is None and healed.passed


def test_sidecar_missing_or_mismatched_is_a_failure_and_never_trusted(tmp_path: Path) -> None:
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    tree.sidecar("BTC/EUR", 1).unlink()
    for _ in range(2):  # replayed on EVERY run, never cached as good
        results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
        failing = {r.hour: r for r in results}[tree.hour(1)]
        assert failing.error is not None and "manifest" in failing.error
        assert census.replayed == 1 and census.reused == 2

    # separately: a final rewritten under its OLD sidecar — the mismatch is named when it is replayed
    other = make_tree(tmp_path / "other", pairs=["BTC/EUR"], hours=2)
    other.rewrite_final_only("BTC/EUR", 1)

    results, _ = verify_replay_incremental(other.primary, None, state_dir=tmp_path / "other-state", depth=10, audit_k=0)

    assert "manifest mismatch" in {r.hour: r for r in results}[other.hour(1)].error


def test_transient_read_error_is_isolated_to_the_hour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec D3/F5: the pre-replay hash sits OUTSIDE `replay_segment`'s never-raises contract, so its
    `OSError` must become one hour's failure, not the whole run's crash."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=4)
    state = tmp_path / "state"
    target = tree.final("BTC/EUR", 2)
    real_read_bytes = Path.read_bytes

    def flaky(self: Path) -> bytes:
        if self == target:
            raise OSError(5, "Input/output error")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", flaky)

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert census.replayed == 4 and len(results) == 4
    by_hour = {r.hour: r for r in results}
    assert by_hour[tree.hour(2)].error is not None
    assert all(by_hour[tree.hour(i)].error is None for i in (0, 1, 3))  # every other hour still verdicted


# --- D5: the recorded environment is forensics, NOT an invalidation key -----------------------------


def test_recorded_environment_never_invalidates(tmp_path: Path) -> None:
    """Adding `polars_version`/`depth` to the stale predicate passes every other test in this file and
    ships D5's permanent-mid-drain pathology — so it is pinned by construction here."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    rows = load_checkpoint(state)
    assert rows is not None
    key = ("BTC/EUR", tree.hour(1))
    rows[key] = dataclasses.replace(rows[key], polars_version="0.0.0+doctored", depth=999)
    save_checkpoint(state, rows.values())

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert census.replayed == 0 and census.reused == 3


# --- D7: an empty or shrunken enumeration never destroys state --------------------------------------


def test_empty_enumeration_leaves_checkpoint_untouched(tmp_path: Path) -> None:
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=4)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    before = (state / "checkpoint.parquet").read_bytes()
    empty = tmp_path / "empty"
    empty.mkdir()

    results, census = verify_replay_incremental(empty, None, state_dir=state, depth=10, audit_k=0)

    assert results == []
    assert (census.replayed, census.reused, census.audited, census.pending, census.evicted) == (0, 0, 0, 0, 0)
    assert census.audit_mismatches == () and census.duration_s >= 0
    assert (state / "checkpoint.parquet").read_bytes() == before


def test_eviction_over_ten_percent_refuses_before_replaying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = make_tree(tmp_path, pairs=["BTC/EUR", "ETH/EUR"], hours=10)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    before = (state / "checkpoint.parquet").read_bytes()

    for index in (7, 8, 9):  # 3 of 20 checkpointed hours: over the 10% refusal line
        tree.delete_hour("BTC/EUR", index)
    tree.write_hour("ETH/EUR", 10)  # a brand-new mandatory hour: real work the guard must precede

    calls: list[Path] = []
    real_replay_segment = replay_module.replay_segment

    def counted(path: Path, symbol: str, depth: int):
        calls.append(path)
        return real_replay_segment(path, symbol, depth)

    monkeypatch.setattr(replay_module, "replay_segment", counted)

    with pytest.raises(EvictionRefusedError):
        verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert calls == []  # refused BEFORE any replay: a refused run wastes no work
    assert (state / "checkpoint.parquet").read_bytes() == before


def test_eviction_at_exactly_ten_percent_proceeds(tmp_path: Path) -> None:
    """The refusal is for eviction ABOVE 10%, so the boundary itself must proceed: `0.1 * 20 == 2.0`
    and `2 > 2.0` is False. Without this, `>` and `>=` are indistinguishable — the two neighbouring
    tests straddle the boundary without ever landing on it."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR", "ETH/EUR"], hours=10)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    for pair in ("BTC/EUR", "ETH/EUR"):  # exactly 2 of 20
        tree.delete_hour(pair, 9)

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert census.evicted == 2 and census.reused == 18 and len(results) == 18
    updated = load_checkpoint(state)
    assert updated is not None and len(updated) == 18


def test_eviction_under_ten_percent_proceeds_and_evicts(tmp_path: Path) -> None:
    tree = make_tree(tmp_path, pairs=["BTC/EUR", "ETH/EUR"], hours=10)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    tree.delete_hour("BTC/EUR", 4)  # 1 of 20: under the line

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert census.evicted == 1 and census.replayed == 0 and census.reused == 19 and len(results) == 19
    updated = load_checkpoint(state)
    assert updated is not None and len(updated) == 19
    assert ("BTC/EUR", tree.hour(4)) not in updated


# --- D8: mid-run progress survives a kill -----------------------------------------------------------


def test_flush_every_250_survives_a_kill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=8)
    state = tmp_path / "state"
    monkeypatch.setattr(replay_module, "_FLUSH_EVERY", 3)
    real_replay_segment = replay_module.replay_segment
    calls = itertools.count(1)

    def killer(path: Path, symbol: str, depth: int):
        if next(calls) == 5:
            raise SystemExit("killed mid-run")
        return real_replay_segment(path, symbol, depth)

    monkeypatch.setattr(replay_module, "replay_segment", killer)
    with pytest.raises(SystemExit):
        verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    monkeypatch.undo()

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    assert census.replayed == 5 and census.reused == 3 and len(results) == 8  # the flushed 3 survived


# --- D6: the sampled audit — the one guard that can detect the cache being wrong --------------------


def doctor_checkpoint(state: Path, key: tuple[str, datetime], **facts: object) -> None:
    """Plant a lie in one checkpoint row: the thing the audit exists to catch.

    A lie that reads as a FAILURE never reaches the audit — `_cached_failure` re-replays any row whose
    `error`/`ts_ordered`/`checksum_present`/`replay_ok` says so; only a lie the stale predicate reads
    as HEALTHY survives into a reused row."""
    rows = load_checkpoint(state)
    assert rows is not None and key in rows
    rows[key] = dataclasses.replace(rows[key], **facts)
    save_checkpoint(state, rows.values())


class _RecordingRandom(random.Random):
    """Records every population `rng.sample` is handed, so a test can assert what was SAMPLED FROM
    rather than inferring it from the mismatches that happened to result."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.populations: list[list] = []

    def sample(self, population, k, *, counts=None):  # type: ignore[override]
        self.populations.append(list(population))
        return super().sample(population, k, counts=counts)


def test_audit_trips_on_a_doctored_fact(tmp_path: Path) -> None:
    """Plant a lie in the checkpoint; the audit must catch it (spec D6: "its own proof is mandatory").

    `opens_with_snapshot` is the fact to lie about. It is deliberately excluded from `_cached_failure`
    (most real hours open with a plain update), so the stale predicate structurally CANNOT see the
    lie — and it is the raw fact `_chain_anchor` folds, so a lie there silently greens a broken chain
    forever. `rows`/`messages` are in neither predicate at all — the shape of a mis-keyed or truncated
    row."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=4)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    doctor_checkpoint(state, ("BTC/EUR", tree.hour(2)), opens_with_snapshot=True)  # hour 2 opens with an update
    doctor_checkpoint(state, ("BTC/EUR", tree.hour(1)), rows=999, messages=999)

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=4, rng=random.Random(7))

    assert census.replayed == 0 and census.reused == 4 and census.audited == 4
    # every offender is named, not just the first one sampled
    assert set(census.audit_mismatches) == {"BTC/EUR 2026-07-14 04:00", "BTC/EUR 2026-07-14 03:00"}
    healed = load_checkpoint(state)
    assert healed is not None
    assert not healed[("BTC/EUR", tree.hour(2))].opens_with_snapshot  # self-healed
    assert (healed[("BTC/EUR", tree.hour(1))].rows, healed[("BTC/EUR", tree.hour(1))].messages) == (4, 3)


def test_audit_trips_on_a_doctored_byte_hash(tmp_path: Path) -> None:
    """A lie in the identity itself — checkpoint corruption, or overlay bit rot the manifest sweep
    cannot see.

    The lie is planted in BOTH the checkpoint row and the sidecar on purpose: `_is_stale` compares
    exactly those two, so a checkpoint-only lie is caught (and re-replayed) before the audit ever sees
    the row. A byte-hash lie can only SURVIVE into a cache-trusted row when the sidecar agrees with
    it — which is precisely the state the audit owns, since it re-hashes the actual bytes."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    lie = "0" * 64
    doctor_checkpoint(state, ("BTC/EUR", tree.hour(1)), byte_hash=lie)
    tree.sidecar("BTC/EUR", 1).write_text(f"{lie}  03.parquet\n")

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=3, rng=random.Random(1))

    assert census.replayed == 0 and census.audited == 3  # reused, never re-replayed: only the audit can see it
    assert census.audit_mismatches == ("BTC/EUR 2026-07-14 03:00",)
    healed = load_checkpoint(state)
    assert healed is not None
    real = hashlib.sha256(tree.final("BTC/EUR", 1).read_bytes()).hexdigest()
    assert healed[("BTC/EUR", tree.hour(1))].byte_hash == real


def test_audit_catches_bytes_rewritten_under_an_unchanged_sidecar(tmp_path: Path) -> None:
    """The real-world shape of the same hole: the bytes changed, the sidecar did not. The cached hash
    still equals the sidecar, so the stale predicate reads the hour as unchanged and reuses it — every
    night, indefinitely. The audit re-hashes and re-replays, and the healed row now carries the
    manifest error, so `_cached_failure` re-replays it tomorrow unaided."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    tree.rewrite_final_only("BTC/EUR", 1)

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=3, rng=random.Random(3))

    assert census.replayed == 0 and census.audited == 3
    assert census.audit_mismatches == ("BTC/EUR 2026-07-14 03:00",)
    healed = load_checkpoint(state)
    assert healed is not None and "manifest mismatch" in healed[("BTC/EUR", tree.hour(1))].error


def test_audit_heals_the_returned_results_not_only_the_checkpoint(tmp_path: Path) -> None:
    """Patching just the checkpoint makes the audit report a mismatch while the returned results still
    read every hour green — `failed_hours` would count 0 over a rotted archive, and `_chain_anchor`
    would fold the lie forward into every successor. So both are asserted: the audited hour's own
    verdict must carry the fresh failure, AND its successor — which anchors only through it — must
    lose its anchor in the refold that runs after the audit."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    tree.rewrite_final_only("BTC/EUR", 1)  # bit rot: new bytes, unchanged sidecar → still reused

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=3, rng=random.Random(3))

    assert census.audit_mismatches == ("BTC/EUR 2026-07-14 03:00",)
    by_hour = {r.hour: r for r in results}
    assert by_hour[tree.hour(1)].error is not None and not by_hour[tree.hour(1)].passed
    assert not by_hour[tree.hour(2)].anchored  # the healed failure re-folds through the chain
    assert by_hour[tree.hour(0)].passed  # and reaches no further than it should


def test_audit_catches_a_broken_hour_doctored_green(tmp_path: Path) -> None:
    """The lie the audit most needs to catch: an hour the instrument had ALREADY measured as broken,
    whose row is then doctored green.

    `ts_ordered=False` is a cached failure, so this hour re-replays nightly and heals or re-fails
    honestly. Flip that one fact to `True` and the row stops being a failure while its bytes — and so
    its sidecar — never changed: it is reused forever, the instrument certifying an hour it has itself
    seen to be broken. Nothing in the stale predicate can ever look at it again. Only the audit can."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    tree.write_unordered_hour("BTC/EUR", 1)
    state = tmp_path / "state"

    honest, _ = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    assert not {r.hour: r for r in honest}[tree.hour(1)].ts_ordered  # measured broken, honestly

    doctor_checkpoint(state, ("BTC/EUR", tree.hour(1)), ts_ordered=True)

    results, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=3, rng=random.Random(2))

    assert (census.replayed, census.reused, census.audited) == (0, 3, 3)  # never re-replayed: reused
    assert census.audit_mismatches == ("BTC/EUR 2026-07-14 03:00",)
    assert not {r.hour: r for r in results}[tree.hour(1)].ts_ordered
    healed = load_checkpoint(state)
    assert healed is not None and not healed[("BTC/EUR", tree.hour(1))].ts_ordered


def test_audit_compares_every_cached_raw_fact() -> None:
    """Completeness pin on the compare tuple, by name — because one field in it cannot be pinned
    behaviourally: `_is_stale` only reuses an hour whose sidecar EQUALS its cached `byte_hash`, so a
    byte-hash divergence can never reach the audit without the manifest `error` it produces arriving
    with it. This pins it (and every other raw fact) anyway: a fact added to `CheckpointRow` and
    forgotten here fails this."""
    forensics = {"pair", "hour", "verifier_version", "polars_version", "depth", "verified_at"}
    raw = [field.name for field in dataclasses.fields(CheckpointRow) if field.name not in forensics]
    row = CheckpointRow(
        pair="BTC/EUR",
        hour=H,
        byte_hash="a" * 64,
        verifier_version=1,
        opens_with_snapshot=True,
        ts_ordered=False,
        checksum_present=True,
        replay_ok=False,
        error="boom",
        rows=7,
        messages=3,
        polars_version="1.2.3",
        depth=10,
        verified_at=H,
    )

    assert replay_module._audit_facts(row) == tuple(getattr(row, name) for name in raw)


def test_audit_k_larger_than_cache_degrades_to_all(tmp_path: Path) -> None:
    """`min(audit_k, len(reused))`: a small archive (or a big drain night) must audit everything it
    has, not raise `ValueError: Sample larger than population`."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=100, rng=random.Random(5))

    assert census.reused == 3 and census.audited == 3 and census.audit_mismatches == ()


def test_audit_zero_disables_cleanly(tmp_path: Path) -> None:
    """`audit_k=0` does no work at all — no sampling, no re-replay (every other test in this file
    depends on that, and the operator escape hatch is worthless if it still costs 25 replays)."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    before = load_checkpoint(state)
    assert before is not None

    calls: list[Path] = []
    real_replay_segment = replay_module.replay_segment

    def counted(path: Path, symbol: str, depth: int):
        calls.append(path)
        return real_replay_segment(path, symbol, depth)

    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(replay_module, "replay_segment", counted)
    try:
        _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    finally:
        monkeypatched.undo()

    assert calls == []
    assert census.audited == 0 and census.audit_mismatches == () and census.reused == 3
    after = load_checkpoint(state)
    assert after is not None
    assert {key: row.verified_at for key, row in after.items()} == {key: row.verified_at for key, row in before.items()}


def test_audited_fresh_result_replaces_cached_row(tmp_path: Path) -> None:
    """An audited hour's row is REPLACED by the fresh one even when it matched: the checkpoint must
    record that this hour was re-verified under today's code, not last month's."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    before = load_checkpoint(state)
    assert before is not None

    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=100, rng=random.Random(11))

    assert census.audited == 3 and census.audit_mismatches == ()
    after = load_checkpoint(state)
    assert after is not None
    assert all(after[key].verified_at > before[key].verified_at for key in before)
    # the facts themselves are unchanged — a clean audit heals nothing and breaks nothing
    assert all(dataclasses.replace(after[key], verified_at=before[key].verified_at) == before[key] for key in before)


def test_audit_never_samples_pending_rows(tmp_path: Path) -> None:
    """Spec D6/F1: the audit samples the REUSED keys only. A pending row is known-stale by
    construction — here, two legitimately rewritten hours the budget deferred — so auditing one
    mismatches with certainty, failing the run every single night of a legitimate drain. That is the
    exact pathology this spec exists to avoid, so the population itself is asserted, not just the
    (absence of) mismatches it produced."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=6)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)

    for index in (4, 5):
        tree.rewrite_hour_shorter("BTC/EUR", index)

    rng = _RecordingRandom(13)
    _, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=10, rng=rng, drain_budget_s=0.0)

    assert (census.replayed, census.reused, census.pending) == (0, 4, 2)
    assert census.audited == 4 and census.audit_mismatches == ()  # a clean drain night never self-DoSes
    deferred = {("BTC/EUR", tree.hour(index)) for index in (4, 5)}
    assert len(rng.populations) == 1 and set(rng.populations[0]).isdisjoint(deferred)
    assert set(rng.populations[0]) == {("BTC/EUR", tree.hour(index)) for index in range(4)}
