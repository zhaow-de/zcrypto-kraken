"""Tests for the gate-export scoring cache primitives (cli/engine/gate_cache.py, spec 00060):
replay_fingerprint (D3 -- covers the replay CODE, not just the journal), evidence_fingerprint
(D2), and load_cache/save_cache (D5 fail-open, D6 atomic write). Everything here is synthetic --
no dataset access, no real replay."""

from __future__ import annotations

import inspect
import json
import pathlib
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

import cli.engine.gate_cache as gate_cache
from cli.engine import CycleOutcome, CycleRecord, SnapshotEntry
from cli.engine.gate_cache import (
    CACHE_SCHEMA_VERSION,
    GateCache,
    due_for_reverification,
    evidence_fingerprint,
    load_cache,
    oldest_verification_age,
    replay_fingerprint,
    save_cache,
    slice_of,
)
from cli.portfolio import CrossfreqSystemConfig

# --- fixtures: a synthetic CycleRecord, mirroring tests/test_engine_journal.py's shape ----------

CYCLE_TS = datetime(2026, 7, 10, 8, 0)
VALID_H4_LAST = datetime(2026, 7, 10, 4, 0)
VALID_DAILY_LAST = datetime(2026, 7, 9, 0, 0)


def _entry(
    pair: str, grid: str, first_ts: datetime, last_ts: datetime, content_hash: str = "a" * 64, n_bars: int = 3
) -> SnapshotEntry:
    return SnapshotEntry(
        pair=pair,
        grid=grid,
        n_bars=n_bars,
        first_ts=first_ts,
        last_ts=last_ts,
        content_hash=content_hash,
        path=f"/snap/{pair}/{grid}.parquet",
    )


def _record(**overrides) -> CycleRecord:
    snapshots = overrides.pop(
        "snapshots",
        (
            _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64),
            _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "b" * 64),
            _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "c" * 64),
            _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "d" * 64),
        ),
    )
    fields = {
        "schema_version": 1,
        "cycle_ts": CYCLE_TS,
        "snapshots": snapshots,
        "final_targets": {"BTC": 0.1, "ETH": -0.05},
        "started_at": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=5),
        "code_version": "0.1.0+fast",
        "builder_path": "fast",
    }
    fields.update(overrides)
    return CycleRecord(**fields)


def _outcome(**overrides) -> CycleOutcome:
    fields = {
        "cycle_ts": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=5),
        "compare_passed": True,
        "mismatch": False,
        "validation_failed": False,
    }
    fields.update(overrides)
    return CycleOutcome(**fields)


# --- evidence_fingerprint ---------------------------------------------------------------------


def test_evidence_fingerprint_changes_with_each_input():
    base = evidence_fingerprint(_record())

    # Mutating a snapshot's content_hash changes it.
    mutated_snapshots = (
        _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "z" * 64),
        _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "b" * 64),
        _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "c" * 64),
        _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "d" * 64),
    )
    assert evidence_fingerprint(_record(snapshots=mutated_snapshots)) != base

    # Mutating cycle_ts changes it.
    assert evidence_fingerprint(_record(cycle_ts=CYCLE_TS + timedelta(hours=4))) != base

    # Mutating completed_at changes it.
    assert evidence_fingerprint(_record(completed_at=CYCLE_TS + timedelta(minutes=6))) != base

    # Mutating final_targets changes it.
    assert evidence_fingerprint(_record(final_targets={"BTC": 0.2, "ETH": -0.05})) != base

    # An identical record reproduces the same fingerprint.
    assert evidence_fingerprint(_record()) == base


def test_evidence_fingerprint_changes_when_n_bars_tampered_leaving_content_hash_untouched():
    # replay_cycle reconciles the freshly read data against entry.n_bars/first_ts/last_ts and
    # raises EngineJournalError on disagreement (see cli.engine.concordance.replay_cycle) -- an
    # evidence fingerprint keyed on content_hash alone would keep serving a stale cached PASS for a
    # record whose n_bars a real replay would reject. content_hash is deliberately left unchanged
    # here to isolate the metadata-only tamper.
    base = evidence_fingerprint(_record())
    tampered_snapshots = (
        _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64, n_bars=4),
        _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "b" * 64),
        _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "c" * 64),
        _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "d" * 64),
    )
    assert evidence_fingerprint(_record(snapshots=tampered_snapshots)) != base


# --- evidence_fingerprint: each evidence-key field pinned by a stale HIT, not by presence (D2/D3) --


def _tamper_entry(index: int, **field) -> tuple[SnapshotEntry, ...]:
    """`_record()`'s default snapshots with exactly one field of `entries[index]` replaced, via
    `dataclasses.replace` rather than rebuilding through `_entry()` -- `_entry()`'s default `path`
    embeds `{pair}`/`{grid}` into the string, so reconstructing a pair/grid tamper through `_entry()`
    would ALSO change `path`, contaminating each field's pin with another field's coverage and
    breaking the Step 4 mutation cross-check (each mutation must fail exactly its own test)."""
    entries = list(_record().snapshots)
    entries[index] = replace(entries[index], **field)
    return tuple(entries)


def _assert_stale_entry_is_rejected(tmp_path, pristine: CycleRecord, tampered: CycleRecord) -> None:
    """D2's pin shape, shared by every evidence-key field test below: a field is pinned by a stale
    cache HIT, never by field presence in the digest -- a test asserting "the field appears in the
    payload" passes against a fingerprint that ignores it entirely. Stores an entry keyed on the
    PRISTINE record's evidence_fingerprint through a real save_cache/load_cache round trip, then
    asserts the fingerprint differs once the record on disk is the TAMPERED one. A stale HIT here is
    exactly the exploit the mutation audit proved end-to-end for all five fields
    (docs/research/14.phase6-gate-guarantee-mutation-audits.md G5-G7, G9-G10).

    SCOPE, stated precisely because an earlier version of this docstring overstated it: these five
    RECONSTRUCT `_evaluate_journal`'s hit test (`command.py:255`, `cached_entry[0] == fp and not
    reverify`); they do not OBSERVE it. `_evaluate_journal` is never called here, and the round trip
    carries no discriminating power of its own -- every one of the five mutants is killed by the
    first assertion, `fp_tampered != fp_pristine`. It earns its place by pinning evidence_fp
    round-trip fidelity, not by proving the wiring. The end-to-end wiring is pinned separately by
    `test_tampered_record_misses_cache` in tests/test_engine_gate_export_cache.py, which asserts
    `calls == [CYCLE_TS]`. The two compose: that one proves the digest gates the cache, these five
    prove each field is in the digest. Do not read them as end-to-end coverage."""
    fp_pristine = evidence_fingerprint(pristine)
    fp_tampered = evidence_fingerprint(tampered)
    assert fp_tampered != fp_pristine

    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"
    outcome = _outcome(cycle_ts=pristine.cycle_ts, completed_at=pristine.completed_at)
    cache = GateCache(replay_fp=replay_fp, entries={pristine.cycle_ts: (fp_pristine, outcome, CYCLE_TS)})
    save_cache(path, cache)
    loaded = load_cache(path, replay_fp)

    cached_entry = loaded.entries[pristine.cycle_ts]
    assert cached_entry[0] != fp_tampered, "stale HIT: the tampered record's fingerprint still matches the cached entry"


def test_evidence_fingerprint_pins_first_ts_via_stale_hit(tmp_path):
    # Finding 5/G5-G6: replay_cycle reconciles freshly-read data against entry.first_ts and raises
    # EngineJournalError on disagreement -- a fingerprint blind to first_ts would let a cached PASS
    # survive a tamper a real replay would reject outright (the audit's B04 exploit, re-confirmed
    # end-to-end through _evaluate_journal).
    pristine = _record()
    tampered = _record(snapshots=_tamper_entry(0, first_ts=pristine.snapshots[0].first_ts + timedelta(hours=1)))
    _assert_stale_entry_is_rejected(tmp_path, pristine, tampered)


def test_evidence_fingerprint_pins_last_ts_via_stale_hit(tmp_path):
    # Finding 6/G5-G6: same tamper class as first_ts (the audit's B05 exploit) -- the other half of
    # the replay_cycle reconciliation window.
    pristine = _record()
    tampered = _record(snapshots=_tamper_entry(0, last_ts=pristine.snapshots[0].last_ts + timedelta(hours=1)))
    _assert_stale_entry_is_rejected(tmp_path, pristine, tampered)


def test_evidence_fingerprint_pins_pair_via_order_preserving_stale_hit(tmp_path):
    # Findings 7/G9-G10 (spec D3): evidence_fingerprint sorts entries by (pair, grid) before
    # digesting them, so an order-CHANGING pair tamper is masked -- the digest would change from the
    # reordering alone even if `pair` were dropped from the payload entirely. That masking is
    # exactly what fooled the first mutation audit into ruling pair/grid "equivalent mutants" (see
    # docs/research/14.phase6-gate-guarantee-mutation-audits.md G9-G10) -- one non-distinguishing
    # probe is not evidence an "equivalent mutant" ruling generalizes. "ETH" -> "FTH" is
    # order-PRESERVING: FTH still sorts after the UNTAMPERED "ETH"/1440 entry, into the same slot
    # "ETH" held (canonical order stays [1, 0, 3, 2]), so only tampering `pair` itself -- never the
    # reordering side-channel -- can move this test. NOT "sorts after BTC": ETH/1440 is also present,
    # and a tamper chosen by that weaker rule (e.g. "CTH") reorders to [1, 0, 2, 3] and is MASKED --
    # the digest would then move from the reordering alone, passing even with `pair` dropped entirely.
    # `path` is deliberately left at its pristine "/snap/ETH/240.parquet" value
    # (dataclasses.replace, not _entry()) so this test isolates `pair` from finding 10's `path` pin
    # below.
    pristine = _record()
    tampered = _record(snapshots=_tamper_entry(2, pair="FTH"))
    _assert_stale_entry_is_rejected(tmp_path, pristine, tampered)


def test_evidence_fingerprint_pins_grid_via_order_preserving_stale_hit(tmp_path):
    # Finding 8/G9-G10 (spec D3): same order-preservation requirement as pair, and the same reason
    # (see the comment above). Entries sort by (pair, grid) and grid compares as a STRING, so "1440"
    # < "240" lexicographically (leading "1" < "2") -- "1441" < "240" too, so renaming the BTC daily
    # grid "1440" -> "1441" keeps it in the same sorted slot within the BTC group. Only tampering
    # `grid` itself can move this test.
    pristine = _record()
    tampered = _record(snapshots=_tamper_entry(1, grid="1441"))
    _assert_stale_entry_is_rejected(tmp_path, pristine, tampered)


def test_evidence_fingerprint_pins_path_via_stale_hit(tmp_path):
    # Finding 10/G7: `path` is the file a real replay actually reads content from. Repointing one
    # entry's path at ANOTHER pair's parquet -- via dataclasses.replace, so pair/grid/content_hash/
    # n_bars/first_ts/last_ts on that entry stay byte-identical -- isolates `path` specifically (the
    # audit's B07 exploit: same stale-HIT shape as every field above).
    pristine = _record()
    tampered = _record(snapshots=_tamper_entry(0, path=pristine.snapshots[2].path))  # BTC/240 repointed at ETH/240's file
    _assert_stale_entry_is_rejected(tmp_path, pristine, tampered)


# --- replay_fingerprint (D3) --------------------------------------------------------------------


def test_replay_fingerprint_covers_replay_code(tmp_path, monkeypatch):
    # This is D3's pin: the fingerprint must change when a covered module's bytes change, and must
    # be stable when nothing covered changes -- a journal-only (or config-only) implementation
    # would pass a "stable otherwise" check but fail the "changes with the code" half below.
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("# module a v1\n")
    f2.write_text("# module b v1\n")
    monkeypatch.setattr(gate_cache, "_replay_code_paths", lambda: (f1, f2))

    fp_before = replay_fingerprint()

    # Stable across repeated calls with unchanged bytes.
    assert replay_fingerprint() == fp_before

    # Changing one covered file's bytes changes the fingerprint.
    f2.write_text("# module b v2 -- a comment-only edit is enough (deliberately over-sensitive)\n")
    fp_after = replay_fingerprint()
    assert fp_after != fp_before

    # Changing the effective config also changes the fingerprint (independent of file bytes).
    fp_default_config = replay_fingerprint()
    fp_other_config = replay_fingerprint(CrossfreqSystemConfig(long_cap=0.5))
    assert fp_other_config != fp_default_config


def test_replay_fingerprint_default_covers_the_real_files():
    # No monkeypatching -- exercises the real, hard-coded file list against the actual repo tree.
    fp = replay_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 64
    assert fp == replay_fingerprint()  # stable/reproducible


def test_replay_fingerprint_changes_when_a_live_gap_module_changes(tmp_path, monkeypatch):
    # The two LIVE gaps in particular: mutating either's bytes must change the fingerprint. Swaps
    # in a mutable tmp copy of the real file's current bytes so the real repo source is never
    # touched by the test.
    for real_path in (
        gate_cache._REPO_ROOT / "cli" / "risk" / "governor.py",
        gate_cache._REPO_ROOT / "cli" / "engine" / "journal.py",
    ):
        stand_in = tmp_path / real_path.name
        stand_in.write_bytes(real_path.read_bytes())
        patched = tuple(stand_in if p == real_path else p for p in gate_cache._replay_code_paths())
        monkeypatch.setattr(gate_cache, "_replay_code_paths", lambda patched=patched: patched)

        fp_before = replay_fingerprint()
        stand_in.write_bytes(stand_in.read_bytes() + b"\n# mutated\n")
        fp_after = replay_fingerprint()
        assert fp_after != fp_before, f"{real_path} is not covered by the fingerprint"


def test_replay_fingerprint_changes_when_an_original_module_changes(tmp_path, monkeypatch):
    # Findings 1-4: these four were in the hand-enumerated list from before the T0075 audit, but no
    # test asserted the fingerprint actually responds to their bytes -- they were droppable from
    # the tuple without failing anything. Same tmp-copy pattern as
    # test_replay_fingerprint_changes_when_a_live_gap_module_changes above (never mutate real repo
    # source).
    for real_path in (
        gate_cache._REPO_ROOT / "cli" / "portfolio" / "crossfreq_system.py",
        gate_cache._REPO_ROOT / "cli" / "portfolio" / "crossfreq.py",
        gate_cache._REPO_ROOT / "cli" / "risk" / "limits.py",
        gate_cache._REPO_ROOT / "cli" / "engine" / "concordance.py",
    ):
        stand_in = tmp_path / real_path.name
        stand_in.write_bytes(real_path.read_bytes())
        patched = tuple(stand_in if p == real_path else p for p in gate_cache._replay_code_paths())
        monkeypatch.setattr(gate_cache, "_replay_code_paths", lambda patched=patched: patched)

        fp_before = replay_fingerprint()
        stand_in.write_bytes(stand_in.read_bytes() + b"\n# mutated\n")
        fp_after = replay_fingerprint()
        assert fp_after != fp_before, f"{real_path} is not covered by the fingerprint"


def test_replay_fingerprint_changes_when_a_verdict_path_module_changes(tmp_path, monkeypatch):
    # Spec 00064 D9: the two files D3's wording always claimed but never hashed. command.py holds
    # `_snapshot_reader` -- the closure every replay reads price data through -- and `_replay_one`,
    # the classifier for exceptions raised by replay_cycle -- NOT the only verdict classifier in
    # the file: command.py:240 maps an unparseable cycle-*.json straight to validation_failed
    # without entering _replay_one, which is precisely what the D4 keystone test pins;
    # dataset.py holds `read_parquet`, feeding both that
    # reader and the snapshot content hash. Before D9 a "close" -> "open" edit in _snapshot_reader
    # changed every replay's verdict while leaving the fingerprint byte-identical. Same tmp-copy
    # pattern as the two tests above (never mutate real repo source).
    for real_path in (
        gate_cache._REPO_ROOT / "cli" / "engine" / "command.py",
        gate_cache._REPO_ROOT / "cli" / "ohlc" / "dataset.py",
    ):
        stand_in = tmp_path / real_path.name
        stand_in.write_bytes(real_path.read_bytes())
        patched = tuple(stand_in if p == real_path else p for p in gate_cache._replay_code_paths())
        monkeypatch.setattr(gate_cache, "_replay_code_paths", lambda patched=patched: patched)

        fp_before = replay_fingerprint()
        stand_in.write_bytes(stand_in.read_bytes() + b"\n# mutated\n")
        fp_after = replay_fingerprint()
        assert fp_after != fp_before, f"{real_path} is not covered by the fingerprint"


def test_replay_fingerprint_covers_the_replay_path():
    # D3: "fast" and "verified" select different builders (build_crossfreq_system_fast vs
    # build_crossfreq_system); a fast->verified switch must not serve the other route's cached
    # verdicts. Must fail if path is not folded into the digest.
    assert replay_fingerprint(path="fast") != replay_fingerprint(path="verified")
    # Defaulting to "fast" preserves every existing no-path call site's fingerprint.
    assert replay_fingerprint() == replay_fingerprint(path="fast")


def test_replay_fingerprint_covers_the_environment(monkeypatch):
    # T0074: a uv.lock bump touching numpy/Python numeric behaviour must invalidate the cache even
    # though the journal and the replay code are byte-for-byte unchanged -- otherwise a stale cache
    # silently serves a pre-bump verdict as gate evidence.
    fp_before = replay_fingerprint()
    assert replay_fingerprint() == fp_before  # stable when nothing changes

    monkeypatch.setattr(gate_cache, "version", lambda _pkg: "99.99.99")
    fp_numpy_changed = replay_fingerprint()
    assert fp_numpy_changed != fp_before

    monkeypatch.undo()
    monkeypatch.setattr(gate_cache.sys, "version_info", (3, 99, 0, "final", 0))
    fp_python_changed = replay_fingerprint()
    assert fp_python_changed != fp_before


def test_replay_fingerprint_survives_missing_distribution(monkeypatch):
    # importlib.metadata.version raises PackageNotFoundError for an odd/uninstalled distribution --
    # per D5's fail-open philosophy this must degrade to a sentinel string, never crash the
    # fingerprint (the caller's OSError guard does not cover this exception type).
    def _boom(_pkg):
        raise gate_cache.PackageNotFoundError("numpy")

    monkeypatch.setattr(gate_cache, "version", _boom)
    fp = replay_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 64


# --- the import closure (spec 00065) -------------------------------------------------------------


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_replay_roots_is_pinned_as_the_full_ordered_tuple():
    # Spec 00065 D1, same whole-tuple discipline as 00064 D1. Coverage is now DERIVED, so the roots
    # are the only hand-maintained input left -- and therefore the only thing that can silently
    # drift. Exact tuple equality catches dropping a root, reordering, or a fourth going unpinned.
    #
    # This pin is doing real work, and it is measured, not assumed: TWO of the three roots are
    # currently REDUNDANT. Dropping concordance.py or dataset.py leaves the closure at all 54
    # modules (both are reachable from command.py), so no coverage test can see them go. Only
    # command.py is load-bearing today -- dropping it loses 8 modules. That redundancy is a fact
    # about today's import graph, not a reason to trim the tuple: each root is an independent
    # replay entry point, and an edit that stops command.py importing concordance would silently
    # drop the whole replay core out of coverage if concordance were not also a root.
    assert gate_cache._REPLAY_ROOTS == (
        gate_cache._REPO_ROOT / "cli" / "engine" / "concordance.py",
        gate_cache._REPO_ROOT / "cli" / "engine" / "command.py",
        gate_cache._REPO_ROOT / "cli" / "ohlc" / "dataset.py",
    )


def test_replay_code_paths_contains_every_previously_enumerated_module():
    # Test-list 3. The twelve paths _REPLAY_CODE_PATHS enumerated by hand before 00065 must all
    # still be covered -- the closure REPLACES that list, it must not shrink it. A walk that
    # collapsed (e.g. an edge-resolution bug returning nothing) fails here rather than silently
    # under-invalidating the cache.
    covered = set(gate_cache._replay_code_paths())
    for rel in (
        ("cli", "portfolio", "crossfreq_system.py"),
        ("cli", "portfolio", "crossfreq.py"),
        ("cli", "risk", "limits.py"),
        ("cli", "risk", "governor.py"),
        ("cli", "engine", "concordance.py"),
        ("cli", "engine", "journal.py"),
        ("cli", "alpha", "a1.py"),
        ("cli", "alpha", "a2.py"),
        ("cli", "portfolio", "builder.py"),
        ("cli", "benchmark", "strategies.py"),
        ("cli", "engine", "command.py"),
        ("cli", "ohlc", "dataset.py"),
    ):
        assert gate_cache._REPO_ROOT.joinpath(*rel) in covered, f"{'/'.join(rel)} dropped out of the closure"


def test_replay_code_paths_contains_the_re_export_layers():
    # Test-list 3 / D5+D10 -- specific modules hand-enumeration MISSED. NOT an exhaustive pin on
    # the re-export layers: that job belongs to
    # test_closure_covers_every_module_the_replay_roots_actually_execute, which enumerates nothing.
    # This list is regression-anchoring for the two SEPARATE ways a package __init__ enters the
    # closure, which fail independently:
    #   - D5 (the first four): `from cli.pkg import X` resolving to the package __init__ as well as
    #     to cli/pkg/X.py. cli/engine/concordance.py:24 binds the fast builder THROUGH
    #     cli/portfolio/__init__.py; rebinding it there changed every verdict while leaving the
    #     pre-00065 fingerprint byte-identical.
    #   - D10 (the last two): ANCESTOR packages, which execute on import of any leaf beneath them
    #     and which the first cut of the walk omitted entirely -- exploitable the same way, at a
    #     byte-identical fingerprint, with the whole suite green.
    # Both were added after a pin that named only the modules someone had already thought of.
    covered = set(gate_cache._replay_code_paths())
    for rel in (
        ("cli", "portfolio", "__init__.py"),
        ("cli", "risk", "__init__.py"),
        ("cli", "alpha", "__init__.py"),
        ("cli", "engine", "errors.py"),
        # D10 ancestors -- on the same replay import path as the four above, and absent from both
        # the closure and this test until the ancestor gap was found at review.
        ("cli", "engine", "__init__.py"),
        ("cli", "ohlc", "__init__.py"),
    ):
        assert gate_cache._REPO_ROOT.joinpath(*rel) in covered, f"{'/'.join(rel)} is not covered"


def test_replay_code_paths_is_sorted_and_cli_only():
    # D4: sorted order is load-bearing. An unstable digest rebuilds the cache EVERY run -- which
    # looks exactly like a working cache while doing no work, so it is pinned, never assumed.
    # D3: third-party stays out (numpy's version is digested separately, T0074), so every covered
    # path lives under cli/.
    paths = gate_cache._replay_code_paths()
    assert list(paths) == sorted(paths)
    assert len(set(paths)) == len(paths), "the closure must not digest the same file twice"
    for path in paths:
        assert path.is_relative_to(gate_cache._REPO_ROOT / "cli"), f"{path} is outside cli/"


def test_replay_code_paths_excludes_non_cli_imports(tmp_path, monkeypatch):
    # Test-list 9 / D3. A synthetic tree whose root imports third-party and stdlib modules: the
    # closure is exactly the cli modules, never the imported outsiders.
    #
    # `json.py` and `numpy/__init__.py` are planted AT THE TREE ROOT deliberately, so that the
    # `parts[0] != "cli"` guard is the only thing keeping them out. Without them the test is
    # decorative: `import json` would resolve to a path that does not exist and drop out anyway, so
    # deleting the guard would not fail anything. With them, deleting the guard fails this test.
    _write(tmp_path / "json.py", "# a stdlib name that also exists in-tree\n")
    _write(tmp_path / "numpy" / "__init__.py", "# a third-party name that also exists in-tree\n")
    _write(tmp_path / "cli" / "engine" / "root.py", "import json\nimport numpy\nfrom cli.pkg import helper\n")
    _write(tmp_path / "cli" / "pkg" / "__init__.py", "from cli.pkg.helper import thing\n")
    _write(tmp_path / "cli" / "pkg" / "helper.py", "thing = 1\n")
    monkeypatch.setattr(gate_cache, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate_cache, "_REPLAY_ROOTS", (tmp_path / "cli" / "engine" / "root.py",))

    assert gate_cache._replay_code_paths() == (
        tmp_path / "cli" / "engine" / "root.py",
        tmp_path / "cli" / "pkg" / "__init__.py",
        tmp_path / "cli" / "pkg" / "helper.py",
    )


def test_unparseable_module_is_still_digested(tmp_path, monkeypatch):
    # Test-list 7 / D6 -- the direction that matters. A module that fails to parse loses only its
    # OUT-EDGES; its bytes are digested regardless. Swallowing a SyntaxError into "no imports" is
    # survivable, swallowing it into "not covered" is exactly the under-invalidation 00065 closes.
    broken = tmp_path / "cli" / "broken.py"
    _write(tmp_path / "cli" / "engine" / "root.py", "from cli.broken import thing\n")
    _write(broken, "def (((  # not valid Python\n")
    monkeypatch.setattr(gate_cache, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate_cache, "_REPLAY_ROOTS", (tmp_path / "cli" / "engine" / "root.py",))

    assert broken in gate_cache._replay_code_paths()

    fp_before = replay_fingerprint()
    broken.write_text("def ))) still not valid Python\n")
    assert replay_fingerprint() != fp_before


def test_replay_code_paths_does_not_collapse(tmp_path):
    # A floor, not a pin of the exact set: the closure measures 61 modules (54 before 00065 D10's
    # ancestor fix), and every contains-test above would still pass if the walk collapsed to just
    # the ~16 modules they name. This catches that collapse. It is deliberately loose -- adding or
    # removing an import in cli/ legitimately moves the count, and this must not become a tripwire
    # on ordinary edits; the exact-coverage guarantee is
    # test_closure_covers_every_module_the_replay_roots_actually_execute's job, not this one's.
    assert len(gate_cache._replay_code_paths()) >= 40


# --- the guarantee: the exploit, determinism, D5 resolution, never-raises (spec 00065 D7/D8) -----


def _clone_repo_cli(tmp_path, monkeypatch):
    """A writable copy of this repo's real `cli/` tree, with `_REPO_ROOT`/`_REPLAY_ROOTS` pointed at
    it. Tests that need to EDIT covered source work here: never mutate the real repo source in a
    test -- a failure mid-test would leave the working tree dirty, and a covered-module edit that
    escaped would change every other test's fingerprint."""
    real_root, real_roots = gate_cache._REPO_ROOT, gate_cache._REPLAY_ROOTS
    tree = tmp_path / "repo"
    shutil.copytree(real_root / "cli", tree / "cli", ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(gate_cache, "_REPO_ROOT", tree)
    monkeypatch.setattr(gate_cache, "_REPLAY_ROOTS", tuple(tree / root.relative_to(real_root) for root in real_roots))
    return tree


def test_rebinding_the_fast_builder_in_the_portfolio_init_moves_the_fingerprint(tmp_path, monkeypatch):
    # THE GUARANTEE (spec 00065 D7-ii, test-list 2). The closure walker is only today's
    # IMPLEMENTATION of it; this test is the thing that must hold however coverage is computed. If
    # it ever stops distinguishing, the cache can serve verdicts produced by different code.
    #
    # The exploit: cli/engine/concordance.py does `from cli.portfolio import
    # build_crossfreq_system_fast`, so every replay binds the fast builder THROUGH
    # cli/portfolio/__init__.py. Rebinding the name there to the VERIFIED daily-oracle builder makes
    # every replay compute a different verdict, without touching either builder's own module.
    #
    # Measured against the pre-00065 twelve-path enumeration, this exact edit was BYTE-IDENTICAL:
    # sha256 484ae6ea48d61739d95fdba9a23c48560082ddeb38a71b706177ab031f9fdb84 both before and after
    # it, with all 31 tests in this file green -- cli/portfolio/__init__.py was simply not one of
    # the twelve hashed paths.
    tree = _clone_repo_cli(tmp_path, monkeypatch)
    init = tree / "cli" / "portfolio" / "__init__.py"

    # Preconditions -- these keep the test about the real exploit rather than about "editing some
    # file in the closure moves a hash". If the code moves so that these no longer hold, this test
    # must be re-aimed at wherever the fast builder is bound, not quietly relaxed.
    concordance_src = (tree / "cli" / "engine" / "concordance.py").read_text()
    assert "from cli.portfolio import" in concordance_src and "build_crossfreq_system_fast" in concordance_src, (
        "concordance no longer binds the fast builder through cli.portfolio -- re-aim this test"
    )
    init_src = init.read_text()
    assert "build_crossfreq_system_fast" in init_src and "build_crossfreq_system" in init_src, (
        "cli/portfolio/__init__.py no longer re-exports the two builders -- re-aim this test"
    )
    assert init in set(gate_cache._replay_code_paths()), "the re-export layer is not covered"

    fp_before = replay_fingerprint()
    init.write_text(init_src + "\nbuild_crossfreq_system_fast = build_crossfreq_system\n")
    assert "\nbuild_crossfreq_system_fast = build_crossfreq_system\n" in init.read_text()  # the edit landed

    assert replay_fingerprint() != fp_before, (
        "rebinding build_crossfreq_system_fast in cli/portfolio/__init__.py left the fingerprint "
        "unchanged -- the cache would serve verdicts from a different builder"
    )


def test_replay_fingerprint_is_identical_in_a_fresh_process_from_a_different_cwd(tmp_path):
    # Test-list 4/5, D4 + D7-iii. Determinism across PROCESSES and CWDs, not just across calls.
    # Both halves are load-bearing and neither is implied by the in-process sorted-order pin above:
    #   - fresh process: set iteration order depends on PYTHONHASHSEED, which is randomized per
    #     process, so an unsorted walk agrees with itself all day inside one interpreter and
    #     disagrees with the next one.
    #   - different cwd: deriving the repo root from cwd instead of __file__ would digest a
    #     different (or empty) file set depending on where the CLI was invoked from.
    # Losing either silently disables the cache: every run's fingerprint mismatches the stored one,
    # so every run rebuilds -- which looks exactly like a working cache while doing no work.
    in_process = replay_fingerprint()
    assert replay_fingerprint() == in_process  # stable across repeated calls

    result = subprocess.run(
        [sys.executable, "-c", "from cli.engine.gate_cache import replay_fingerprint; print(replay_fingerprint())"],
        cwd=tmp_path,  # deliberately NOT the repo root
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == in_process, "the fingerprint is not reproducible across processes/cwds"


def test_from_cli_pkg_import_x_resolves_to_both_the_package_and_the_submodule(tmp_path, monkeypatch):
    # Test-list 6 / D5, on a synthetic tree carrying BOTH shapes a `from cli.pkg import X` can take:
    #   - `submodule` -- a real cli/pkg/submodule.py; resolving only the package would miss it.
    #   - `reexported_name` -- a name bound in cli/pkg/__init__.py with no file of its own; this is
    #     the build_crossfreq_system_fast shape, and resolving only `cli/pkg/X.py` would miss the
    #     __init__ that binds it. That miss is the entire pre-00065 hole.
    # Static analysis cannot tell the two apart, so D5 resolves both and accepts the over-inclusion.
    _write(tmp_path / "cli" / "engine" / "root.py", "from cli.pkg import submodule, reexported_name\n")
    _write(tmp_path / "cli" / "pkg" / "__init__.py", "reexported_name = 1\n")
    _write(tmp_path / "cli" / "pkg" / "submodule.py", "thing = 2\n")
    monkeypatch.setattr(gate_cache, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate_cache, "_REPLAY_ROOTS", (tmp_path / "cli" / "engine" / "root.py",))

    assert gate_cache._replay_code_paths() == (
        tmp_path / "cli" / "engine" / "root.py",
        tmp_path / "cli" / "pkg" / "__init__.py",
        tmp_path / "cli" / "pkg" / "submodule.py",
    )


# D8, half one: the EXCEPTION TYPE is the contract. `_evaluate_journal` degrades to the no-cache
# path by catching OSError specifically (command.py:224), so a broken module must surface as an
# OSError and nothing else -- any other type propagates through that guard and aborts a gate-export
# run over what is only a cache optimization. The walk itself never raises; it is the digest's
# read_bytes that fails, BY DESIGN, so a module that cannot be read can never be silently skipped.
# (Half two -- that the caller actually degrades -- is pinned end-to-end against these same two
# breakages in tests/test_engine_gate_export_cache.py.)


def test_replay_fingerprint_raises_oserror_when_a_root_is_missing(tmp_path, monkeypatch):
    root = tmp_path / "cli" / "engine" / "root.py"
    _write(tmp_path / "cli" / "engine" / "other.py", "# the tree exists; the root does not\n")
    monkeypatch.setattr(gate_cache, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate_cache, "_REPLAY_ROOTS", (root,))

    assert not root.exists()
    assert root in gate_cache._replay_code_paths()  # a missing root stays IN the covered set...
    with pytest.raises(OSError):  # ...so it fails loudly at digest time instead of vanishing
        replay_fingerprint()


def test_replay_fingerprint_raises_oserror_when_a_covered_module_is_unreadable(tmp_path, monkeypatch):
    root = tmp_path / "cli" / "engine" / "root.py"
    helper = tmp_path / "cli" / "pkg" / "helper.py"
    _write(root, "from cli.pkg import helper\n")
    _write(tmp_path / "cli" / "pkg" / "__init__.py", "")
    _write(helper, "thing = 1\n")
    helper.chmod(0o000)
    monkeypatch.setattr(gate_cache, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate_cache, "_REPLAY_ROOTS", (root,))

    try:
        assert helper in gate_cache._replay_code_paths()  # covered, and unreadable
        with pytest.raises(OSError):
            replay_fingerprint()
    finally:
        helper.chmod(0o644)  # restore so tmp_path cleanup never depends on the test's outcome


# --- cache round-trip (D4/D8 of the spec test list) ----------------------------------------------


def test_cache_round_trip_preserves_outcome_exactly(tmp_path):
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    passing = _outcome()
    mismatch = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4), mismatch=True, compare_passed=False)
    validation_failed = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=8), validation_failed=True, compare_passed=False)

    cache = GateCache(
        replay_fp=replay_fp,
        entries={
            passing.cycle_ts: ("evidence-fp-1", passing, CYCLE_TS),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch, CYCLE_TS),
            validation_failed.cycle_ts: ("evidence-fp-3", validation_failed, CYCLE_TS),
        },
    )
    save_cache(path, cache)
    loaded = load_cache(path, replay_fp)

    assert loaded.replay_fp == replay_fp
    assert loaded.entries.keys() == cache.entries.keys()
    for cycle_ts, (evidence_fp, outcome, verified_at) in cache.entries.items():
        loaded_evidence_fp, loaded_outcome, loaded_verified_at = loaded.entries[cycle_ts]
        assert loaded_evidence_fp == evidence_fp
        assert loaded_outcome == outcome
        assert loaded_verified_at == verified_at
        # A cached failure must never come back as a pass.
        assert loaded_outcome.mismatch == outcome.mismatch
        assert loaded_outcome.validation_failed == outcome.validation_failed
        assert loaded_outcome.compare_passed == outcome.compare_passed


def test_cache_round_trip_preserves_verified_at(tmp_path):
    # D5/D6 (schema v2): verified_at round-trips alongside mismatch=True and validation_failed=True
    # entries, not just a passing one.
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    passing = _outcome()
    mismatch = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4), mismatch=True, compare_passed=False)
    validation_failed = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=8), validation_failed=True, compare_passed=False)

    verified_at_passing = CYCLE_TS + timedelta(minutes=1)
    verified_at_mismatch = CYCLE_TS + timedelta(hours=4, minutes=1)
    verified_at_validation_failed = CYCLE_TS + timedelta(hours=8, minutes=1)

    cache = GateCache(
        replay_fp=replay_fp,
        entries={
            passing.cycle_ts: ("evidence-fp-1", passing, verified_at_passing),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch, verified_at_mismatch),
            validation_failed.cycle_ts: ("evidence-fp-3", validation_failed, verified_at_validation_failed),
        },
    )
    save_cache(path, cache)
    loaded = load_cache(path, replay_fp)

    assert loaded.entries[passing.cycle_ts][2] == verified_at_passing
    assert loaded.entries[mismatch.cycle_ts][2] == verified_at_mismatch
    assert loaded.entries[validation_failed.cycle_ts][2] == verified_at_validation_failed


# --- load_cache: fail open, never raise (D5) ------------------------------------------------------


def test_load_cache_degrades_never_raises(tmp_path):
    replay_fp = "fixed-replay-fp"

    # None path -- absent, not rejected.
    empty = load_cache(None, replay_fp)
    assert empty.entries == {}
    assert empty.replay_fp == replay_fp
    assert empty.rejected is False

    # Absent file -- absent, not rejected (no file ever existed to discard).
    absent_path = tmp_path / "does-not-exist.json"
    absent = load_cache(absent_path, replay_fp)
    assert absent.entries == {}
    assert absent.rejected is False

    # Truncated/unparseable JSON -- a file existed and was discarded.
    truncated_path = tmp_path / "truncated.json"
    truncated_path.write_text('{"schema_version": 1, "replay_fp": "x", "entries": [')
    truncated = load_cache(truncated_path, replay_fp)
    assert truncated.entries == {}
    assert truncated.rejected is True

    # Wrong schema_version -- discarded.
    wrong_schema_path = tmp_path / "wrong-schema.json"
    wrong_schema_path.write_text(json.dumps({"schema_version": CACHE_SCHEMA_VERSION + 1, "replay_fp": replay_fp, "entries": []}))
    wrong_schema = load_cache(wrong_schema_path, replay_fp)
    assert wrong_schema.entries == {}
    assert wrong_schema.rejected is True

    # replay_fp mismatch -- discarded.
    good_path = tmp_path / "good.json"
    outcome = _outcome()
    cache = GateCache(replay_fp=replay_fp, entries={outcome.cycle_ts: ("evidence-fp", outcome, CYCLE_TS)})
    save_cache(good_path, cache)
    mismatched = load_cache(good_path, "a-different-replay-fp")
    assert mismatched.entries == {}
    assert mismatched.replay_fp == "a-different-replay-fp"
    assert mismatched.rejected is True

    # Unreadable path (a directory, not a file, raises IsADirectoryError on read) -- discarded.
    unreadable_path = tmp_path / "a-directory"
    unreadable_path.mkdir()
    unreadable = load_cache(unreadable_path, replay_fp)
    assert unreadable.entries == {}
    assert unreadable.rejected is True


def test_v1_cache_is_rejected_wholesale(tmp_path):
    # D6 (finding 14/G14): CACHE_SCHEMA_VERSION 1 -> 2 (verified_at changes the entry shape). A v1
    # file on disk must be rejected wholesale -- no partial read of its (now-shaped-differently)
    # entries -- forcing one full replay and rewrite, per the existing fail-open contract (never a
    # migration). The entry below is deliberately v2-SHAPED (verified_at present): a REAL v1 file
    # would lack it and die on a KeyError inside the entry loop regardless of whether the explicit
    # schema_version check fires at all -- which is exactly how this test used to pass for the
    # wrong reason (the audit's `!=` -> `>` mutation slips a v1-declaring file straight past a
    # KeyError-shaped payload undetected: `1 > 2` is False, so the check doesn't fire, but the
    # entry loop then dies on the missing verified_at anyway, and the test still sees rejected).
    # v2-shaping the row isolates the schema_version check as the ONLY thing that can reject this
    # file, so the test now fails for the right reason.
    replay_fp = "fixed-replay-fp"
    path = tmp_path / "gate-cache.json"
    v1_payload = {
        "schema_version": 1,
        "replay_fp": replay_fp,
        "entries": [
            {
                "evidence_fp": "evidence-fp",
                "verified_at": CYCLE_TS.isoformat(),
                "cycle_ts": CYCLE_TS.isoformat(),
                "completed_at": (CYCLE_TS + timedelta(minutes=5)).isoformat(),
                "compare_passed": True,
                "mismatch": False,
                "validation_failed": False,
            }
        ],
    }
    path.write_text(json.dumps(v1_payload))

    loaded = load_cache(path, replay_fp)

    assert loaded.entries == {}
    assert loaded.rejected is True


def test_higher_schema_version_is_also_rejected_wholesale(tmp_path):
    # The schema gate must reject ANY mismatched version, not just an older one -- a v2-shaped file
    # (verified_at present, so nothing else could reject it) declaring a version NEWER than
    # CACHE_SCHEMA_VERSION exercises the other direction, which a `!=` -> `<` mutation (permissive
    # toward newer versions) would silently accept while still passing the v1 test above.
    # NOT a coverage gap being filled: test_load_cache_degrades_never_raises already carries a
    # CACHE_SCHEMA_VERSION + 1 case and already kills `<`. This is a dedicated, named pin for the
    # guarantee, where that one is a single bullet inside a six-case omnibus named for a different
    # guarantee -- and it uses a POPULATED entries list where the omnibus uses [], so a mutant that
    # rejects the version but still serves rows cannot hide behind an empty file. Recorded so the
    # next reader does not mistake this for coverage that was previously missing.
    replay_fp = "fixed-replay-fp"
    path = tmp_path / "gate-cache.json"
    v_next_payload = {
        "schema_version": CACHE_SCHEMA_VERSION + 1,
        "replay_fp": replay_fp,
        "entries": [
            {
                "evidence_fp": "evidence-fp",
                "verified_at": CYCLE_TS.isoformat(),
                "cycle_ts": CYCLE_TS.isoformat(),
                "completed_at": (CYCLE_TS + timedelta(minutes=5)).isoformat(),
                "compare_passed": True,
                "mismatch": False,
                "validation_failed": False,
            }
        ],
    }
    path.write_text(json.dumps(v_next_payload))

    loaded = load_cache(path, replay_fp)

    assert loaded.entries == {}
    assert loaded.rejected is True


def test_load_cache_rejects_wholesale_on_one_malformed_row(tmp_path):
    # Finding 11/G8 (spec D5): every existing fail-open test corrupts the file BEFORE the entry
    # loop (truncated JSON, wrong schema, replay_fp mismatch, an unreadable path) -- this is the
    # ONE path where "discard the file" and "skip the bad row" diverge: a structurally valid,
    # correct-schema file with one good row and one malformed row (an unparseable cycle_ts). The
    # malformed row's `datetime.fromisoformat` call is not individually guarded, so it propagates
    # out of the entry loop into load_cache's own except clause and discards the WHOLE file -- the
    # good row must never be served alone.
    replay_fp = "fixed-replay-fp"
    path = tmp_path / "gate-cache.json"

    def _row(cycle_ts_str: str, evidence_fp: str) -> dict:
        return {
            "evidence_fp": evidence_fp,
            "verified_at": CYCLE_TS.isoformat(),
            "cycle_ts": cycle_ts_str,
            "completed_at": (CYCLE_TS + timedelta(minutes=5)).isoformat(),
            "compare_passed": True,
            "mismatch": False,
            "validation_failed": False,
        }

    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "replay_fp": replay_fp,
        "entries": [_row(CYCLE_TS.isoformat(), "evidence-fp-good"), _row("not-a-timestamp", "evidence-fp-bad")],
    }
    path.write_text(json.dumps(payload))

    loaded = load_cache(path, replay_fp)

    assert loaded.entries == {}, "one malformed row must invalidate the WHOLE file, not just be skipped"
    assert loaded.rejected is True


def test_load_cache_never_raises_on_wrong_top_level_type(tmp_path):
    # D5 (finding 15/G15): valid JSON that parses fine but is the wrong top-level type -- a list,
    # not a dict -- raises TypeError on `payload["schema_version"]`; caught by the same except
    # tuple as every other fail-open path here, degrading to an empty, rejected cache rather than
    # propagating out of load_cache.
    replay_fp = "fixed-replay-fp"
    path = tmp_path / "wrong-type.json"
    path.write_text(json.dumps([1, 2, 3]))

    loaded = load_cache(path, replay_fp)

    assert loaded.entries == {}
    assert loaded.rejected is True


# --- save_cache: atomic write (D6) ----------------------------------------------------------------


def test_save_cache_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    # A normal write lands via a .tmp sibling that is gone afterward.
    outcome = _outcome()
    cache = GateCache(replay_fp=replay_fp, entries={outcome.cycle_ts: ("evidence-fp", outcome, CYCLE_TS)})
    save_cache(path, cache)
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    original_content = path.read_text()

    # None path is a no-op -- never raises, never creates a file.
    save_cache(None, cache)

    # A simulated mid-write failure (os.replace raising) must not corrupt or touch the pre-existing
    # cache, and save_cache itself must not raise (D6/D5: never fail trusting, never abort the run).
    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash between tmp-write and replace")

    monkeypatch.setattr(gate_cache.os, "replace", _boom)
    other_outcome = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4))
    other_cache = GateCache(replay_fp=replay_fp, entries={other_outcome.cycle_ts: ("evidence-fp-2", other_outcome, CYCLE_TS)})
    save_cache(path, other_cache)  # must not raise

    assert path.read_text() == original_content  # the prior cache survives untouched


def test_save_cache_never_raises_on_mixed_key_types(tmp_path):
    # D5/D6 (finding 16/G16): save_cache's `sorted(cache.entries.items())` compares keys; a cache
    # holding both a datetime and a str key raises TypeError from the comparison itself ("'<' not
    # supported between instances of 'str' and 'datetime.datetime'") -- the `TypeError` arm of
    # `except (OSError, TypeError)` is reachable and load-bearing, not dead code. Must degrade
    # silently (log + continue), never abort a run that already succeeded; nothing is partially
    # written since the TypeError fires while building the payload, before any write.
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"
    outcome = _outcome()
    mixed_entries = {
        CYCLE_TS: ("evidence-fp-1", outcome, CYCLE_TS),
        "not-a-datetime-key": ("evidence-fp-2", outcome, CYCLE_TS),
    }
    cache = GateCache(replay_fp=replay_fp, entries=mixed_entries)

    save_cache(path, cache)  # must not raise

    assert not path.exists()  # nothing partially written


# --- slice_of / due_for_reverification (D2/D3) ---------------------------------------------------


def test_slice_of_is_deterministic_and_process_stable():
    # Hardcoded (cycle_ts -> slice) pairs, computed once from the sha256(isoformat) % 24 derivation
    # and pinned here: a future change to the derivation must FAIL this test rather than silently
    # redistributing every cycle's slice, which would look like nothing happened while quietly
    # resetting the whole rotation schedule.
    pinned = {
        datetime(2026, 7, 10, 8, 0): 13,
        datetime(2020, 1, 1, 0, 0): 13,
        datetime(2026, 12, 31, 23, 0): 23,
    }
    for cycle_ts, expected_slice in pinned.items():
        assert slice_of(cycle_ts) == expected_slice
        # Same cycle_ts -> same slice across repeated calls (process-stable, not e.g. seeded by
        # builtin hash() randomization).
        assert slice_of(cycle_ts) == slice_of(cycle_ts)


def test_slice_of_distributes_without_gross_skew():
    base = datetime(2024, 1, 1, 0, 0)
    n = 480
    slices = [slice_of(base + timedelta(hours=i)) for i in range(n)]

    counts = Counter(slices)
    assert set(counts) == set(range(24))  # every slice covered

    mean = n / 24
    for slice_index, count in counts.items():
        assert count <= 3 * mean, f"slice {slice_index} holds {count}, more than 3x the mean {mean}"


def test_due_for_reverification_matches_the_run_hour():
    cycle_ts = datetime(2026, 7, 10, 8, 0)
    expected_slice = slice_of(cycle_ts)
    for hour in range(24):
        now = datetime(2026, 7, 15, hour, 0)
        assert due_for_reverification(cycle_ts, now) == (expected_slice == hour % 24)


def test_rotation_slices_guard_rejects_values_above_24():
    """`slice_of` returns `[0, _ROTATION_SLICES)` but `due_for_reverification` selects the current
    slice via `now.hour % _ROTATION_SLICES`, which can only ever produce `[0, 23]` -- any
    `_ROTATION_SLICES > 24` would leave the high slices permanently unreachable, silently never
    re-verified. The module-level guard immediately below the constant must actually fire for such
    a value, not just exist as inert prose next to it -- extracts the real constant-plus-guard
    lines from the module source (comment lines and blank lines around it drift-tolerant) and execs
    them standalone with the constant patched to 25."""
    lines = inspect.getsource(gate_cache).splitlines()
    start = lines.index("_ROTATION_SLICES = 24")
    end = start + 1
    while end < len(lines) and (lines[end].startswith("#") or lines[end] == ""):
        end += 1
    assert lines[end].startswith("assert"), (
        "expected a module-level guard (an `assert`) immediately below `_ROTATION_SLICES = 24` "
        "(only comment/blank lines in between) -- none found"
    )
    snippet = "\n".join(lines[start : end + 1])
    mutated = snippet.replace("_ROTATION_SLICES = 24", "_ROTATION_SLICES = 25", 1)
    with pytest.raises(AssertionError):
        exec(compile(mutated, "<gate_cache _ROTATION_SLICES guard, patched to 25>", "exec"), {})


# --- oldest_verification_age (D5) -----------------------------------------------------------------


def test_oldest_verification_age():
    now = CYCLE_TS + timedelta(days=2)

    assert oldest_verification_age(GateCache(replay_fp="fp", entries={}), now) is None

    passing = _outcome()
    mismatch = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4), mismatch=True, compare_passed=False)
    oldest_verified_at = CYCLE_TS - timedelta(hours=10)  # the least-recent of the two
    newest_verified_at = CYCLE_TS + timedelta(hours=1)

    cache = GateCache(
        replay_fp="fp",
        entries={
            passing.cycle_ts: ("evidence-fp-1", passing, newest_verified_at),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch, oldest_verified_at),
        },
    )
    age = oldest_verification_age(cache, now)
    assert age == (now - oldest_verified_at).total_seconds()


def test_closure_covers_every_module_the_replay_roots_actually_execute():
    """THE STRUCTURAL PIN (spec 00065 D10) -- the only test here that cannot go stale, because it
    enumerates nothing. Every other coverage test names the modules it expects, so it can only ever
    catch a gap someone already thought of; this one asks Python what actually executes and demands
    the closure be a superset.

    It exists because the first cut of the closure walk failed it. `_resolve_module` mapped a dotted
    name to the leaf file only, but importing `cli.engine.command` EXECUTES `cli/__init__.py` and
    `cli/engine/__init__.py` first. SEVEN modules ran on every replay while unhashed -- the four
    ancestor `__init__.py` files, plus cli/ohlc/{ingest,qa,reconstruct}.py, which became traversable
    only once cli/ohlc/__init__.py entered the closure -- and it was
    exploitable exactly like the hand-enumerated list before it: rebinding
    `build_crossfreq_system_fast` in `cli/engine/__init__.py` made every replay run the VERIFIED
    daily-oracle builder -- a different verdict -- at a byte-identical fingerprint, with all 64
    tests in this file and its sibling passing. That is the THIRD round of the same
    under-invalidation defect (hand list -> D9's two files -> ancestor packages), and enumerating
    pins missed all three.

    Sub-process, not this one: pytest has already imported far more of `cli` than a replay does, so
    an in-process `sys.modules` read would silently pass by over-counting.

    Over-inclusion in the other direction is fine and deliberately NOT asserted (D3/D5): covering a
    module a given run happens not to execute costs one rebuild; missing one corrupts gate
    evidence."""
    probe = (
        "import sys, json, pathlib\n"
        "import cli.engine.concordance, cli.engine.command, cli.ohlc.dataset\n"
        "print(json.dumps(sorted({str(pathlib.Path(m.__file__).resolve())\n"
        "    for n, m in sys.modules.items()\n"
        "    if n.split('.')[0] == 'cli' and getattr(m, '__file__', None)})))"
    )
    repo_root = gate_cache._REPO_ROOT
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=repo_root, check=True)
    executed = {pathlib.Path(p) for p in json.loads(result.stdout)}
    covered = {p.resolve() for p in gate_cache._replay_code_paths()}

    missing = sorted(str(p.relative_to(repo_root)) for p in executed - covered)
    assert not missing, (
        "these modules execute on every replay but are NOT digested into replay_fingerprint, so "
        f"editing one serves a stale cached verdict at an unchanged fingerprint: {missing}"
    )
