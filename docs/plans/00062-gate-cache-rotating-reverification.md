# gate-cache rotating re-verification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Restore, at bounded cost, the continuous parquet-byte verification that a `gate-export --cache` hit currently skips (spec `00062`, [[T0077]]).

**Architecture:** A deterministic slice function in `cli/engine/gate_cache.py`, a `verified_at` field on each cache entry (schema v2), one extra condition in `_evaluate_journal`'s cache-eligibility test, and three metric changes in the textfile writer. No change to `replay_cycle`, `evaluate_gate`, the journal format, or `report`.

**Tech Stack:** Python 3.14, stdlib `hashlib`/`datetime`, pytest.

## Global Constraints

- **This is gate evidence.** Correctness beats speed wherever they conflict. A cache hit must still equal a fresh replay field-for-field (spec `00060` D4, preserved).
- **Rotation is always on when the cache is active (D1)** — not a flag. A safety property that can be switched off will be.
- **The slice is a fixed property of the cycle (D2):** `slice_of(cycle_ts) = int(sha256(cycle_ts.isoformat().encode()).hexdigest(), 16) % _ROTATION_SLICES`, `_ROTATION_SLICES = 24`. Never the loop index or list position — the journal grows and artifact ordering can shift.
- **The current slice is `now.hour % _ROTATION_SLICES` (D3)** — stateless, no persisted cursor.
- **A forced re-verification failure is a gate failure, not a cache event (D4):** it yields the same `CycleOutcome(mismatch=True)` any replay would and flows into `JournalCounts`/`evaluate_gate` unchanged. Forced replays count as `replayed`, never `from_cache`.
- **`CACHE_SCHEMA_VERSION` 1 → 2 (D6).** v1 files are rejected wholesale by the existing check — fail-open, no migration code.
- **No `_total` suffix on per-run gauges (D7).**
- **Never write into the journal tree**; `report` still calls `_evaluate_journal(cache_path=None)`.

______________________________________________________________________

## Task 1: `gate_cache.py` — slice function, `verified_at`, schema v2

**Files:** modify `cli/engine/gate_cache.py`; tests in `tests/test_engine_gate_cache.py`.

**Interfaces:**

```python
CACHE_SCHEMA_VERSION = 2
_ROTATION_SLICES = 24

def slice_of(cycle_ts: datetime) -> int:
    """The cycle's permanent re-verification slice, in [0, _ROTATION_SLICES).
    sha256 over the ISO timestamp -- NOT builtin hash(), which is not guaranteed
    stable across processes or releases, and NOT the loop index, which moves."""

def due_for_reverification(cycle_ts: datetime, now: datetime) -> bool:
    """True when this cycle falls in the run's current slice (now.hour % _ROTATION_SLICES)."""

@dataclass(frozen=True)
class GateCache:
    replay_fp: str
    entries: dict[datetime, tuple[str, CycleOutcome, datetime]]   # + verified_at
    rejected: bool = False

def oldest_verification_age(cache: GateCache, now: datetime) -> float | None:
    """now - min(verified_at) in seconds; None when the cache is empty."""
```

- [ ] **Step 1: failing tests**
  - `test_slice_of_is_deterministic_and_process_stable` — same `cycle_ts` ⇒ same slice across repeated calls; assert three hardcoded (cycle_ts → slice) pairs so a change to the derivation is caught, not silently absorbed.
  - `test_slice_of_distributes_without_gross_skew` — 480 hourly cycles cover all 24 slices, none holding more than ~3× the mean.
  - `test_due_for_reverification_matches_the_run_hour` — a cycle is due exactly when `slice_of(cycle_ts) == now.hour % 24`, checked across all 24 hours.
  - `test_cache_round_trip_preserves_verified_at` — including `mismatch=True` / `validation_failed=True` entries.
  - `test_v1_cache_is_rejected_wholesale` — a schema_version 1 file ⇒ empty cache, `rejected=True`, no partial read.
  - `test_oldest_verification_age` — returns the least-recent entry's age; `None` on an empty cache.
- [ ] **Steps 2–4:** run → fail → implement → pass.
- [ ] **Step 5:** `uv run pre-commit run -a`; commit `feat(cli): gate-cache rotation slice + verified_at (schema v2)`.

______________________________________________________________________

## Task 2: wire rotation into `_evaluate_journal` + the metrics

**Files:** modify `cli/engine/command.py`; tests in `tests/test_engine_gate_export_cache.py`.

The eligibility test becomes:

```python
reverify = due_for_reverification(record.cycle_ts, now)
if cached_entry is not None and cached_entry[0] == fp and not reverify:
    outcome, verified_at = cached_entry[1], cached_entry[2]   # carry verified_at forward
    from_cache_count += 1
else:
    outcome, verified_at = _replay_one(record, reader), now   # stamp on real verification
    replayed_count += 1
```

`_evaluate_journal` needs `now` — thread it from the caller rather than calling `_utc_now()` internally, so tests can drive the clock.

Metrics: rename `zcrypto_gate_cache_replayed_total` → `zcrypto_gate_cache_replayed`, `_hits_total` → `_hits`; add `zcrypto_gate_cache_oldest_verification_age_seconds` and `zcrypto_gate_export_duration_seconds` (wall, measured around the whole export).

- [ ] **Step 1: failing tests**
  - **`test_tampered_parquet_with_intact_record_is_caught_within_one_rotation`** — THE KEYSTONE. Warm the cache; alter the parquet bytes on disk leaving the record's `content_hash` claim untouched (so `evidence_fingerprint` is unchanged and it would otherwise hit); run once per hour 0–23; the cycle's own slice must force a replay yielding `mismatch=True`. **Must fail if rotation is removed.**
  - `test_rotation_is_bounded` — warm cache, no tampering: one run replays only its slice (≈ n/24), the rest served from cache.
  - `test_warm_equals_cold_with_rotation_active` — `CycleOutcome` lists and `evaluate_gate` status identical (spec `00060` D4 preserved).
  - `test_forced_reverification_failure_counts_as_replayed_and_moves_the_gate` — D4: it lands in `JournalCounts.mismatches`, not in `from_cache`.
  - `test_verified_at_carried_on_hit_stamped_on_replay` — and `oldest_verification_age` falls below one rotation period after a full sweep.
  - `test_metrics_renamed_and_new_ones_present` — no `_total`-suffixed cache gauge remains; both new metrics appear with plausible values.
- [ ] **Steps 2–4:** fail → implement → pass. Also run `tests/test_engine_command.py` and `tests/test_cli_help_hygiene.py`.
- [ ] **Step 5:** gate + commit `feat(cli): rotating re-verification for the gate cache`.

______________________________________________________________________

## Task 3 (orchestrator, not a subagent): real-journal verification + closeout

- [ ] On the ops mirror: no-cache / cold / warm against the **modified** code ⇒ **identical gate metrics**. The iter-110 evidence covers the unmodified predicate and does not carry over.
- [ ] Measure the rotation's real cost: warm-run wall time with rotation vs the 0.30 s of the un-rotated warm run; confirm it is ≈ n/24 replays, not n.
- [ ] Confirm `report` is unaffected (no cache file, same output).
- [ ] Final whole-branch review; fix wave if needed.
- [ ] Closeout: iterations-history entry; [[T0077]] → `resolved` **in the same PR** (see `.claude/rules/open-topics.md` — the flip rides the work); [[T0069]]'s `--cache` sub-item unblocked but still attended; PR into `develop`.

## Self-Review

- Spec coverage: D1→Task 2; D2/D3→Task 1; D4→Task 2; D5→Tasks 1–2; D6→Task 1; D7/D8→Task 2. Spec test-list 1–8 map to Tasks 1–2, item 9 to Task 3.
- Type consistency: `GateCache.entries` values become a 3-tuple `(fp, outcome, verified_at)` — every read site must be updated, and `oldest_verification_age` returns `float | None`, not `float`.
- Grounded: `_evaluate_journal` (`command.py:196`), the eligibility test (`command.py:228-234`), the metric block (`command.py:296-302`), `CACHE_SCHEMA_VERSION` (`gate_cache.py:43`) — all verified present.
