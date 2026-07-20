# gate-export incremental scoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Bound `gate-export`'s per-run cost by the journal's new tail rather than its whole history (spec `00060`, [[T0069]]'s structural fix).

**Architecture:** A new pure module `cli/engine/gate_cache.py` (fingerprints, load/save, `CycleOutcome` round-trip) plus an opt-in `cache` parameter threaded through `_evaluate_journal` and a `--cache` option on `gate-export`. No change to `evaluate_gate`, the journal format, or `report`.

**Tech Stack:** Python 3.14, stdlib `hashlib`/`json`/`os.replace`, pytest.

## Global Constraints

- **Opt-in (D1):** no `--cache` ⇒ today's behavior byte-for-byte, no file created. `report` is never cached.
- **Never write into the journal tree (D1).** The journal is an append-only archive.
- **Two fingerprints (D2/D3):** a per-cycle *evidence* fingerprint (all `SnapshotEntry.content_hash` in canonical order + `cycle_ts` + `completed_at` + `final_targets`), and one per-file *replay* fingerprint over the source bytes of `cli/portfolio/crossfreq_system.py`, `cli/portfolio/crossfreq.py`, `cli/risk/limits.py`, `cli/engine/concordance.py` plus the effective `CrossfreqSystemConfig`. A replay-fingerprint mismatch invalidates the **whole** cache. Deliberately over-sensitive — over-invalidation is safe, under-invalidation corrupts gate evidence.
- **A cache hit must equal a fresh replay, field for field (D4).**
- **Fail open (D5):** any cache problem ⇒ full replay + rewrite; never abort, never serve a partially-trusted entry.
- **Atomic write on success only (D6):** `<path>.tmp` + `os.replace`.
- **Cache only success-record replays (D7)** — not sidecars, not absent boundaries.

---

## Task 1: `cli/engine/gate_cache.py` — fingerprints, load/save, round-trip

**Files:** create `cli/engine/gate_cache.py`; test `tests/test_engine_gate_cache.py`.

**Interfaces:**
```python
CACHE_SCHEMA_VERSION = 1

def replay_fingerprint(config: CrossfreqSystemConfig = CrossfreqSystemConfig()) -> str:
    """sha256 over the source bytes of the modules that determine a replay's result, plus the
    effective config. Deliberately over-sensitive: a comment-only edit invalidates the cache."""

def evidence_fingerprint(record: CycleRecord) -> str:
    """sha256 over everything a replay verdict depends on from the journal side: every
    SnapshotEntry.content_hash in canonical (pair, grid) order, cycle_ts, completed_at, final_targets."""

@dataclass(frozen=True)
class GateCache:
    replay_fp: str
    entries: dict[datetime, tuple[str, CycleOutcome]]   # cycle_ts -> (evidence_fp, outcome)

def load_cache(path: Path | None, replay_fp: str) -> GateCache:
    """Read + validate. Returns an EMPTY cache (never raises) on: path None/absent, unreadable,
    unparseable, wrong schema_version, or a replay_fp mismatch (D3/D5)."""

def save_cache(path: Path | None, cache: GateCache) -> None:
    """Atomic <path>.tmp + os.replace. No-op when path is None. Never raises on write failure --
    log and continue (the cache is an optimization; the run already succeeded)."""
```
Serialize `CycleOutcome` explicitly (its fields + isoformat datetimes) — do not pickle.

- [ ] **Step 1: failing tests** in `tests/test_engine_gate_cache.py`:
  - `test_evidence_fingerprint_changes_with_each_input` — mutating any of content_hash / cycle_ts / completed_at / final_targets changes it; an identical record reproduces it.
  - `test_replay_fingerprint_covers_replay_code` — it changes when a covered module's bytes change (monkeypatch the file list / feed altered bytes) and is stable otherwise. **This is D3's pin — it must fail if the fingerprint is journal-only.**
  - `test_cache_round_trip_preserves_outcome_exactly` — including `mismatch=True` and `validation_failed=True` variants (D8 of the spec's test list: a cached failure must not become a pass).
  - `test_load_cache_degrades_never_raises` — None path, absent file, truncated JSON, wrong schema_version, replay_fp mismatch ⇒ empty cache, no exception.
  - `test_save_cache_is_atomic` — writes via a `.tmp` sibling then replaces; a pre-existing cache survives a simulated mid-write failure.
- [ ] **Steps 2–4:** run → fail → implement → pass.
- [ ] **Step 5:** `uv run pre-commit run -a`; commit `feat(cli): gate-export scoring cache primitives`.

---

## Task 2: wire it into `_evaluate_journal` + `gate-export`

**Files:** modify `cli/engine/command.py`; tests in `tests/test_engine_command.py` (or a new `tests/test_engine_gate_export_cache.py`).

- `_evaluate_journal(journal_root, *, cache_path: Path | None = None) -> (entries, counts, newest_ts, cache_stats)`.
  Load the cache once; for each success record compute `evidence_fingerprint`; on a match reuse the stored `CycleOutcome` (no `replay_cycle` call), else replay and record the new entry. Save once at the end. Sidecars unchanged (D7).
  `cache_stats` carries `replayed`, `from_cache`, `invalidated: bool`.
  **`report` must keep calling it with `cache_path=None`.**
- `gate-export` gains `--cache PATH` (default None) and emits the D8 metrics next to the existing gate metrics: cycles replayed, cycles served from cache, cache-invalidated flag. Help strings must stay free of internal-tracker tokens.

- [ ] **Step 1: failing tests**
  - **`test_warm_cache_equals_cold_cache`** — the D4 keystone: same journal, run cold then warm; assert the `CycleOutcome` lists are **equal** and `evaluate_gate(...)` statuses are equal.
  - `test_warm_cache_replays_only_the_new_cycle` — count `replay_cycle` calls via monkeypatch; appending one cycle ⇒ exactly one replay.
  - `test_tampered_record_misses_cache` — mutate a cached record's evidence; that cycle is replayed, the stale entry is not served.
  - `test_replay_fingerprint_change_invalidates_all` — inject a different replay fingerprint ⇒ every cycle replayed, `invalidated` true.
  - `test_no_cache_option_is_unchanged_behavior` — no `--cache` ⇒ same outcomes, no file created.
  - `test_gate_export_emits_cache_metrics` — replayed + from_cache sum to the success-record count.
- [ ] **Steps 2–4:** fail → implement → pass. Also run `tests/test_engine_command.py` and `tests/test_cli_help_hygiene.py`.
- [ ] **Step 5:** gate + commit `feat(cli): gate-export --cache incremental scoring`.

---

## Task 3 (orchestrator, not a subagent): real-journal verification + closeout

- [ ] On the ops mirror: cold run (no cache) → record gate status + wall time; cold-with-cache → warm run. Assert identical gate status, 0 replays warm, and record the measured speedup.
- [ ] Confirm `report` is unaffected (no cache file, same output).
- [ ] Final whole-branch review; fix wave if needed.
- [ ] Closeout: iter-110 entry in `docs/iterations-history-phase6.md`; [[T0069]] `## Done so far` updated (incremental scoring landed; the attended relocation remains); PR into `develop`; merge via `merge-pr` when green.

## Self-Review

- Spec coverage: D1→Tasks 1–2; D2/D3→Task 1; D4→Task 2 keystone; D5→Task 1; D6→Task 1; D7→Task 2; D8→Task 2. Spec test-list 1–10 map to Task 2 (1,2,3,4,6,9), Task 1 (5,7,8), Task 3 (10).
- Type consistency: `GateCache.entries` is keyed by `datetime` (aware UTC `cycle_ts`) throughout; `cache_stats` is a small frozen dataclass, not a bare tuple, so adding a field later doesn't break unpacking.
- Grounded: `_evaluate_journal` (command.py:139), `replay_cycle`/`CycleOutcome`/`evaluate_gate` (concordance.py), `_journal_artifacts`/`_snapshot_reader`, `CrossfreqSystemConfig` — all verified present.
