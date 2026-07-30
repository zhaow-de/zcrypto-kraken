# Archive verification instruments, re-fitted — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `continuity.py` measures silence and truncation against measured stream density instead of density-blind constants, refuses to score a stream it cannot self-calibrate, and the daily `verify-replay` stops paging forever on one historical bad hour — closing T0097.

**Architecture:** One new pure function, `stream_timeline()`, turns a stream's segment list into (a) the threshold sample, (b) the intra-row silence source, and (c) a short list of classified boundary intervals. `report()` consumes it: threshold from the sample, silence from intra, booking and truncation counting from the boundaries. The `verify-replay` change is one rendered argument.

**Tech Stack:** Python 3.14, polars, pytest, Jinja2 (template render harness), bash.

## Global Constraints

- Spec of record: `docs/specs/00076-continuity-instruments-design.md`. Every decision below cites its D-number; do not invent behavior the spec does not name.
- `infra/scripts/continuity.py` is the **T0003 exit-bar instrument** and must keep running on a host with only stdlib + polars. Do NOT add imports beyond `argparse`, `datetime`, `re`, `dataclasses`, `pathlib`, `polars` at module top. The `cli.archive.reader` import stays lazy inside `_canonical_streams`.
- **`--overlay` exit-bar isolation is untouched** (spec 00050): the canonical report never prints a verdict line. `report()` keeps its required `show_exit_bar` parameter with no default.
- Threshold formula stays `max(p99.99(pool) × 10, 5.0)` (D2). Do not change the multiplier, the floor, or the quantile.
- The exit bar's numeric threshold stays `< 0.1 %`.
- `UNMEASURED` bound is **5002** pooled intervals (D6) — Task 1 measures the constant before any code depends on it.
- Every guard added here is proven by constructing the defect it names and watching it trip (`.claude/rules/agent-ops.md`); reading the assertion is not verification.
- **The PROPERTY each test asserts is the contract; its fixture constants are worked examples.** Row counts, spacings and expected seconds were computed by hand and several were wrong on the first pass (the cold review caught an off-by-one and a same-day `--since`). If a constant does not reproduce, fix the fixture arithmetic and say so — never weaken the assertion, and never let a row spill past its own hour (the real tree partitions by timestamp, so such a fixture tests a shape that cannot exist).
- **Fixtures must clear `MIN_POOL`.** Anything under 5,002 intervals is `UNMEASURED` by design, which silently turns an assertion about gap booking into an assertion about nothing.
- Commit after each task. Stage by explicit path, one kind per commit (`.claude/rules/commit-messages.md`; the `staged-kind` hook enforces the claude/non-claude boundary).
- Run the full gate before each commit: `uv run pre-commit run -a`.

---

### Task 1: Test harness + the degeneracy bound, measured

**Files:**
- Create: `tests/test_infra_continuity.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `write_stream(root, pair, hours, *, kind="book")` — a fixture builder later tasks reuse. Signature: `write_stream(root: Path, pair: str, hours: dict[datetime, list[datetime]], kind: str = "book") -> None`, writing `<root>/<base>/<quote>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` with a single `ts` column (µs precision, UTC).

- [ ] **Step 1: Write the fixture builder and the bound test**

```python
"""T0097 / spec 00076: the continuity instrument's measurement semantics.

Every test here constructs the defect it names and asserts the instrument reacts -- reading the
assertion is not verification (`.claude/rules/agent-ops.md`).
"""

import datetime as dt
import importlib.util
from pathlib import Path

import polars as pl
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/continuity.py"

UTC = dt.UTC


def _load():
    # Imported by path, not as a package module: the script is standalone by design (stdlib +
    # polars only, so it runs on a host without the repo installed). Cache-busting matters --
    # a same-second, same-length edit can leave a stale .pyc valid (`agent-ops.md`).
    spec = importlib.util.spec_from_file_location("continuity_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


continuity = _load()


def write_stream(root: Path, pair: str, hours: dict[dt.datetime, list[dt.datetime]], kind: str = "book") -> None:
    """Write one segment file per hour. `hours` maps the hour-start to that hour's row timestamps."""
    base, quote = pair.split("/")
    for h, stamps in hours.items():
        d = root / base / quote / kind / f"{h.year:04d}" / f"{h.month:02d}" / f"{h.day:02d}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({"ts": pl.Series(stamps, dtype=pl.Datetime("us", "UTC"))}).write_parquet(d / f"{h.hour:02d}.parquet")


def evenly(h: dt.datetime, n: int, step: float, start: float = 0.0) -> list[dt.datetime]:
    """`n` timestamps inside hour `h`, `step` seconds apart, beginning `start` seconds in."""
    return [h + dt.timedelta(seconds=start + i * step) for i in range(n)]


@pytest.mark.parametrize(("n", "degenerate"), [(5001, True), (5002, False)])
def test_quantile_degeneracy_bound_is_measured_not_assumed(n, degenerate):
    """D6's constant, pinned to polars' observed behavior.

    With nearest interpolation `quantile(0.9999)` returns the element at round(0.9999*(n-1)),
    which IS the maximum until n exceeds 5001 -- so below the bound the derived threshold is
    10x the worst outage and the instrument is structurally blind.
    """
    s = pl.Series([1.0] * (n - 1) + [9999.0])
    assert (s.quantile(0.9999) == s.max()) is degenerate


def test_min_pool_matches_the_measured_bound():
    assert continuity.MIN_POOL == 5002
```

- [ ] **Step 2: Run it — the bound test passes, the constant test fails**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: `test_quantile_degeneracy_bound_is_measured_not_assumed` PASSES both params (it measures polars, which needs no production change); `test_min_pool_matches_the_measured_bound` FAILS with `AttributeError: module ... has no attribute 'MIN_POOL'`.

If the bound test fails instead, **stop and report**: polars' quantile behavior differs from the spec's derivation and D6's constant must be re-derived from what you measured, not forced.

- [ ] **Step 3: Add the constant**

In `infra/scripts/continuity.py`, after `FINAL = re.compile(r"^\d{2}$")`:

```python
# D6: with polars' default nearest interpolation, quantile(0.9999) returns the element at
# round(0.9999*(n-1)) -- which IS the maximum while n <= 5001, so the derived threshold would be
# 10x the worst outage and the instrument blind by construction. Below this many pooled intervals a
# stream is reported UNMEASURED rather than scored. The bound is pinned by
# tests/test_infra_continuity.py, which measures polars rather than trusting this comment.
MIN_POOL = 5002
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add tests/test_infra_continuity.py infra/scripts/continuity.py
git commit
```
Message: `test(infra): pin the quantile degeneracy bound continuity.py must refuse below`

---

### Task 2: `stream_timeline()` — the interval model

**Files:**
- Modify: `infra/scripts/continuity.py`
- Test: `tests/test_infra_continuity.py`

**Interfaces:**
- Consumes: `MIN_POOL` (Task 1); `write_stream`/`evenly` fixtures (Task 1).
- Produces:

```python
@dataclasses.dataclass(frozen=True)
class StreamTimeline:
    pool: pl.Series              # float seconds: intra-row diffs + contiguous-hour crossings (threshold sample, D1)
    intra: pl.Series             # float seconds: intra-row diffs only (silence booking source)
    boundaries: list[tuple[float, str]]  # (seconds, kind) with kind in {"crossing","excess","edge_head","edge_tail"}
    missing_hours: int
    span_hours: int
    genesis_skipped: bool

def stream_timeline(segs: list[tuple[dt.datetime, Path]], *, genesis_hour: dt.datetime) -> StreamTimeline: ...
```

`segs` is the already-`--since`-filtered, sorted `(hour, path)` list. `genesis_hour` is the stream's earliest hour **in the unfiltered tree** (D5).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_infra_continuity.py`:

```python
H0 = dt.datetime(2026, 7, 1, 10, tzinfo=UTC)
H1 = H0 + dt.timedelta(hours=1)
H2 = H0 + dt.timedelta(hours=2)


def _segs(root: Path, pair: str, kind: str = "book"):
    return sorted(continuity.segments(root, kind)[pair])


def test_contiguous_crossing_is_pooled_and_classified(tmp_path):
    # Two adjacent hours, 1 s spacing, the crossing indistinguishable from an ordinary interval.
    write_stream(tmp_path, "AAA/EUR", {H0: evenly(H0, 3600, 1.0), H1: evenly(H1, 3600, 1.0)})
    tl = continuity.stream_timeline(_segs(tmp_path, "AAA/EUR"), genesis_hour=H0)
    assert tl.missing_hours == 0
    assert len(tl.pool) == len(tl.intra) + 1  # exactly one crossing joined the sample
    kinds = [k for _, k in tl.boundaries]
    assert kinds.count("crossing") == 1
    assert "edge_head" not in kinds  # H0 is the genesis hour (D5)
    assert tl.genesis_skipped is True


def test_missing_hour_books_once_and_its_excess_is_not_pooled(tmp_path):
    # H0 and H2 present, H1 absent; each hour ends/starts 10 s inside its boundary, so the
    # crossing spans 3600 + 20 s and only the 20 s excess may be booked (D4).
    write_stream(
        tmp_path,
        "AAA/EUR",
        {H0: evenly(H0, 3591, 1.0), H2: evenly(H2, 3580, 1.0, start=10.0)},
    )
    tl = continuity.stream_timeline(_segs(tmp_path, "AAA/EUR"), genesis_hour=H0)
    assert tl.missing_hours == 1
    excesses = [s for s, k in tl.boundaries if k == "excess"]
    assert len(excesses) == 1
    # H0's last row sits 10 s before its boundary, H2's first 10 s after its start: 3600 + 20.
    assert excesses[0] == pytest.approx(20.0, abs=0.01)
    assert len(tl.pool) == len(tl.intra)  # the excess never joins the threshold sample


def test_non_genesis_leading_edge_is_measured_and_trailing_edge_always_is(tmp_path):
    # Window starts at H1 while the tree's genesis is H0, so H1's head is a real measurement (D10).
    write_stream(tmp_path, "AAA/EUR", {H0: evenly(H0, 3600, 1.0), H1: evenly(H1, 100, 1.0, start=40.0)})
    tl = continuity.stream_timeline(_segs(tmp_path, "AAA/EUR")[1:], genesis_hour=H0)
    kinds = dict(map(reversed, tl.boundaries))
    assert kinds["edge_head"] == pytest.approx(40.0, abs=0.01)
    assert kinds["edge_tail"] == pytest.approx(3600.0 - 139.0, abs=0.01)
    assert tl.genesis_skipped is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: the three new tests FAIL with `AttributeError: module ... has no attribute 'stream_timeline'`.

- [ ] **Step 3: Implement `stream_timeline`**

Add `import dataclasses` to the module imports (alphabetical: after `argparse`). Insert after `MIN_POOL`:

```python
HOUR = dt.timedelta(hours=1)


@dataclasses.dataclass(frozen=True)
class StreamTimeline:
    """A stream's hours read as ONE timeline (D1), not as independent files.

    `pool` is the threshold sample: intra-row diffs plus the crossings between contiguous hours, so
    a boundary is judged by the same measured density as any other interval. `intra` books silence;
    `boundaries` books and counts truncations. A crossing therefore appears in `pool` (for the
    statistic) and in `boundaries` (for booking) but never in `intra` -- that separation is what
    keeps it from being booked twice.
    """

    pool: pl.Series
    intra: pl.Series
    boundaries: list[tuple[float, str]]
    missing_hours: int
    span_hours: int
    genesis_skipped: bool


def stream_timeline(segs: list[tuple[dt.datetime, Path]], *, genesis_hour: dt.datetime) -> StreamTimeline:
    """Build the interval model for one stream's (already `--since`-filtered, sorted) segments."""
    intra_parts: list[pl.Series] = []
    crossings: list[float] = []
    boundaries: list[tuple[float, str]] = []
    missing_hours = 0
    prev_hi: dt.datetime | None = None
    prev_hour: dt.datetime | None = None

    for h, p in segs:
        ts = pl.read_parquet(p, columns=["ts"])["ts"]
        lo, hi = ts.min(), ts.max()
        intra_parts.append(ts.diff().drop_nulls().dt.total_microseconds() / 1e6)
        if prev_hour is None:
            # D5: the genesis hour begins mid-hour by construction, so its head measures the
            # stream's birth, not a gap. Any other first-in-window hour IS measurable (D10).
            if h != genesis_hour:
                boundaries.append(((lo - h).total_seconds(), "edge_head"))
        else:
            missing = int((h - prev_hour) / HOUR) - 1
            crossing = (lo - prev_hi).total_seconds()
            if missing == 0:
                crossings.append(crossing)
                boundaries.append((crossing, "crossing"))
            else:
                # D4: the whole hours are booked at 3600 each; only the excess -- the real tail+head
                # silence bracketing the hole -- is a measurement, and it never joins the sample.
                missing_hours += missing
                boundaries.append((crossing - 3600.0 * missing, "excess"))
        prev_hi, prev_hour = hi, h

    if prev_hour is not None:
        boundaries.append(((prev_hour + HOUR - prev_hi).total_seconds(), "edge_tail"))

    intra = pl.concat(intra_parts) if intra_parts else pl.Series([], dtype=pl.Float64)
    pool = pl.concat([intra, pl.Series(crossings, dtype=pl.Float64)]) if crossings else intra
    span_hours = int((prev_hour - segs[0][0]) / HOUR) + 1 if segs else 0
    return StreamTimeline(
        pool=pool,
        intra=intra,
        boundaries=boundaries,
        missing_hours=missing_hours,
        span_hours=span_hours,
        genesis_skipped=bool(segs) and segs[0][0] == genesis_hour,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add infra/scripts/continuity.py tests/test_infra_continuity.py
git commit
```
Message: `feat(infra): read a stream's hours as one timeline, not independent files`

---

### Task 3: Wire `report()` to the timeline — booking, truncation, genesis

**Files:**
- Modify: `infra/scripts/continuity.py`
- Test: `tests/test_infra_continuity.py`
- **Migrate: `tests/test_continuity_overlay.py`** — its fixtures are 120 rows/hour (`range(0, 3600, 30)`), so under D6 every stream in that file becomes `UNMEASURED` and five of its eight tests break. They are this instrument's existing regression carriers (the PR #220 legs) and must move with the change, in this task's commit.

**Interfaces:**
- Consumes: `stream_timeline`, `StreamTimeline` (Task 2).
- Produces: `report(streams, *, since, quiet, show_exit_bar, genesis)` — the added keyword `genesis: dict[str, dt.datetime]` maps pair → earliest tree hour (D5). `main()` computes it from the unfiltered `segments()` result.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_infra_continuity.py`:

```python
def _run(root: Path, capsys, *, since=dt.datetime.min.replace(tzinfo=UTC), kind="book"):
    streams = continuity.segments(root, kind)
    genesis = {pair: min(h for h, _ in segs) for pair, segs in streams.items()}
    rc = continuity.report(streams, since=since, quiet=False, show_exit_bar=True, genesis=genesis)
    return rc, capsys.readouterr().out


def _column(out: str, prefix: str, field: str) -> str:
    """The value under `field` on the row starting with `prefix`, located via the HEADER rather than
    a fixed index -- the same helper `tests/test_continuity_overlay.py` uses, and for the same
    reason: a fixed index silently reads whatever now sits in slot N. Doubly true here, where rows
    carry a trailing ` genesis` marker that shifts every negative index."""
    lines = out.splitlines()
    header = next(line for line in lines if field in line)
    row = next(line for line in lines if line.startswith(prefix))
    return row.split()[header.split().index(field)]


def test_genesis_hour_books_no_gap_and_is_annotated(tmp_path):
    # A stream born 535 s into its hour -- exactly the T0092 shape -- must not book that head.
    hours = {H0 + dt.timedelta(hours=i): evenly(H0 + dt.timedelta(hours=i), 6000, 0.6) for i in range(1, 3)}
    hours[H0] = evenly(H0, 5100, 0.6, start=535.7)
    write_stream(tmp_path, "AAA/EUR", hours)
    tl = continuity.stream_timeline(_segs(tmp_path, "AAA/EUR"), genesis_hour=H0)
    assert not [s for s, k in tl.boundaries if k == "edge_head"]


def test_genesis_annotation_and_zero_gap_in_the_report(tmp_path, capsys):
    hours = {H0 + dt.timedelta(hours=i): evenly(H0 + dt.timedelta(hours=i), 6000, 0.6) for i in range(1, 3)}
    hours[H0] = evenly(H0, 5100, 0.6, start=535.7)
    write_stream(tmp_path, "AAA/EUR", hours)
    rc, out = _run(tmp_path, capsys)
    assert rc == 0
    assert "genesis" in out
    assert "truncated hours: 0" in out
    assert "PASS" in out


def test_identical_outage_counts_the_same_on_dense_and_slow_streams(tmp_path, capsys):
    """The false-GREEN the topic measured: a 200 s outage counted 200.1 s on a dense stream and
    0.0 s on a slow one, because the threshold self-calibrated to the outage itself.

    ONE outage among four clean hours, so the fixture sits inside D6a's safe regime -- with two
    outages in a ~11k pool the p99.99 lands ON the second one and the slow stream self-inflates by
    design, which is D6a's registered residual, not a defect this test may hide behind.
    """
    for pair, step in (("DENSE/EUR", 0.1), ("SLOW/EUR", 0.6)):
        hours = {}
        for i in range(4):
            h = H0 + dt.timedelta(hours=i)
            n = int(3000 / step)
            stamps = evenly(h, n, step)
            if i == 1:  # the single outage: a 200 s hole, then the stream resumes inside the hour
                stamps += [stamps[-1] + dt.timedelta(seconds=200.0 + j * step) for j in range(1, 30)]
            assert (stamps[-1] - h).total_seconds() < 3600, "rows must stay inside their own hour"
            hours[h] = stamps
        write_stream(tmp_path, pair, hours)
    _, out = _run(tmp_path, capsys)
    dense = float(_column(out, "DENSE/EUR", "gap_s"))
    slow = float(_column(out, "SLOW/EUR", "gap_s"))
    assert dense == pytest.approx(slow, rel=0.05)
    assert slow > 150  # the 200 s outage is counted on the slow stream, not swallowed


def test_restart_clobber_crossing_is_one_truncation_booked_once(tmp_path, capsys):
    # T0036's signature: H0 stops 300 s early, H1 starts 300 s late -> a 600 s crossing.
    write_stream(
        tmp_path,
        "AAA/EUR",
        {
            H0: evenly(H0, 5500, 0.6),
            H1: evenly(H1, 5500, 0.6, start=300.0),
            H2: evenly(H2, 5999, 0.6),
        },
    )
    _, out = _run(tmp_path, capsys)
    assert _column(out, "AAA/EUR", "trunc") == "1"
    gap = float(_column(out, "AAA/EUR", "gap_s"))
    assert gap == pytest.approx(600.0, rel=0.05)  # booked once, not as head+tail as well
    assert "truncated hours: 1" in out


def test_missing_hour_is_not_double_counted(tmp_path, capsys):
    write_stream(
        tmp_path,
        "AAA/EUR",
        {H0: evenly(H0, 5999, 0.6), H2: evenly(H2, 5980, 0.6, start=10.0)},
    )
    _, out = _run(tmp_path, capsys)
    gap = float(_column(out, "AAA/EUR", "gap_s"))
    assert gap == pytest.approx(3610.0, rel=0.02)  # 3600 for the hour + the 10 s excess, never 7200


def test_since_window_keeps_genesis_from_moving_and_books_a_late_leading_edge(tmp_path, capsys):
    """D5 + D10 through `main()`, the only path where the unfiltered-genesis defense actually runs.

    The genesis sits on the PREVIOUS day, because `--since` takes a date and cannot split a day:
    the window opens at 00:00, whose head is 400 s late -- a real restart, which must be booked and
    counted rather than inheriting genesis's free pass.

    Arithmetic, so the assertions are exact: 0.6 s spacing puts p99.99 at 0.6 and the threshold at
    max(6.0, 5.0) = 6.0; the head is 400 s (booked, 1 truncation), the crossing 2.6 s and the
    trailing tail 1.2 s (both under it, booked as nothing).
    """
    gen = dt.datetime(2026, 6, 30, 23, tzinfo=UTC)
    d1h0 = dt.datetime(2026, 7, 1, 0, tzinfo=UTC)
    d1h1 = dt.datetime(2026, 7, 1, 1, tzinfo=UTC)
    write_stream(
        tmp_path,
        "AAA/EUR",
        {
            gen: evenly(gen, 5999, 0.6),
            d1h0: evenly(d1h0, 5330, 0.6, start=400.0),
            d1h1: evenly(d1h1, 5999, 0.6),
        },
    )
    argv = ["continuity.py", str(tmp_path), "--since", "2026-07-01"]
    import sys

    old = sys.argv
    try:
        sys.argv = argv
        continuity.main()
    finally:
        sys.argv = old
    out = capsys.readouterr().out
    assert _column(out, "AAA/EUR", "trunc") == "1"
    assert float(_column(out, "AAA/EUR", "gap_s")) == pytest.approx(400.0, rel=0.05)
    assert "genesis" not in out, "a --since window must not promote H1 into the genesis free pass"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: the six new tests FAIL (`report()` has no `genesis` keyword).

- [ ] **Step 3: Rewrite `report()`'s per-stream body**

Delete `report()`'s now-stranded local `HOUR = dt.timedelta(hours=1)` (Task 2 moved it to module level; ruff here selects only `I`, so the gate will not flag it). Then replace the whole `for pair, segs in sorted(streams.items()):` body (from `segs = [(h, p) for h, p in segs if h >= since]` through the `if not quiet:` print) with:

```python
    for pair, segs in sorted(streams.items()):
        segs = [(h, p) for h, p in segs if h >= since]
        if not segs:
            continue
        segs.sort()
        tl = stream_timeline(segs, genesis_hour=genesis[pair])

        gap = tl.missing_hours * 3600.0
        n = len(tl.pool)
        # D6: below the bound the p99.99 IS the maximum, so the threshold would be 10x the worst
        # outage. Report the stream as unmeasurable rather than score it against a blind number.
        measured = n >= MIN_POOL
        thresh = max(float(tl.pool.quantile(0.9999) or 0) * 10, 5.0) if measured else 0.0
        trunc = 0
        if measured:
            gap += float(tl.intra.filter(tl.intra > thresh).sum() or 0.0)
            for secs, _kind in tl.boundaries:
                if secs > thresh:
                    gap += secs
                    trunc += 1

        covered = tl.span_hours * 3600.0
        if not measured:
            unmeasured.append(pair)
            if not quiet:
                print(f"{pair:<10} {tl.span_hours:>6} {tl.missing_hours:>8} {'-':>6} {n:>9} {'UNMEASURED':>12} {'':>10} {covered:>11.0f} {'':>8}")
            continue

        pct = 100.0 * gap / covered if covered else 0.0
        worst = max(worst, pct)
        totals.append((pair, tl.span_hours, tl.missing_hours, trunc, gap, covered, pct))
        if not quiet:
            mark = " genesis" if tl.genesis_skipped else ""
            print(
                f"{pair:<10} {tl.span_hours:>6} {tl.missing_hours:>8} {trunc:>6} {n:>9} {thresh:>12.1f} {gap:>10.1f} {covered:>11.0f} {pct:>7.4f}%{mark}"
            )
```

Add `unmeasured: list[str] = []` beside `totals = []`, and change the header/rule lines to:

```python
    print(f"{'pair':<10} {'hours':>6} {'missing':>8} {'trunc':>6} {'n':>9} {'thresh_s':>12} {'gap_s':>10} {'covered_s':>11} {'gap%':>8}")
    print("-" * 88)
```

(and the two later `print("-" * 75)` become `print("-" * 88)`; the TOTAL row's format string gains a matching `{'':>9}` column for `n`.)

Update the signature and docstring:

```python
def report(
    streams: dict[str, list[tuple[dt.datetime, Path]]],
    *,
    since: dt.datetime,
    quiet: bool,
    show_exit_bar: bool,
    genesis: dict[str, dt.datetime],
) -> int:
```

Docstring addition (append to the existing one): `genesis` maps each pair to its earliest hour in the UNFILTERED tree, so a `--since` window cannot promote a later hour into D5's free pass.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: the six new Task-3 tests pass alongside Tasks 1-2's. Exact totals are not asserted here -- count what the run reports.

- [ ] **Step 5: Update the two `report()` call sites in `main()`**

```python
def main() -> int:
    a = build_parser().parse_args()

    since = dt.datetime.fromisoformat(a.since).replace(tzinfo=dt.UTC) if a.since else dt.datetime.min.replace(tzinfo=dt.UTC)
    raw = segments(a.root, a.kind)
    # D5: genesis comes from the UNFILTERED tree -- a --since window must not promote a later hour
    # into the genesis free pass.
    genesis = {pair: min(h for h, _ in segs) for pair, segs in raw.items()}
    rc = report(raw, since=since, quiet=a.quiet, show_exit_bar=True, genesis=genesis)

    if a.overlay is not None:
        print()
        print(
            f"=== CANONICAL VIEW (reconciled-first, healed from {a.overlay}) -- informational only, NOT the exit-bar instrument ==="
        )
        canonical = _canonical_streams(a.root, a.overlay, a.kind)
        report(
            canonical,
            since=since,
            quiet=a.quiet,
            show_exit_bar=False,
            genesis={pair: min(h for h, _ in segs) for pair, segs in canonical.items()},
        )
    return rc
```

- [ ] **Step 6: Migrate `tests/test_continuity_overlay.py`'s fixtures — preserving each test's property**

Run: `uv run pytest tests/test_continuity_overlay.py -v`
Expected BEFORE the migration: 5 failures — `test_default_invocation_has_no_canonical_section`, `test_overlay_mode_prints_both_reports`, `test_the_table_prints_the_threshold_that_produced_each_gap` (`float("UNMEASURED")` → ValueError), `test_the_total_row_never_fabricates_a_threshold` (StopIteration — no TOTAL row), `test_quiet_mode_drops_the_per_pair_rows_and_keeps_the_total`.

That failure list is *correct behavior*, not a regression: 120-row streams are exactly what D6 refuses. Migrate each fixture to clear `MIN_POOL` **while keeping the property the test was written to prove**:

- The `_write_hour(..., stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 30)])` calls become dense enough streams. Keep the *two different densities* wherever a test uses them — `test_the_table_prints_the_threshold_that_produced_each_gap` exists to show two streams of the same hour deriving different thresholds, and it must still do so. Working shapes: 1 s spacing over 2 h (5,999 intervals → thresh 10.0) beside 2 s over 3 h (5,399 intervals → thresh 20.0); adjust the asserted threshold values to whatever those fixtures actually derive, verified by running.
- `test_empty_window_prints_no_exit_bar` and the empty-tree test keep `rc == 1` and no verdict — D6 does not touch them.
- Do not delete a test to make the suite green. If a property genuinely cannot survive D6, **stop and report** rather than dropping it.

Run: `uv run pytest tests/test_continuity_overlay.py tests/test_infra_continuity.py -v`
Expected AFTER: all pass, with no test removed (`git diff --stat` shows edits, not deletions).

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q`
Expected: the full suite green.

- [ ] **Step 8: Commit**

```bash
uv run pre-commit run -a
git add infra/scripts/continuity.py tests/test_infra_continuity.py tests/test_continuity_overlay.py
git commit
```
Message: `feat(infra): book and count truncation from measured density, not fixed constants`

---

### Task 4: `UNMEASURED` fails the bar

**Files:**
- Modify: `infra/scripts/continuity.py`
- Test: `tests/test_infra_continuity.py`

**Interfaces:**
- Consumes: `unmeasured` (Task 3).
- Produces: the verdict line `EXIT BAR (<0.1% gap time): *** FAIL *** (unmeasured streams: N)` when any stream is unmeasured.

- [ ] **Step 1: Write the failing tests**

```python
def test_small_sample_is_unmeasured_and_fails_the_bar(tmp_path, capsys):
    # 200 rows -> 199 intra intervals, far under MIN_POOL: a clean-looking stream that cannot be
    # self-calibrated must never bank a PASS.
    write_stream(tmp_path, "THIN/EUR", {H0: evenly(H0, 200, 18.0), H1: evenly(H1, 200, 18.0)})
    rc, out = _run(tmp_path, capsys)
    assert "UNMEASURED" in out
    assert "FAIL (unmeasured streams: 1)" in out
    # Every stream unmeasured is still "we read something and judged it" -- rc 0 with a FAIL
    # verdict. Only an empty tree or an empty window returns 1 with NO verdict (D6).
    assert rc == 0
    assert "TOTAL" not in out, "no measured stream may produce a TOTAL row"


def test_unmeasured_stream_is_excluded_from_the_total_row(tmp_path, capsys):
    write_stream(tmp_path, "THIN/EUR", {H0: evenly(H0, 200, 18.0)})
    write_stream(tmp_path, "DENSE/EUR", {H0: evenly(H0, 5999, 0.6), H1: evenly(H1, 5999, 0.6)})
    _, out = _run(tmp_path, capsys)
    # covered_s on TOTAL counts only the measured stream -- read via the header, never a fixed
    # index: the DENSE row carries a trailing ` genesis` marker that shifts every negative index.
    assert float(_column(out, "TOTAL", "covered_s")) == pytest.approx(float(_column(out, "DENSE/EUR", "covered_s")))
    assert "FAIL (unmeasured streams: 1)" in out


def test_all_streams_measured_keeps_the_plain_verdict(tmp_path, capsys):
    write_stream(tmp_path, "DENSE/EUR", {H0: evenly(H0, 5999, 0.6), H1: evenly(H1, 5999, 0.6)})
    _, out = _run(tmp_path, capsys)
    assert "unmeasured" not in out
    assert "EXIT BAR (<0.1% gap time): PASS" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: the three new tests FAIL (no `unmeasured streams` text).

- [ ] **Step 3: Implement the verdict**

Replace the `if show_exit_bar:` block:

```python
    if show_exit_bar:
        # D6: an unmeasurable stream must not be silently skipped -- a bar that ignores what it
        # could not measure is the same false-green the instrument exists to prevent.
        if unmeasured:
            print(f"  EXIT BAR (<0.1% gap time): *** FAIL *** (unmeasured streams: {len(unmeasured)})")
        else:
            print("  EXIT BAR (<0.1% gap time): " + ("PASS" if worst < 0.1 else "*** FAIL ***"))
```

Also, when `totals` is empty but `unmeasured` is not, the existing `no segments in the requested window` early return would hide them **and skip the verdict entirely** — the exact false-green D6 forbids. The all-unmeasured case must still print its FAIL:

```python
    if not totals:
        # Nothing measurable. Two different situations, and only one of them may stay silent:
        # streams existed but none could be self-calibrated (D6 -- say so, and FAIL), versus no
        # segments at all (nothing was measured, so nothing may bank OR fail a verdict).
        if unmeasured:
            print(f"no measurable segments: {len(unmeasured)} stream(s) under the {MIN_POOL}-interval bound")
            if show_exit_bar:
                print(f"  EXIT BAR (<0.1% gap time): *** FAIL *** (unmeasured streams: {len(unmeasured)})")
            return 0
        print("no segments in the requested window")
        return 1
```

Note the return value: `0` when streams were read but none measurable (the verdict carries the judgement), `1` only when there was nothing to read at all — matching `test_empty_window_prints_no_exit_bar`'s existing contract.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_continuity.py -v`
Expected: the three new tests pass alongside every earlier one.

- [ ] **Step 5: Update the module docstring**

In the `Three kinds of gap` block, replace item 2 and 3's wording to match the model:

```
  1. MISSING hour   -- no segment at all              -> 3600 s
  2. BOUNDARY silence -- the interval spanning an hour boundary (last row of H-1 -> first row
                        of H), judged by the same derived threshold as any other interval;
                        this is the T0036 restart-clobber signature, and it is what `trunc` counts
  3. INTRA-hour silence   -- consecutive rows further apart than a threshold derived
                              from the data itself (not guessed)

A stream with fewer than MIN_POOL intervals is reported UNMEASURED and FAILS the exit bar: below
that bound the derived threshold degenerates to 10x the worst outage (see MIN_POOL).
```

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run -a
git add infra/scripts/continuity.py tests/test_infra_continuity.py
git commit
```
Message: `feat(infra): a stream too small to self-calibrate is UNMEASURED and fails the bar`

---

### Task 5: Window the daily verify-replay

**Files:**
- Modify: `infra/ansible/roles/ops/templates/verify-replay.sh.j2`
- Create: `tests/test_infra_verify_replay_template.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing later tasks consume.

- [ ] **Step 1: Write the failing test**

```python
"""Guard: the daily verify-replay must run WINDOWED (spec 00076 D7).

Unwindowed, one historical bad hour exits 1 every day forever behind a CRITICAL alert -- the
`ops_verify_replay_exit_code` rule -- which is how an operator learns to ignore it. The CLI has
had `--since` all along; only this runner omitted it.

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's Jinja defaults, matching
`test_infra_archive_pull_template.py`.
"""

import shutil
import subprocess
from pathlib import Path

import jinja2

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/ops/templates/verify-replay.sh.j2"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

CONTEXT = {
    "ops_textfile_dir": "/var/lib/zcrypto-ops/textfile",
    "ops_verify_replay_healthcheck_url": "https://hc-ping.com/deadbeef",
    "ops_nas_mount": "/mnt/zhao-crypto",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_uid": "1001",
    "ops_gid": "1001",
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "0" * 64,
    "ops_capture_subdir": "capture-segments",
    "ops_reconciled_subdir": "capture-reconciled",
    "ops_verify_replay_window_days": 7,
}


def _render() -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**CONTEXT)


def test_renders_valid_bash(tmp_path):
    script = tmp_path / "verify-replay.sh"
    script.write_text(_render())
    assert subprocess.run([shutil.which("bash"), "-n", str(script)], capture_output=True).returncode == 0


def test_the_replay_is_windowed():
    out = _render()
    assert "--since" in out, "an unwindowed daily replay pages forever on one historical bad hour"
    # The window is computed at run time, not baked at render time: a rendered date would freeze
    # on the day of the converge and silently narrow to nothing.
    assert "date -u -d" in out or "date -u --date" in out
    assert "7 days ago" in out


def test_window_days_is_configurable_and_reaches_the_command():
    out = _ENV.from_string(TEMPLATE.read_text()).render(**{**CONTEXT, "ops_verify_replay_window_days": 3})
    assert "3 days ago" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_infra_verify_replay_template.py -v`
Expected: `test_renders_valid_bash` passes; the two `--since` tests FAIL.

- [ ] **Step 3: Edit the template**

After the `URL=` line (line 16), add:

```bash
# spec 00076 D7: the replay is WINDOWED. Unwindowed, a single historical bad hour exits 1 every
# day forever behind the CRITICAL exit-code alert -- training an operator to ignore the one alert
# that means the archive stopped replaying. The window is computed per run, never rendered at
# converge time (a baked date freezes on the day of the converge and narrows to nothing). Old hours
# are not left unguarded: the hourly archive-pull hash-verifies every segment against its manifest.
SINCE=$(date -u -d '{{ ops_verify_replay_window_days }} days ago' +%F)
```

And change the command's last line (33) to:

```bash
    archive verify-replay "/nas/{{ ops_capture_subdir }}" "/data/{{ ops_reconciled_subdir }}" --since "$SINCE"
```

- [ ] **Step 4: Add the role default**

In `infra/ansible/roles/ops/defaults/main.yml`, beside the other verify-replay vars:

```yaml
# spec 00076 D7 -- the daily replay's window. 7 days matches the T0003 exit bar's own framing and
# bounds a permanent hole to a week of paging instead of forever; a hole found this way is
# registered durably when triaged, because an alert that ages out is not a record.
ops_verify_replay_window_days: 7
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_verify_replay_template.py -v`
Expected: 3 passed.

- [ ] **Step 6: Prove the defect the guard names**

Construct it rather than trust the test (`agent-ops.md`). In a scratch dir, build a tiny canonical tree with one un-replayable hour, then:

Run: `uv run zcrypto archive verify-replay <primary> <reconciled>` — expect a non-zero exit naming the bad hour.
Run: `uv run zcrypto archive verify-replay <primary> <reconciled> --since <date after the bad hour>` — expect exit 0.

Record both outputs in the commit message. If the second still exits non-zero, **stop and report** — `--since` does not do what D7 assumes.

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run -a
git add infra/ansible/roles/ops/templates/verify-replay.sh.j2 infra/ansible/roles/ops/defaults/main.yml tests/test_infra_verify_replay_template.py
git commit
```
Message: `fix(infra): window the daily verify-replay so one bad hour cannot page forever`

---

### Task 6: Real-data acceptance — the load-bearing check

**Files:** none changed (measurement only).

**Interfaces:**
- Consumes: the finished instrument (Tasks 1–4).
- Produces: the before/after numbers quoted in the closeout and the PR body.

- [ ] **Step 1: Capture the BEFORE numbers from the merge-base**

```bash
SCRATCH=<the session scratchpad dir named in your dispatch prompt>   # never /tmp
git stash list  # expect empty
git worktree add "$SCRATCH/continuity-before" $(git merge-base HEAD develop)
uv run python "$SCRATCH/continuity-before/infra/scripts/continuity.py" /mnt/zhao-crypto/capture-segments > "$SCRATCH/before.txt"
```

Read `$SCRATCH/before.txt` and record: ETH/BTC's `gap%`, the TOTAL row, the truncated-hours count, the verdict.

- [ ] **Step 2: Capture the AFTER numbers**

```bash
uv run python infra/scripts/continuity.py /mnt/zhao-crypto/capture-segments > "$SCRATCH/after.txt"
```

- [ ] **Step 3: Assert the four acceptance criteria** (spec 00076 *Verification*)

1. ETH/BTC moves from ~0.13 % FAIL to ~0.04 % PASS.
2. SOL/BTC's genesis (535.3 s) likewise stops being booked.
3. The EUR streams' 7 genuine truncations survive as truncations (count may re-attribute across the two streams — the total must not drop to 0).
4. No stream's real counted outages disappear: the ~210 s events (BTC-quoted) and ~1550 s events (EUR) remain in the booked gap.

If any criterion fails, **stop and report with both files** — do not adjust the instrument to make the numbers agree.

- [ ] **Step 4: Clean up the worktree**

```bash
git worktree remove "$SCRATCH/continuity-before"
```

- [ ] **Step 5: Commit the record**

No code changes; the numbers land in the closeout (Task 7). If Step 3 revealed anything requiring a fix, that fix is its own task with its own tests.

---

### Task 7: Closeout

**Files:**
- Modify: `docs/open-topics/T0097-archive-verification-instruments-have-measurement-defects.md`
- Modify: `docs/open-topics/README.md`
- Modify: `.claude/rules/capture-deploys.md` (**protected — the owner signs off on this edit at closeout**)
- Modify: `docs/iterations-history-phase6.md`
- Modify: `docs/memo.local.md` (Edit/Write tools only, read before and read back after — never a shell heredoc)

- [ ] **Step 1: Resolve and archive T0097**

All three legs are now addressed: the threshold is fitted (Task 3), the head/tail test is boundary-spanning (Tasks 2–3), the verify-replay is windowed (Task 5). Its one surviving residual — D6a's repeat-outage regime — was **split into [[T0112]] before this archive** (already registered and indexed on this branch), so the topic carries no live deferred sub-item, per `.claude/rules/open-topics.md`. Per `.claude/skills/topic-ops/SKILL.md`: flip `status: partial` → `status: resolved`, **delete the `ripe_when:` key**, add a `## Resolution` section naming spec 00076, this plan, the commits, the acceptance numbers and the T0112 split, then `git mv` the file into `docs/open-topics/archive/`.

- [ ] **Step 2: Move its index bullet**

In `docs/open-topics/README.md`, move the T0097 bullet from `### Partially done` to the end of the same category's `### Resolved`, and repoint the link at `archive/`.

- [ ] **Step 3: Retire the genesis carve-out from `capture-deploys.md`** *(protected — present the exact diff and take the owner's word before writing)*

The verify-by-outcome bullet's genesis exception exists because the instrument had no carve-out. It now does. Replace the `**Exception — a NEW stream's genesis hour** …` sentence with: `a new stream's genesis hour is annotated and not booked, so it no longer reads as a truncation.`

- [ ] **Step 4: Append the iterations-history entry** (`.claude/skills/iteration-closeout/SKILL.md` — phase 6)

One bullet per: the fit and what it refuted; the timeline model; UNMEASURED; the windowed replay; the acceptance numbers.

- [ ] **Step 5: Update the memo**

Move the T0097 queue item to `DONE ITEMS` with citations (PR, commits, the acceptance numbers), per the *done* procedure in `.claude/skills/zcrypto-grooming/references/memo-protocol.md`.

- [ ] **Step 6: Commit** (two commits — `docs` kind and `claude` kind never share one)

```bash
uv run pre-commit run -a
git add docs/open-topics/... docs/iterations-history-phase6.md
git commit   # docs(ops): iter closeout -- the verification instruments, re-fitted (T0097 resolved)
git add .claude/rules/capture-deploys.md
git commit   # claude(rules): the genesis carve-out is retired -- the instrument annotates it now
```

- [ ] **Step 7: Attended deploy** *(the owner runs it; do not attempt from a subagent)*

The template change reaches the fleet only via an ops converge: `--limit zcrypto-ops`, `--check --diff` first, `daemon.json` unchanged, `ops_alloy_digest` omitted (Alloy is not the subject), and the currently-running `ops_image_digest` passed. Verify by outcome at the next daily tick: `ops_verify_replay_exit_code` 0 with `--since` visible in the unit's resolved `argv[]`.

## Self-review

**Spec coverage.** D1 → Task 2. D2 → Task 3 Step 3. D3 → Task 3 (trunc from boundaries). D4 → Task 2 (excess, not pooled) + Task 3 (booked once). D5 → Task 2 (genesis head skipped) + Task 3 (annotation, unfiltered genesis map). D6 → Task 1 (bound measured) + Tasks 3–4 (UNMEASURED, TOTAL exclusion, verdict). D7 → Task 5. D8 → Task 5 Step 3's comment (no sweep built — the absence is the decision). D9 → nothing built, by design; recorded in the spec. D10 → Task 2 (edges) + Task 3 (booked above threshold).

**Placeholders:** none — every step carries its code or its exact command.

**Type consistency:** `stream_timeline(segs, *, genesis_hour)` returns `StreamTimeline` in Task 2 and is called with the same signature in Task 3; `report(..., genesis=...)` is added in Task 3 and both call sites are updated in the same task.
