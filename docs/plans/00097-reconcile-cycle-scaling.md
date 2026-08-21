# 00097 — Reconcile cycle scaling: telemetry, vectorization, skip-cache — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The ops reconcile cycle stops scaling with window byte volume — duration telemetry + a 1,500 s warning, int64-μs vectorized gap arithmetic, and a fingerprint skip-cache with a sampled audit — while provably changing nothing about what any hour decides, books, or mints (spec `00097`).

**Architecture:** Three layers that compose: (1) `reconcile()` stamps its own duration and end-of-cycle success into the textfile; (2) the gap arithmetic in `cli/archive/reconcile.py` and `cli/archive/settle.py` moves from Python-datetime lists to int64-microsecond numpy arrays behind unchanged public signatures; (3) a new `cli/archive/scan_cache.py` fingerprints each settled hour's file-set so `command.py` skips hours that provably cannot decide anything new, re-examining 2 LRU hours per cycle as an audit that drops the whole cache on one divergence.

**Tech Stack:** Python 3.14, polars, numpy, pytest + Typer `CliRunner`; Grafana provisioning YAML; Ansible ops role (converge unchanged — same unit, new image).

## Global Constraints

- **Byte-equality is the contract** (spec D6): ledger records, residual seconds, verdicts, and every existing textfile family are identical to develop's output on the same inputs — proven by golden replay, not argued.
- **Strict `>` threshold semantics everywhere** — a window exactly at the threshold is not a gap (both `min_gap_seconds` and `min_seconds` paths).
- **Threshold comparisons stay in float64**: compute `seconds = diff_us / 1e6` and compare `seconds > threshold` — identical arithmetic to `timedelta.total_seconds()`, so no integer-threshold conversion may be introduced.
- **`.to_list()` on a `ts` column is banned from the per-hour hot path** — allowed only inside `classify_dark_episode` input construction (runs only on dark hours) and error-message construction.
- **Public APIs keep their signatures**: `find_book_gaps`, `find_unwitnessed_gaps`, `fleet_dark_windows`, `containing_dark_window` accept what they accept today (the settle pair additionally accepts int64 arrays); `Gap`/`DarkWindow` keep datetime fields.
- **The H-1 straddle limitation comment in `containing_dark_window` is preserved verbatim** — this change must not "fix" it.
- **Metric HELP text carries no internal tokens** (`operator-facing-text.md`; `tests/test_internal_terms_not_operator_visible.py` sweeps `# HELP` literals).
- **The exact non-monotonic error message is preserved**: `"non-monotonic ts in the {pair} book stream: {prev} is followed by {curr}. Refusing to reconcile — sorting is forbidden (L2 rows carry absolute quantities), so the input itself must be fixed."`
- Run everything through `uv run …` from the repo root; commit gate is `uv run pre-commit run -a`; commits per `commit-messages.md` (each implementer credits its own model).
- `ts` is `Datetime(time_unit='us', time_zone='UTC')` — verified on a live segment. `.to_numpy()` yields `datetime64[us]`; `.view(np.int64)` is the zero-copy μs view.

## File map

- `cli/archive/command.py` — duration/end-stamp (Task 1), hot-loop array rewiring + `partition_gaps` call (Task 4), skip/audit integration (Task 6).
- `cli/archive/reconcile.py` — `_message_ts`, `_primary_silence` vectorized; new `partition_gaps`; wrappers (Task 2).
- `cli/archive/settle.py` — `us_from_dt`/`dt_from_us`/`us_array` helpers; `fleet_dark_windows`, `containing_dark_window` vectorized (Task 3).
- `cli/archive/scan_cache.py` — NEW (Task 5).
- `tests/test_archive_reconcile_command.py`, `tests/test_archive_reconcile.py`, `tests/test_archive_settle.py`, NEW `tests/test_archive_scan_cache.py` — per task.
- `infra/grafana/alerts.yaml`, `infra/runbooks/ops.md` — Task 8.
- `docs/reference/fleet-pins.md`, T0147 topic + index, `docs/iterations-history-phase6.md` — Tasks 9–10 (attended/closeout).

---

### Task 1: Cycle-duration gauge + end-of-cycle `last_success` stamp (spec D1)

**Files:**
- Modify: `cli/archive/command.py` — `_write_textfile` (~line 359) and `reconcile()`'s textfile call (~line 909).
- Test: `tests/test_archive_reconcile_command.py`.

**Interfaces:**
- Consumes: `_write_textfile(path, *, now, totals, lags)` — existing.
- Produces: `_write_textfile(path, *, now, ended, totals, lags)` — new required kwarg `ended: datetime`; emits `zcrypto_reconcile_cycle_duration_seconds` (gauge) = `(ended - now).total_seconds()` and stamps `last_success_timestamp_seconds` with `ended.timestamp()` instead of `now.timestamp()`. `now` continues to feed `_lag` and ledger `at` stamps — those semantics are frozen.

- [ ] **Step 1: Write the failing tests.** Locate the existing textfile test(s) in `tests/test_archive_reconcile_command.py` (grep `last_success_timestamp`), then add:

```python
def test_textfile_reports_cycle_duration_and_stamps_completion(tmp_path):
    start = datetime(2026, 8, 21, 8, 12, 15, tzinfo=UTC)
    ended = datetime(2026, 8, 21, 8, 35, 6, tzinfo=UTC)
    out = tmp_path / "reconcile.prom"
    command._write_textfile(out, now=start, ended=ended, totals=command._totals([]), lags={})
    text = out.read_text()
    assert "# TYPE zcrypto_reconcile_cycle_duration_seconds gauge" in text
    assert "zcrypto_reconcile_cycle_duration_seconds 1371.0" in text
    # the success stamp is the END of the cycle, not its start (spec 00097 D1)
    assert f"zcrypto_reconcile_last_success_timestamp_seconds {ended.timestamp()}" in text
    assert f"zcrypto_reconcile_last_success_timestamp_seconds {start.timestamp()}" not in text
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_archive_reconcile_command.py::test_textfile_reports_cycle_duration_and_stamps_completion -v` — FAIL: unexpected keyword `ended`.

- [ ] **Step 3: Implement.** In `_write_textfile`, add `ended: datetime` to the keyword-only signature; change the `last_success_timestamp_seconds` sample from `now.timestamp()` to `ended.timestamp()`; directly below it emit:

```python
    _emit(
        "cycle_duration_seconds",
        "gauge",
        "Wall-clock seconds the last completed reconcile cycle took, start to publish.",
        [("", (ended - now).total_seconds())],
    )
```

In `reconcile()`, at the textfile call site (inside `if textfile is not None:`), capture the end stamp and pass it:

```python
    if textfile is not None:
        lags = {source: _lag(scan, now=now) for source, scan in scans.items()}
        try:
            _write_textfile(textfile, now=now, ended=_utc_now(), totals=totals, lags=lags)
```

Any other `_write_textfile` caller found by `grep -rn "_write_textfile" cli/ tests/` gets the new kwarg with a real `ended`.

- [ ] **Step 4: Run the file's suite.** `uv run pytest tests/test_archive_reconcile_command.py -v` — all PASS (fix any existing test that pinned the start-stamp; the new semantics are the spec).
- [ ] **Step 5: Commit.** `git add cli/archive/command.py tests/test_archive_reconcile_command.py && git commit -m "feat(archive): cycle-duration gauge, and last_success stamps the cycle's end"` (+ trailers per `commit-messages.md`).

---

### Task 2: Vectorize `_message_ts` / `_primary_silence`; add `partition_gaps` (spec D3)

**Files:**
- Modify: `cli/archive/reconcile.py:60-90` (`_message_ts`), `:194-233` (`_primary_silence`), `:136-192` (`find_book_gaps` / `find_unwitnessed_gaps` become wrappers).
- Modify: `cli/archive/settle.py` — add the shared μs helpers (imported by reconcile.py).
- Test: `tests/test_archive_reconcile.py`.

**Interfaces:**
- Produces (settle.py, module level, above `fleet_dark_windows`):

```python
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def us_from_dt(moment: datetime) -> int:
    """Exact microseconds since epoch — integer path only, no float rounding."""
    delta = moment - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def dt_from_us(us: int) -> datetime:
    """Exact inverse of `us_from_dt`."""
    return _EPOCH + timedelta(microseconds=int(us))


def us_array(stamps: Iterable[datetime] | np.ndarray) -> np.ndarray:
    """int64-μs view of `stamps`; ndarray passes through, datetimes convert exactly."""
    if isinstance(stamps, np.ndarray):
        return stamps.astype(np.int64, copy=False)
    return np.fromiter((us_from_dt(s) for s in stamps), dtype=np.int64)
```

- Produces (reconcile.py): `_message_ts(df) -> np.ndarray` (int64 μs, order-preserving dedup, raises the exact frozen error); `partition_gaps(primary, secondary, *, min_gap_seconds, hour_start, hour_end) -> tuple[list[Gap], list[Gap]]` — `(witnessed, unwitnessed)`, computing primary silence **once**; `find_book_gaps`/`find_unwitnessed_gaps` unchanged signatures, now `partition_gaps(...)[0]` / `[1]` with docstrings intact.

- [ ] **Step 1: Failing tests** (append to `tests/test_archive_reconcile.py`, reusing its frame fixtures — read its existing `_book`-style helpers first and use those):

```python
def test_message_ts_returns_int64_microseconds_deduped_in_order():
    df = _frame([(0.0, "snapshot"), (1.5, "update"), (1.5, "update"), (7.25, "update")])
    out = _message_ts(df)
    assert out.dtype == np.int64
    assert [dt_from_us(u) for u in out] == [H, H + timedelta(seconds=1.5), H + timedelta(seconds=7.25)]


def test_message_ts_non_monotonic_error_is_verbatim():
    df = _frame([(5.0, "update"), (0.0, "update")])
    with pytest.raises(CaptureError, match=r"is followed by .*sorting is forbidden"):
        _message_ts(df)


def test_partition_gaps_partitions_every_silence_window():
    primary = _frame([(0.0, "update"), (100.0, "update")])       # one 100 s silence, 0→100
    secondary = _frame([(50.0, "update")])                        # witnesses it
    witnessed, blind = partition_gaps(primary, secondary, min_gap_seconds=30.0, hour_start=H, hour_end=HOUR_END)
    assert [(g.start, g.end) for g in witnessed] == [(H, H + timedelta(seconds=100))]
    # the tail 100→3600 has no witness inside it
    assert [(g.start, g.end) for g in blind] == [(H + timedelta(seconds=100), HOUR_END)]
    assert find_book_gaps(primary, secondary, min_gap_seconds=30.0, hour_start=H, hour_end=HOUR_END) == witnessed
    assert find_unwitnessed_gaps(primary, secondary, min_gap_seconds=30.0, hour_start=H, hour_end=HOUR_END) == blind


def test_threshold_exact_window_is_not_a_gap():
    # 30.0 s exactly: STRICTLY greater is the contract on both sides of the vectorization
    primary = _frame([(0.0, "update"), (30.0, "update"), (3599.0, "update")])
    gaps = _primary_silence(primary, 30.0, H, HOUR_END)
    assert [(g.start.second, g.end.second) for g in gaps] == []  # 30.0 s and 1.0 s windows both below/at threshold


def test_us_round_trip_is_exact():
    moments = [H + timedelta(microseconds=n) for n in (0, 1, 999_999, 123_456_789)]
    assert [dt_from_us(us_from_dt(m)) for m in moments] == moments
```

(`_frame` = the file's existing book-frame builder; if it is named differently, use the existing one — do not mint a duplicate. `test_threshold_exact_window_is_not_a_gap` needs the 3599→3600 tail to also stay sub-threshold, hence the 3599 stamp.)

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_archive_reconcile.py -k "message_ts or partition or threshold_exact or round_trip" -v` — FAILs (dtype/name errors).

- [ ] **Step 3: Implement.** In `settle.py` add the three helpers above (with `import numpy as np` and `Iterable` already imported there). In `reconcile.py` (`from .settle import dt_from_us, us_from_dt` + `import numpy as np`):

```python
def _message_ts(df: pl.DataFrame) -> np.ndarray:
    if df.height == 0:
        return np.empty(0, dtype=np.int64)
    raw = df["ts"].to_numpy().view(np.int64)  # Datetime(us, UTC) → datetime64[us] → μs ints, zero-copy
    drops = np.nonzero(np.diff(raw) < 0)[0]
    if drops.size:
        i = int(drops[0])
        pair = df["symbol"][0] if "symbol" in df.columns else "?"
        raise CaptureError(
            f"non-monotonic ts in the {pair} book stream: {dt_from_us(raw[i]).isoformat()} is followed by "
            f"{dt_from_us(raw[i + 1]).isoformat()}. Refusing to reconcile — sorting is forbidden (L2 rows carry "
            f"absolute quantities), so the input itself must be fixed."
        )
    keep = np.empty(raw.shape, dtype=bool)
    keep[0] = True
    np.not_equal(raw[1:], raw[:-1], out=keep[1:])  # non-decreasing (just proven) ⇒ dropping equal neighbours == unique(maintain_order=True)
    return raw[keep]
```

Keep the docstring, adding one line: "Returns int64 microseconds since epoch (spec 00097 D3); `dt_from_us` is the exact inverse."

```python
def _primary_silence(primary: pl.DataFrame, min_gap_seconds: float, hour_start: datetime, hour_end: datetime) -> list[Gap]:
    """Every window in which the PRIMARY was silent longer than the threshold, witnessed or not."""
    _validate_hour_bounds(hour_start, hour_end)
    _validate_rows_within_hour(primary, "primary", hour_start, hour_end)

    pri = _message_ts(primary)
    if pri.size == 0:
        # (existing whole-hour Gap branch, verbatim)
        return [
            Gap(
                start=hour_start,
                end=hour_end,
                seconds=(hour_end - hour_start).total_seconds(),
                start_is_primary_message=False,
                end_is_primary_message=False,
            )
        ]

    edges = np.concatenate(([us_from_dt(hour_start)], pri, [us_from_dt(hour_end)]))
    seconds = np.diff(edges).astype(np.float64) / 1e6  # identical float to total_seconds()
    idx = np.nonzero(seconds > min_gap_seconds)[0]     # STRICTLY greater, unchanged
    last = edges.size - 1
    return [
        Gap(
            start=dt_from_us(edges[i]),
            end=dt_from_us(edges[i + 1]),
            seconds=float(seconds[i]),
            start_is_primary_message=(i != 0),
            end_is_primary_message=(i + 1 != last),
        )
        for i in idx
    ]


def partition_gaps(
    primary: pl.DataFrame,
    secondary: pl.DataFrame,
    *,
    min_gap_seconds: float,
    hour_start: datetime,
    hour_end: datetime,
) -> tuple[list[Gap], list[Gap]]:
    """Both halves of the primary-silence partition in ONE derivation: (witnessed, unwitnessed).

    `find_book_gaps` and `find_unwitnessed_gaps` are thin views over this — spec 00097 D3 collapses
    what used to be two independent derivations of the same silence windows per pair-hour.
    """
    _validate_hour_bounds(hour_start, hour_end)
    _validate_rows_within_hour(secondary, "secondary", hour_start, hour_end)
    _message_ts(secondary)  # for its check alone: raises on non-decreasing `ts` (see its docstring)
    witnessed: list[Gap] = []
    blind: list[Gap] = []
    for gap in _primary_silence(primary, min_gap_seconds, hour_start, hour_end):
        (witnessed if secondary_covers(secondary, gap) else blind).append(gap)
    return witnessed, blind
```

`find_book_gaps` / `find_unwitnessed_gaps`: keep signatures and full docstrings; bodies become `return partition_gaps(primary, secondary, min_gap_seconds=min_gap_seconds, hour_start=hour_start, hour_end=hour_end)[0]` (resp. `[1]`).

- [ ] **Step 4: Run the whole file.** `uv run pytest tests/test_archive_reconcile.py -v` — every pre-existing test passes UNCHANGED (they are the API contract; if one fails, the vectorization is wrong — fix the code, never the test).
- [ ] **Step 5: Commit.** `git add cli/archive/reconcile.py cli/archive/settle.py tests/test_archive_reconcile.py && git commit -m "feat(archive): int64-us vectorized primary-silence derivation, computed once per pair-hour"`.

---

### Task 3: Vectorize `fleet_dark_windows` / `containing_dark_window` (spec D3)

**Files:**
- Modify: `cli/archive/settle.py:100-176`.
- Test: `tests/test_archive_settle.py`.

**Interfaces:**
- Produces: both functions additionally accept `np.ndarray` (int64 μs) as `stamps`; datetime iterables keep working (the existing tests are the equivalence anchor). Output types unchanged.

- [ ] **Step 1: Failing tests** (append to `tests/test_archive_settle.py`):

```python
def test_fleet_dark_windows_accepts_us_arrays_identically():
    stamps = [_at(0), _at(10), _at(600), _at(3600)]
    as_dt = fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    as_us = fleet_dark_windows(us_array(stamps), hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    assert as_dt == as_us and as_dt  # identical AND non-empty (a vacuous equality proves nothing)


def test_containing_dark_window_accepts_us_arrays_identically():
    stamps = [_at(0), _at(100), _at(700)]
    window = fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)[0]
    a = containing_dark_window(stamps, window, hour_start=H, hour_end=HOUR_END)
    b = containing_dark_window(us_array(stamps), window, hour_start=H, hour_end=HOUR_END)
    assert a == b and a is not None
```

- [ ] **Step 2: Verify failure.** `uv run pytest tests/test_archive_settle.py -k us_arrays -v` — FAIL (`us_array` import error until the test imports it; add `from cli.archive.settle import us_array` to the test file's imports).

- [ ] **Step 3: Implement.** Replace the bodies (docstrings stay, including the H-1 straddle comment block verbatim):

```python
def fleet_dark_windows(
    stamps: Iterable[datetime] | np.ndarray, *, hour_start: datetime, hour_end: datetime, min_seconds: float
) -> list[DarkWindow]:
    arr = us_array(stamps)
    lo, hi = us_from_dt(hour_start), us_from_dt(hour_end)
    inside = np.unique(arr[(arr >= lo) & (arr <= hi)])  # sorted + deduped == sorted(set(...)); bounds inclusive as before
    edges = np.concatenate(([lo], inside, [hi]))
    seconds = np.diff(edges).astype(np.float64) / 1e6
    idx = np.nonzero(seconds > min_seconds)[0]  # STRICTLY greater, matching find_book_gaps
    return [
        DarkWindow(start=dt_from_us(edges[i]), end=dt_from_us(edges[i + 1]), seconds=float(seconds[i]))
        for i in idx
    ]
```

```python
def containing_dark_window(
    stamps: Iterable[datetime] | np.ndarray, window: DarkWindow, *, hour_start: datetime, hour_end: datetime
) -> DarkWindow | None:
    # (docstring + KNOWN LIMITATION comment verbatim)
    arr = us_array(stamps)
    lo, hi = us_from_dt(hour_start), us_from_dt(hour_end)
    inside = np.unique(arr[(arr >= lo) & (arr <= hi)])
    edges = np.concatenate(([lo], inside, [hi]))
    ws, we = us_from_dt(window.start), us_from_dt(window.end)
    i = int(np.searchsorted(edges, ws, side="right")) - 1  # the interval whose left edge is the last one <= window.start
    if i < 0 or i + 1 >= edges.size:
        return None
    a, b = int(edges[i]), int(edges[i + 1])
    if a <= ws and we <= b:
        return DarkWindow(start=dt_from_us(a), end=dt_from_us(b), seconds=(b - a) / 1e6)
    return None
```

(Consecutive edge intervals partition the hour, so only the interval bracketing `window.start` can contain the whole window — `searchsorted` replaces the linear scan without changing which interval is chosen, including when `window.start` equals an interior stamp: `side="right"` lands on the interval that *starts* at that stamp, exactly the one the linear scan would have accepted.)

- [ ] **Step 4: Run the whole file.** `uv run pytest tests/test_archive_settle.py -v` — every pre-existing test green unchanged.
- [ ] **Step 5: Commit.** `git add cli/archive/settle.py tests/test_archive_settle.py && git commit -m "feat(archive): fleet-dark derivation on int64-us arrays"`.

---

### Task 4: Rewire `command.py`'s hot loop to arrays and `partition_gaps` (spec D3)

**Files:**
- Modify: `cli/archive/command.py:584-700` (stamps collection, `both_streams_silent` block) and `:700-760` (heal block's gap calls).
- Test: `tests/test_archive_reconcile_command.py` (existing tests are the contract; no new tests except the truthiness regression below).

**Interfaces:**
- Consumes: `partition_gaps` (Task 2), array-accepting `fleet_dark_windows`/`containing_dark_window` (Task 3).

- [ ] **Step 1: One regression test first** — ndarray truthiness is the known trap (`if pair_stamps.get(p)` raises on arrays). Add to `tests/test_archive_reconcile_command.py` a case that books a `both_streams_silent` hour where a pair has BOTH mirrors readable (so the `containing_dark_window` branch runs on a non-empty array). If the existing dark-hour test already covers both-mirrors-readable (check for `stream_windows` assertions), note that in the report instead of duplicating it.
- [ ] **Step 2: Rewire.** In the per-hour book-load block replace the two `.to_list()` extends:

```python
        books: dict[str, dict[str, pl.DataFrame | None]] = {}
        stamp_parts: list[np.ndarray] = []
        pair_parts: dict[str, list[np.ndarray]] = {}
        broken = False
        for pair in book_pairs:
            frames: dict[str, pl.DataFrame | None] = {}
            for source, root in (("primary", primary_root), ("secondary", secondary_root)):
                ...  # unchanged guards and _read
                arr = frames[source]["ts"].to_numpy().view(np.int64)
                stamp_parts.append(arr)
                pair_parts.setdefault(pair, []).append(arr)
            books[pair] = frames
```

Before `fleet_dark_windows`: `stamps = np.concatenate(stamp_parts) if stamp_parts else np.empty(0, dtype=np.int64)` and `pair_stamps = {p: np.concatenate(parts) for p, parts in pair_parts.items()}`. In the `stream_windows` construction replace the truthiness guard: `if both_mirrors and pair_stamps.get(p) is not None and pair_stamps[p].size` (was `and pair_stamps.get(p)`). The `classify_dark_episode` input block is untouched (it already reads from `books[p]` frames, not from `stamps`).

In the heal block, replace the `find_book_gaps` call with `gaps, blind = partition_gaps(primary, secondary, min_gap_seconds=min_gap_seconds, hour_start=hour, hour_end=hour_end)` (same `try/except CaptureError` wrapper) and delete the later `find_unwitnessed_gaps` call — the unwitnessed block consumes `blind` directly. Everything else in both blocks stays byte-identical.

- [ ] **Step 3: Run the command suite.** `uv run pytest tests/test_archive_reconcile_command.py tests/test_archive_reconcile.py tests/test_archive_settle.py -v` — all green.
- [ ] **Step 4: Spot-benchmark.** `time uv run python -m cli archive reconcile /mnt/zhao-crypto/capture-segments /mnt/zhao-crypto/capture-segments-red <scratch-dir> --window-hours 4` — record the wall time in the task report beside Task 7's baseline of **103.9 s** for the same window shape (expect single-digit seconds; if not <20 s, profile before proceeding).
- [ ] **Step 5: Commit.** `git add cli/archive/command.py tests/test_archive_reconcile_command.py && git commit -m "feat(archive): hot loop hands us arrays to the dark-window derivation"`.

---

### Task 5: `scan_cache.py` — fingerprints, entries, atomic persistence, audit pick (spec D4/D5)

**Files:**
- Create: `cli/archive/scan_cache.py`.
- Test: `tests/test_archive_scan_cache.py` (new).

**Interfaces (produces — Task 6 consumes exactly these):**

```python
ALGO_VERSION = 1


@dataclass(frozen=True)
class CacheEntry:
    fingerprint: str    # sha256 hex over the hour's file-set (presences with size+mtime_ns, plus absences)
    examined_at: str    # isoformat of the cycle-start `now` of the FULL examination that wrote this entry
    late_at_exam: bool  # the examination ran with the hour past LATE_MINT_HOURS
    failures: int       # failures attributed to this hour during that examination
    complete: bool      # no expected final was absent at examination time


def algo_salt(min_gap_seconds: float) -> str          # f"v{ALGO_VERSION}:min_gap={min_gap_seconds!r}"
def hour_fingerprint(hour, *, primary_root, secondary_root, book_pairs, trade_pairs) -> tuple[str, bool]
    # (sha256, complete). Expected set: every book pair × book × both roots, every trade pair × trades × both roots.
    # Present file → line "pair|kind|source|size|mtime_ns"; absent → "ABSENT|pair|kind|source". complete = no ABSENT line.
def load_cache(reconciled_root, *, salt) -> dict[str, CacheEntry]   # {} on absent/corrupt/foreign-salt — fail-open to slow
def save_cache(reconciled_root, entries, *, salt) -> None           # JSON {"algo": salt, "hours": {...}}, tmp + os.replace
def delete_cache(reconciled_root) -> None                            # missing_ok
def is_skippable(entry, fingerprint, complete) -> bool               # the five spec-D4 preconditions in one place
def pick_audit_hours(skippable_hours, entries, k=2) -> list[str]     # k oldest examined_at, ties by hour ascending
```

Note one deliberate simplification vs the spec's field list, to be echoed in the PR: `last_audited` collapses into `examined_at` — an audited hour is *fully examined*, so its `examined_at` advances and "least-recently-audited" is exactly "oldest `examined_at`". Same rotation, one field.

- [ ] **Step 1: Failing tests** — `tests/test_archive_scan_cache.py`, using the segment-tree fixture idiom from `tests/test_archive_reconcile_command.py` (`_seg_path`/`_write`):

```python
def test_fingerprint_changes_on_size_mtime_new_file_and_absence(tmp_path): ...
    # write BTC book hour on both roots → fp1, complete=True (with book_pairs=["BTC/EUR"], trade_pairs=[])
    # append bytes to one file → fp2 != fp1; bump only mtime via os.utime → fp3 != fp2
    # delete the secondary file → (fp4, complete=False) and fp4 != fp3

def test_load_returns_empty_on_absent_corrupt_and_foreign_salt(tmp_path): ...
    # absent → {}; write garbage bytes → {}; save with salt A, load with salt B → {}

def test_save_load_round_trip_atomic(tmp_path): ...
    # save two entries, load, equality; no *.tmp file left behind

def test_is_skippable_requires_all_five_preconditions(): ...
    # a fully-good entry is skippable; then each of: fp mismatch, late_at_exam=False,
    # failures=1, complete=False (stored) and complete=False (current) — flips it to False

def test_pick_audit_hours_is_oldest_examined_first_and_deterministic(): ...
    # three skippable hours with distinct examined_at → the two oldest, in hour order; ties break by hour
```

Write them as real tests (each ~6 lines with the fixtures), run: `uv run pytest tests/test_archive_scan_cache.py -v` — FAIL (module absent).

- [ ] **Step 2: Implement `cli/archive/scan_cache.py`** (~100 lines):

```python
"""Per-hour examination fingerprints for the reconcile skip-cache (spec 00097 D4/D5).

Mirror finals are immutable once pulled (written at hour close, hash-verified hourly by the NAS
pull), so `(size, mtime_ns)` identifies a final exactly; the fingerprint also records ABSENCES so a
file arriving late re-examines the hour. `load_cache` never raises — absent, corrupt, and
foreign-salt caches all read as empty, so every failure is fail-open to a SLOW full cycle, never to
a wrong skip. Written atomically (`checkpoint.py`'s tmp + `os.replace` idiom).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .settle import hour_path

ALGO_VERSION = 1
_FILENAME = "scan-cache.json"


@dataclass(frozen=True)
class CacheEntry:
    fingerprint: str
    examined_at: str
    late_at_exam: bool
    failures: int
    complete: bool


def algo_salt(min_gap_seconds: float) -> str:
    return f"v{ALGO_VERSION}:min_gap={min_gap_seconds!r}"


def hour_fingerprint(
    hour: datetime, *, primary_root: Path, secondary_root: Path, book_pairs: list[str], trade_pairs: list[str]
) -> tuple[str, bool]:
    lines: list[str] = []
    complete = True
    for kind, pairs in (("book", book_pairs), ("trades", trade_pairs)):
        for pair in pairs:
            for source, root in (("primary", primary_root), ("secondary", secondary_root)):
                path = hour_path(root, pair, kind, hour)
                try:
                    st = path.stat()
                    lines.append(f"{pair}|{kind}|{source}|{st.st_size}|{st.st_mtime_ns}")
                except FileNotFoundError:
                    lines.append(f"ABSENT|{pair}|{kind}|{source}")
                    complete = False
    lines.sort()
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), complete


def _cache_path(reconciled_root: Path) -> Path:
    return reconciled_root / _FILENAME


def load_cache(reconciled_root: Path, *, salt: str) -> dict[str, CacheEntry]:
    try:
        payload = json.loads(_cache_path(reconciled_root).read_text())
        if payload.get("algo") != salt:
            return {}
        return {hour: CacheEntry(**entry) for hour, entry in payload["hours"].items()}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def save_cache(reconciled_root: Path, entries: dict[str, CacheEntry], *, salt: str) -> None:
    path = _cache_path(reconciled_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"algo": salt, "hours": {h: asdict(e) for h, e in entries.items()}}))
    os.replace(tmp, path)


def delete_cache(reconciled_root: Path) -> None:
    _cache_path(reconciled_root).unlink(missing_ok=True)


def is_skippable(entry: CacheEntry | None, fingerprint: str, complete: bool) -> bool:
    """Spec 00097 D4: all five preconditions, in one place, fail-closed."""
    return (
        entry is not None
        and entry.fingerprint == fingerprint
        and entry.late_at_exam
        and entry.failures == 0
        and entry.complete
        and complete
    )


def pick_audit_hours(skippable_hours: list[str], entries: dict[str, CacheEntry], k: int = 2) -> list[str]:
    """The k skippable hours least recently FULLY examined — deterministic, no randomness (D5)."""
    return sorted(skippable_hours, key=lambda h: (entries[h].examined_at, h))[:k]
```

(`hour_path` lives in settle.py — import it rather than re-deriving the layout. The salt check on `algo` also covers `min_gap_seconds` changes by construction.)

- [ ] **Step 3: Run.** `uv run pytest tests/test_archive_scan_cache.py -v` — all PASS.
- [ ] **Step 4: Commit.** `git add cli/archive/scan_cache.py tests/test_archive_scan_cache.py && git commit -m "feat(archive): scan-cache fingerprints with fail-open persistence"`.

---

### Task 6: Skip + audit integration in `reconcile()` (spec D4/D5)

**Files:**
- Modify: `cli/archive/command.py` — after the `seen`/`failures` setup (~line 528) and at the per-hour loop (~line 557).
- Test: `tests/test_archive_reconcile_command.py`.

**Interfaces:**
- Consumes: everything Task 5 produces, `is_late` from settle.py.

**Precondition to verify before editing** (put the answer in the task report): the per-hour body has **no hour-level `continue`** — every `continue` in lines 557-900 belongs to an inner `for pair …` loop, so code appended at the bottom of the hour body runs for every examined hour. Verify by reading the indentation, not by assumption.

- [ ] **Step 1: Failing tests** (command-level, real trees via the file's fixtures; run the CLI twice via `CliRunner` with distinct `--textfile` paths where needed):

```python
def test_second_cycle_skips_settled_hours_and_first_does_not(tmp_path, caplog): ...
    # Build THREE healthy LATE hours on both roots (all book+trades finals present for one pair).
    # k=2 audit arithmetic: with fewer than 3 skippable hours the audit claims them all and nothing
    #   is ever skipped — 3 skippable − 2 audited = 1 skipped, deterministically the NEWEST hour
    #   (equal examined_at from cycle 1, tie broken by hour ascending, oldest two audited).
    # Cycle 1: summary logs skipped=0; scan-cache.json exists afterwards with 3 entries.
    # Cycle 2 (same trees): summary logs skipped=1 audited=2, and the ledger gains NO new records.

def test_changed_file_reexamines(tmp_path): ...
    # Same three-hour setup, both cycles as above — but before cycle 2, os.utime the NEWEST hour's
    #   final (the one that would have been skipped): cycle 2 logs skipped=0 — the fingerprint
    #   mismatch forced it back to a full examination.

def test_non_late_hour_is_never_cached(tmp_path): ...
    # Hour between SETTLED and LATE: cycle 1 examines; cache carries late_at_exam=False; cycle 2 examines again.

def test_audit_divergence_drops_cache_and_logs_error(tmp_path, caplog): ...
    # Cycle 1 on a healthy late hour → cached. Delete the ledger file (so `seen` is empty next run)
    #   but keep the trees: cycle 2's audit re-examines the hour, appends records where the cache said
    #   settled → divergence: ERROR "scan-cache audit divergence" logged AND scan-cache.json deleted.
    # (Deleting the ledger is the cheapest constructible divergence; the mechanism under test is
    #   generic: audit examination changed records/failures ⇒ drop everything.)

def test_corrupt_cache_is_a_full_cycle(tmp_path): ...
    # Write garbage into scan-cache.json → cycle runs full (skipped count 0), then rewrites a valid cache.
```

Run: FAIL (no skip machinery yet).

- [ ] **Step 2: Implement.** After `failures = 0` add the pre-pass:

```python
    salt = scan_cache.algo_salt(min_gap_seconds)
    cache = scan_cache.load_cache(reconciled_root, salt=salt)
    window = settled_hours(now=now, window_hours=window_hours)
    fingerprints = {
        hour.isoformat(): scan_cache.hour_fingerprint(
            hour, primary_root=primary_root, secondary_root=secondary_root,
            book_pairs=book_pairs, trade_pairs=trade_pairs,
        )
        for hour in window
    }
    skippable = [
        iso for iso, (fp, complete) in fingerprints.items()
        if scan_cache.is_skippable(cache.get(iso), fp, complete)
    ]
    audit_hours = set(scan_cache.pick_audit_hours(skippable, cache))
    skip_hours = set(skippable) - audit_hours
    new_cache: dict[str, scan_cache.CacheEntry] = {}
    cache_divergent = False
```

Change the loop to iterate `for hour in window:` (same list the fingerprints used — never call `settled_hours` twice with a drifting `now`). At the top of the body:

```python
        hour_iso = hour.isoformat()
        if hour_iso in skip_hours:
            new_cache[hour_iso] = cache[hour_iso]  # carried forward untouched
            continue
        records_before, failures_before = len(records), failures
```

At the very bottom of the hour body (after the trades loop, same indent as `hour_end = …`):

```python
        fp, complete = fingerprints[hour_iso]
        if hour_iso in audit_hours and (len(records) != records_before or failures != failures_before):
            logger.error(
                "archive reconcile: scan-cache audit divergence hour=%s fingerprint=%s -- the fingerprint "
                "model failed somewhere, dropping the whole cache",
                hour_iso,
                fp,
            )
            cache_divergent = True
        new_cache[hour_iso] = scan_cache.CacheEntry(
            fingerprint=fp,
            examined_at=now.isoformat(),
            late_at_exam=late,
            failures=failures - failures_before,
            complete=complete,
        )
```

After the loop (before the `totals = _totals(records)` line):

```python
    if cache_divergent:
        scan_cache.delete_cache(reconciled_root)
    else:
        scan_cache.save_cache(reconciled_root, new_cache, salt=salt)
```

Extend the completion log line with the two new counts: `… failures=%d skipped=%d audited=%d` (values `len(skip_hours)`, `len(audit_hours & {h.isoformat() for h in window})` — audit_hours is already window-scoped, so `len(audit_hours)`).

- [ ] **Step 3: Run.** `uv run pytest tests/test_archive_reconcile_command.py -v` — new and pre-existing all green (pre-existing single-cycle tests are unaffected: a first cycle skips nothing).
- [ ] **Step 4: Full local gate.** `uv run pytest` (data-dependent tests skip without `data/ohlc-full`; note which skipped) and `uv run pre-commit run -a`.
- [ ] **Step 5: Commit.** `git add cli/archive/command.py tests/test_archive_reconcile_command.py && git commit -m "feat(archive): settled hours skip behind fingerprints, two audited per cycle"`.

---

### Task 7: Golden equivalence + benchmark (spec D6) — workstation, real mirrors

**Files:** none committed — scratch only (`$SCRATCH` = the session scratchpad dir). Results go verbatim into the task report, then into T0147's resolution (Task 10).

- [ ] **Step 1: Choose the window.** `WINDOW=72`; verify `2026-08-20T07:00` is inside: it is iff `now - 72h - 2h < 2026-08-20 07:00` — if not (plan executed later than 2026-08-24), widen WINDOW so the four historical dark hours' nearest one is covered, and say so in the report.
- [ ] **Step 2: Develop baseline.**

```bash
git worktree add "$SCRATCH/golden-develop" develop
cd "$SCRATCH/golden-develop" && uv sync
mkdir -p "$SCRATCH/out-develop"
time uv run python -m cli archive reconcile /mnt/zhao-crypto/capture-segments /mnt/zhao-crypto/capture-segments-red "$SCRATCH/out-develop" --window-hours 72
```

- [ ] **Step 3: Branch, cold + warm.** From the repo root (branch checkout), same command into `$SCRATCH/out-branch` — run it **twice** (cold builds the cache, warm consumes it), `time` both.
- [ ] **Step 4: Diff.**

```bash
uv run python - <<'PY'
import json, sys
def norm(path):
    out = []
    for line in open(path):
        r = json.loads(line)
        r.pop("at", None)
        out.append(json.dumps(r, sort_keys=True))
    return out
a = norm("SCRATCH/out-develop/reconcile-ledger.jsonl")
b = norm("SCRATCH/out-branch/reconcile-ledger.jsonl")
print("ledger records:", len(a), len(b))
sys.exit(0 if a == b else 1)
PY
```

(with `SCRATCH` substituted; non-zero exit = STOP, the vectorization or cache changed a decision — that is a Task 2-6 bug, never something to normalize away). Warm-run check: the warm ledger must equal the cold ledger byte-for-byte (`cmp`), since a second run over unchanged inputs decides nothing new.
- [ ] **Step 5: Record.** In the report: develop wall time, branch cold, branch warm, record counts, and the dark-hour verdict lines from both logs (must match). Then `git worktree remove "$SCRATCH/golden-develop"`.

---

### Task 8: Alert rule + runbook (spec D2)

**Files:**
- Modify: `infra/grafana/alerts.yaml` (insert directly after the `zcrypto-reconcile-exporter-stale` rule, before `zcrypto-reconcile-residual-gap`).
- Modify: `infra/runbooks/ops.md` (new section + one stale sentence fix).
- Test: `uv run pytest tests/test_internal_terms_not_operator_visible.py -q` and `uv run pre-commit run -a` (yamllint).

- [ ] **Step 1: The rule** (push happens in Task 9 — this lands YAML only):

```yaml
  - uid: zcrypto-reconcile-cycle-duration
    title: "Reconciler · cycle approaching its own tick"
    ruleGroup: zcrypto-reconciler
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      # The overlay-writer runs every 30 min; a cycle at 1500 s is 83% of that interval. Past 1800 s
      # the timer's trigger fires against a still-activating unit and is DROPPED, so the cadence
      # silently halves -- and nothing else pages below the exporter-stale rule's 3 h. This gauge is
      # published by the cycle itself, so absence is that rule's page, not this one's (noDataState OK).
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: zcrypto_reconcile_cycle_duration_seconds
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: gt, params: [1500]}
    noDataState: OK  # absence = exporter/cycle gone = zcrypto-reconcile-exporter-stale's page; double-paging one failure helps nobody
    execErrState: Alerting
    for: 0s  # one slow cycle is already the signal -- the gauge only updates twice an hour
    annotations:
      summary: "A reconcile cycle took over 1500 s against its 1800 s half-hourly tick. Past the tick the timer's next trigger is silently dropped and the booking cadence halves. Usually market-volume growth in the 48 h window; check the cycle-duration trend and the skip counts in the cycle log. Runbook: infra/runbooks/ops.md#zcrypto-reconcile-cycle-duration"
      unit: "seconds the last completed cycle took"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics
```

- [ ] **Step 2: Runbook.** New `infra/runbooks/ops.md` section (anchor `zcrypto-reconcile-cycle-duration`, same shape as its siblings): *What you are seeing* — the last completed cycle exceeded 1,500 s of its 1,800 s tick. *What it means* — duration tracks the 48 h window's data volume plus the number of non-skipped hours; the skip-cache normally holds steady-state cycles to tens of seconds, so a page here means the cache is being bypassed (look for `scan-cache audit divergence` at ERROR, or a fingerprint churn — an incomplete hour re-examining every cycle) or volume genuinely outgrew the vectorized floor. *What to do* — read the cycle log's `skipped=`/`audited=` counts; `skipped=0` on consecutive cycles means the cache is not engaging (divergence dropped it, or hours are incomplete — check for absent finals); a healthy skip count with high duration means volume — re-derive headroom before the next vol regime and consider the incremental redesign registered in the topic that created this rule. *Retire when* — the rule is absent from `alerts.yaml`, i.e. deliberately removed.
  Also fix the now-stale sentence added 2026-08-21 in the residual-gap section: replace "and the stamp is written near cycle *start*, so it lags a long cycle's completion" with "and since spec `00097` the stamp is written at cycle *completion*".
- [ ] **Step 3: Gates.** `uv run pre-commit run -a` and `uv run pytest tests/test_internal_terms_not_operator_visible.py -q` — green.
- [ ] **Step 4: Commit.** `git add infra/grafana/alerts.yaml infra/runbooks/ops.md && git commit -m "feat(obs): warn when the reconcile cycle nears its tick"`.

---

### Task 9: Rollout (spec D7) — **ATTENDED, main session only**

Host-touching steps never go to a subagent (`agent-ops.md`). Sequence, each verified before the next:

- [ ] 1. Whole-branch review (Fable floor — reconcile books permanent loss), trailers, push. CI builds the image for the branch head.
- [ ] 2. `gh run watch` the image build; read the new digest from the workflow output or `ghcr` manifest — never from memory.
- [ ] 3. Pull the digest on the ops host (`ssh hp sudo docker pull ghcr.io/zhaow-de/zcrypto-capture@sha256:<new>`).
- [ ] 4. `docs/reference/fleet-pins.md`: ops row → the new digest, rollback operand = current `6b4c13899653`; converge evidence goes in this commit's MESSAGE.
- [ ] 5. Check `https://status.kraken.com/api/v2/scheduled-maintenances.json` for a published `WebSocket`/`REST` window (T0145 rule) + sweep open-topics/memo for blockers; present both with the converge request.
- [ ] 6. Converge: `infra/ansible/scripts/converge.sh --limit zcrypto-ops -e ops_image_digest=sha256:<new> -e liquidations_decision=roll-after` (no `ops_alloy_digest` — `config.alloy` untouched; `daemon.json` untouched). Time it between `:12`/`:42` ticks.
- [ ] 7. First post-converge cycle: read `cycle_duration_seconds` **by value** (expect a full cache-building cycle, roughly the Task 7 cold time scaled to 48 h). Second cycle: expect the warm O(1) number. `infra/scripts/ops-postverify.sh` green; `(no series)` reads FAIL.
- [ ] 8. Push the D2 rule: `PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh` with the vaulted token per the script header; verify the new rule evaluates against the live sample (state OK, value = the warm duration) — by value, not presence.

### Task 10: Closeout

- [ ] T0147 → `resolved` + archive + index move (`topic-ops` mechanics): the resolution records the measured before/after (1,371 s → cold/warm numbers), the golden-equivalence result, the audit design, and the alert uid. No decisions-log entry — engineering, not subject-matter (the `decisions-log.md` gate). No data-catalog change — the scan-cache is operational state, not a dataset.
- [ ] Append the iterations-history entry (phase 6 file — `iteration-closeout` skill): telemetry, vectorization (with the 60 %/97 % profile), skip-cache + audit, alert, and the golden-equivalence proof. Re-verify every status claim against the full branch log immediately before PR-open (`iterations-history.md`).
- [ ] PR into `develop` on the user's word (`open-pr` skill).

---

## Self-review (run before committing the plan)

1. **Spec coverage**: D1→Task 1, D2→Task 8+9.8, D3→Tasks 2-4, D4→Tasks 5-6, D5→Tasks 5-6 (audit), D6→Task 7 + per-task tests, D7→Task 9, resolution definition→Task 10. `last_audited`→`examined_at` simplification flagged in Task 5 and for the PR body.
2. **Placeholders**: Task 5 Step 1 test bodies are outlined with `...` — deliberate: each names its exact construction and assertion in prose and the fixtures exist; the implementer writes the bodies. Everything else is concrete code.
3. **Type consistency**: `us_from_dt`/`dt_from_us`/`us_array` defined once in settle.py (Task 2), consumed in Tasks 2-4; `CacheEntry` fields consistent between Tasks 5 and 6; `partition_gaps` signature identical in Tasks 2 and 4.
