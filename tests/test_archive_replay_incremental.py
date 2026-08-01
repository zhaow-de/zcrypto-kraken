"""TDD for `verify_replay_incremental` — the incremental orchestrator (spec 00078).

Every test here is a CONSTRUCTED proof of one clause, not a restatement of it: the checkpoint caches
only RAW per-hour facts and the chain verdict is refolded every run (D1), failures and manifest
violations are never trusted from cache (D2/D3), new hours are mandatory while older stale hours
drain oldest-first under a wall-clock budget (D4), the recorded environment does NOT invalidate (D5),
an empty or shrunken enumeration never destroys state (D7), and mid-run progress survives a kill
(D8).

The synthetic-tree idiom (per-level fan-out + committed final + `.sha256` sidecar) is
`tests/test_archive_replay.py`'s, extended with the mutations these tests need.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.archive import replay as replay_module
from cli.archive.checkpoint import load_checkpoint, save_checkpoint
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


def make_tree(tmp_path: Path, pairs: list[str], hours: int, *, snapshot_first_hour: bool = True) -> Tree:
    """`pairs` × `hours` contiguous canonical book hours. Hour 0 opens with a snapshot (so the whole
    run chain-anchors); every later hour opens with an update, exactly like ~96% of real hours."""
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
    """The review's breaking sequence: H chained through a good H-1; H-1 rewritten to fail; H must flip.

    Caching `_chain_anchor`'s OUTPUT instead of the raw `opens_with_snapshot` fact makes anchoring
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
