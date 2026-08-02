"""T0097 / spec 00076: the continuity instrument's measurement semantics.

Every test here constructs the defect it names and asserts the instrument reacts -- reading the
assertion is not verification (`.claude/rules/agent-ops.md`).
"""

import datetime as dt
import importlib.util
import random
import re
import sys
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
    # Registered in sys.modules before exec: continuity.py's `from __future__ import annotations`
    # makes dataclass field annotations strings, and `dataclasses` resolves those against
    # `sys.modules[cls.__module__]` -- unregistered, that lookup is None and StreamTimeline's
    # decoration crashes.
    spec = importlib.util.spec_from_file_location("continuity_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
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


H0 = dt.datetime(2026, 7, 1, 10, tzinfo=UTC)
H1 = H0 + dt.timedelta(hours=1)
H2 = H0 + dt.timedelta(hours=2)


def _segs(root: Path, pair: str, kind: str = "book"):
    return sorted(continuity.segments(root, kind)[pair])


def test_contiguous_crossing_is_pooled_and_classified(tmp_path):
    # H0 ends 2 s before its boundary, so the crossing is 2 s -- distinct from the uniform 1 s
    # intra-hour spacing. `len(pool) == len(intra) + 1` is invariant under double-booking (a
    # crossing wrongly pooled into `intra` too moves both sides of the relation together), so the
    # property is pinned directly instead: intra's exact length, and the crossing's value absent
    # from it.
    write_stream(tmp_path, "AAA/EUR", {H0: evenly(H0, 3599, 1.0), H1: evenly(H1, 3600, 1.0)})
    tl = continuity.stream_timeline(_segs(tmp_path, "AAA/EUR"), genesis_hour=H0)
    assert tl.missing_hours == 0
    assert len(tl.intra) == 7197  # 3598 (H0) + 3599 (H1) intra-row diffs, crossing excluded
    assert 2.0 not in tl.intra  # the 2 s crossing must never land in the silence-booking series
    assert len(tl.pool) == 7198  # intra's 7197 plus the crossing, exactly once
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
    # 3 hours span H0..H2 (H1 missing) -- distinct from len(segs) == 2, so a mutant that drops the
    # `+ 1` or substitutes `len(segs)` for the real span is caught rather than passing by accident.
    assert tl.span_hours == 3


def test_non_genesis_leading_edge_is_measured_and_trailing_edge_always_is(tmp_path):
    # Window starts at H1 while the tree's genesis is H0, so H1's head is a real measurement (D10).
    write_stream(tmp_path, "AAA/EUR", {H0: evenly(H0, 3600, 1.0), H1: evenly(H1, 100, 1.0, start=40.0)})
    tl = continuity.stream_timeline(_segs(tmp_path, "AAA/EUR")[1:], genesis_hour=H0)
    kinds = dict(map(reversed, tl.boundaries))
    assert kinds["edge_head"] == pytest.approx(40.0, abs=0.01)
    assert kinds["edge_tail"] == pytest.approx(3600.0 - 139.0, abs=0.01)
    assert tl.genesis_skipped is False


def _run(root: Path, capsys, *, since=dt.datetime.min.replace(tzinfo=UTC), kind="book"):
    streams = continuity.segments(root, kind)
    genesis = {pair: min(h for h, _ in segs) for pair, segs in streams.items()}
    rc = continuity.report(streams, since=since, quiet=False, show_exit_bar=True, genesis=genesis)
    return rc, capsys.readouterr().out


def _column(out: str, prefix: str, field: str) -> str:
    """The value under `field` on the row starting with `prefix`, located by CHARACTER RANGE from the
    header -- the same helper `tests/test_continuity_overlay.py` uses, and for the same reason:
    `str.split()` collapses blank cells (an UNMEASURED row's blank thresh_s/gap_s/gap% slots, the
    TOTAL row's blank n/thresh_s slots), silently shifting every field after the first blank one onto
    the wrong index instead of reading it as blank. Every column is right-justified to a fixed width
    behind a single-space separator, so a field's cell always ENDS at the same character offset as its
    header token, whether the cell holds a value or is blank; the cell STARTS just after the preceding
    header token ends. Doubly load-bearing here, where rows also carry a trailing ` genesis` marker
    that would shift every negative index too.

    The header row is located by its `pair` prefix, NOT by "the first line containing `field`": the
    column names are ordinary words that also occur in the post-table reason notes ("... whose
    spacing **tail** steepens ..."), and a `field in line` lookup silently falls through to a note
    once the column it names is gone -- measured, `_column(out, "TOTAL", "tail")` then returns `''`
    and a blank-cell assertion PASSES against a table with no `tail` column at all."""
    lines = out.splitlines()
    header = next(line for line in lines if line.startswith("pair"))
    row = next(line for line in lines if line.startswith(prefix))
    tokens = list(re.finditer(r"\S+", header))
    idx = next(i for i, m in enumerate(tokens) if m.group() == field)
    lo = tokens[idx - 1].end() + 1 if idx > 0 else 0
    hi = tokens[idx].end()
    return row[lo:hi].strip()


def test_column_reads_blank_cells_on_unmeasured_and_total_rows(tmp_path, capsys):
    """`_column` is now load-bearing for both continuity test files (T0097 Finding 3): a
    `str.split()`-based version misreads an UNMEASURED row's blank `gap_s` cell as its NEXT
    non-blank cell's value, and raises `IndexError` on the TOTAL row (which has two blank cells of
    its own). AAA/EUR is measured (3 full hours, pool well past MIN_POOL); THIN/EUR is a single
    sparse hour (120 rows), reported UNMEASURED and excluded from the TOTAL row's totals.
    """
    hours = {H0 + dt.timedelta(hours=i): evenly(H0 + dt.timedelta(hours=i), 6000, 0.6) for i in range(3)}
    write_stream(tmp_path, "AAA/EUR", hours)
    write_stream(tmp_path, "THIN/EUR", {H0: evenly(H0, 120, 30.0)})
    _, out = _run(tmp_path, capsys)
    assert _column(out, "THIN/EUR", "gap_s") == ""
    assert _column(out, "THIN/EUR", "thresh_s") == "UNMEASURED"
    assert float(_column(out, "TOTAL", "covered_s")) == pytest.approx(3 * 3600.0)  # THIN/EUR excluded


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
    """For MEASURED streams (n >= MIN_POOL), the booked outage is density-independent: the same 200 s
    hole is counted the same whether the surrounding stream samples at 0.1 s or 0.6 s spacing. This is
    a characterization test, not a regression carrier for the thin-stream false-GREEN the topic
    originally measured (a self-calibrating threshold that swallows the outage on a sparse stream) --
    that defect class is closed by refusal, not by this test's booking: any stream sparse enough to
    exhibit it is exactly a stream D6 declares UNMEASURED (see Task 4's UNMEASURED -> FAIL). Confirmed
    against the pre-Task-3 `report()` too: this same fixture already passes there (DENSE 200.1 /
    SLOW 201.0, identical to the new code), so both assertions hold under either measurement basis.

    ONE outage among four clean hours, so the fixture sits inside D6a's safe regime -- with two
    outages in a ~11k pool the p99.99 lands ON the second one and the slow stream self-inflates by
    design, which is D6a's registered residual, not a defect this test may hide behind.

    Fixture arithmetic: `n = int(3600 / step)` packs each hour to (just under) full -- so the
    inter-hour crossings stay at ~1 step, not a real gap. Hour 1's outage is carved OUT of that full
    hour (drop the offsets in [3000, 3200)) rather than appended after a truncated prefix: appending
    after only `3000 / step` rows left a second, unbooked ~600 s hole at every hour's tail (it swamped
    the intended single 200 s signal -- measured, that shape produced gap_s 2397.6 (DENSE) vs 0.0
    (SLOW), the opposite of what this test exists to prove). Carving the window out of a full hour
    leaves exactly one ~(200 + step) s hole and nothing else anomalous.
    """
    for pair, step in (("DENSE/EUR", 0.1), ("SLOW/EUR", 0.6)):
        hours = {}
        for i in range(4):
            h = H0 + dt.timedelta(hours=i)
            n = int(3600 / step)
            offsets = [j * step for j in range(n)]
            if i == 1:  # the single outage: drop the 200 s window from an otherwise full hour
                offsets = [o for o in offsets if not (3000.0 <= o < 3200.0)]
            stamps = [h + dt.timedelta(seconds=o) for o in offsets]
            assert (stamps[-1] - h).total_seconds() < 3600, "rows must stay inside their own hour"
            hours[h] = stamps
        write_stream(tmp_path, pair, hours)
    _, out = _run(tmp_path, capsys)
    dense = float(_column(out, "DENSE/EUR", "gap_s"))
    slow = float(_column(out, "SLOW/EUR", "gap_s"))
    assert dense == pytest.approx(slow, rel=0.05)
    assert slow > 150  # the 200 s outage is counted on the slow stream, not swallowed


def test_trunc_counts_only_boundary_truncations_not_intra_silence(tmp_path, capsys):
    """`trunc` is the T0036 restart-clobber counter that drives the operator-facing
    `truncated hours: N -- MUST be 0` line -- it must count only BOUNDARY truncations
    (edge_head/edge_tail/crossing/excess), never intra-hour silence, or ordinary silence would be
    reported as restart damage. H1 carries a genuine 50 s intra-hour outage above threshold (booked
    into `gap_s`); H0/H2 are full hours and every boundary (2 crossings + 1 edge_tail) stays at the
    ~0.6 s step, far under the derived 6.0 s threshold -- so `trunc` must stay at its boundary-only
    value (0) while `gap_s` still reflects the outage.
    """

    def full_hour(h: dt.datetime, step: float) -> list[dt.datetime]:
        n = int(3600 / step)
        return [h + dt.timedelta(seconds=j * step) for j in range(n)]

    def full_hour_with_gap(h: dt.datetime, step: float, gap_start: float, gap_len: float) -> list[dt.datetime]:
        n = int(3600 / step)
        offsets = [j * step for j in range(n) if not (gap_start <= j * step < gap_start + gap_len)]
        return [h + dt.timedelta(seconds=o) for o in offsets]

    write_stream(
        tmp_path,
        "AAA/EUR",
        {
            H0: full_hour(H0, 0.6),
            H1: full_hour_with_gap(H1, 0.6, 1800.0, 50.0),
            H2: full_hour(H2, 0.6),
        },
    )
    _, out = _run(tmp_path, capsys)
    assert _column(out, "AAA/EUR", "trunc") == "0"
    assert float(_column(out, "AAA/EUR", "gap_s")) == pytest.approx(51.0, rel=0.05)


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


def test_small_sample_is_unmeasured_and_fails_the_bar(tmp_path, capsys):
    # 200 rows -> 199 intra intervals, far under MIN_POOL: a clean-looking stream that cannot be
    # self-calibrated must never bank a PASS.
    write_stream(tmp_path, "THIN/EUR", {H0: evenly(H0, 200, 18.0), H1: evenly(H1, 200, 18.0)})
    rc, out = _run(tmp_path, capsys)
    assert "UNMEASURED" in out
    assert "*** FAIL *** (unmeasured streams: 1)" in out
    # D4's attribution, pinned in BOTH directions: the under-bound reason is NAMED, and it is not
    # misattributed as a steepened tail. A mutant that drops the `n >= MIN_POOL` guard on the
    # steepened list books every under-bound refusal as a tail refusal, and nothing else in this
    # file notices -- the steepened-tail tests only assert the under-bound line is ABSENT.
    assert f"under the {continuity.MIN_POOL}-interval bound" in out
    assert "steepens more than" not in out
    # Every stream unmeasured is still "we read something and judged it" -- rc 0 with a FAIL
    # verdict. Only an empty tree or an empty window returns 1 with NO verdict line (D6).
    assert rc == 0
    assert "TOTAL" not in out, "no measured stream may produce a TOTAL row"


def test_unmeasured_stream_is_excluded_from_the_total_row(tmp_path, capsys):
    write_stream(tmp_path, "THIN/EUR", {H0: evenly(H0, 200, 18.0)})
    write_stream(tmp_path, "DENSE/EUR", {H0: evenly(H0, 5999, 0.6), H1: evenly(H1, 5999, 0.6)})
    _, out = _run(tmp_path, capsys)
    # covered_s on TOTAL counts only the measured stream -- read via the header, never a fixed
    # index: the DENSE row carries a trailing ` genesis` marker that shifts every negative index.
    assert float(_column(out, "TOTAL", "covered_s")) == pytest.approx(float(_column(out, "DENSE/EUR", "covered_s")))
    assert "*** FAIL *** (unmeasured streams: 1)" in out


def test_all_streams_measured_keeps_the_plain_verdict(tmp_path, capsys):
    write_stream(tmp_path, "DENSE/EUR", {H0: evenly(H0, 5999, 0.6), H1: evenly(H1, 5999, 0.6)})
    _, out = _run(tmp_path, capsys)
    assert "unmeasured" not in out
    assert "EXIT BAR (<0.1% gap time): PASS" in out


def test_the_thin_stream_false_green_is_now_a_refusal_not_a_zero(tmp_path, capsys):
    """T0097's headline measured finding: an identical outage counted 200.1 s on a dense stream and
    0.0 s on a thin one, because the self-calibrating threshold inflated to ~10x the outage itself
    and swallowed it whole. Reconstructed end-to-end against the OLD (pre-T0097, commit 6f614957)
    `report()` -- the version that already prints `thresh_s` and survives an empty window, but has
    neither `StreamTimeline` nor `MIN_POOL` -- via `git show 6f614957:infra/scripts/continuity.py`:

    A THIN/EUR stream, 3 s spacing, 2 hours, with a genuine 204 s outage carved out of hour 0 (the
    same carve technique `test_trunc_counts_only_boundary_truncations_not_intra_silence` uses:
    drop the offsets in [1800.0, 2000.0) from an otherwise full hour). Measured directly against the
    OLD module: 1,133 rows survive in hour 0 (1,132 intra diffs, one of them the 204 s outage),
    2,332 pooled diffs total across both hours. With nearest interpolation, `quantile(0.9999)` on
    that small a pool lands ON the outage itself, so `thresh_s` derives to 2040.0 (10x 204) --
    comfortably above the 204 s hole, which vanishes from the count entirely. All that's left is
    each hour's ~2 s tail remainder (1,200 samples/hour at 3 s spacing don't reach exactly to the
    hour boundary): `gap_s = 4.0`, `pct = 0.0556%`, `EXIT BAR: PASS`. The OLD instrument reports a
    stream with a genuine 204 s outage as clean.

    Under the NEW instrument, the SAME fixture pools to 2,332 intervals -- under MIN_POOL (5,002) --
    so it is never scored against that self-calibrated number at all: UNMEASURED, and the exit bar
    FAILS rather than banking the 0.0556% the old code would have reported. This is the assertion
    that closes T0097's original defect: a stream sparse enough to self-calibrate into blindness is
    exactly a stream this instrument now refuses to score.
    """

    def full_hour(h: dt.datetime, step: float) -> list[dt.datetime]:
        n = int(3600 / step)
        return [h + dt.timedelta(seconds=j * step) for j in range(n)]

    def full_hour_with_gap(h: dt.datetime, step: float, gap_start: float, gap_len: float) -> list[dt.datetime]:
        n = int(3600 / step)
        offsets = [j * step for j in range(n) if not (gap_start <= j * step < gap_start + gap_len)]
        return [h + dt.timedelta(seconds=o) for o in offsets]

    write_stream(
        tmp_path,
        "THIN/EUR",
        {H0: full_hour_with_gap(H0, 3.0, 1800.0, 200.0), H1: full_hour(H1, 3.0)},
    )
    rc, out = _run(tmp_path, capsys)
    assert _column(out, "THIN/EUR", "thresh_s") == "UNMEASURED"
    assert "*** FAIL *** (unmeasured streams: 1)" in out
    assert rc == 0
    assert "TOTAL" not in out, "no measured stream may produce a TOTAL row -- not even a comfortable one"


# --- T0112 / spec 00079: the tail-steepness gate -------------------------------------------------
#
# MIN_POOL closes the k=1 case only. At k >= 2 same-scale outages the pool clears the bound, p99.99
# lands ON an outage, and the derived threshold inflates to 10x it -- the instrument then books
# 0.0 s over genuinely missing data, which is the false GREEN the whole script exists to prevent.


def _bursty(n: int, rng: random.Random) -> list[float]:
    """T0097's measured spacing shape: same-millisecond bursts, so the pool's median is 0.

    This is the shape that already refuted any median-based statistic, and it is what makes the
    RATIO_FLOOR_S denominator floor necessary rather than cosmetic.
    """
    out: list[float] = []
    while len(out) < n:
        b = rng.randint(1, 12)
        out.extend([0.0] * (b - 1))
        out.append(rng.expovariate(1 / 0.35))
    return out[:n]


def _bimodal(n: int, rng: random.Random) -> list[float]:
    """A legitimately two-scale venue: 90 % of updates ~0.05 s apart, 10 % ~2 s apart."""
    return [rng.expovariate(1 / 0.05) if rng.random() < 0.9 else rng.expovariate(1 / 2.0) for _ in range(n)]


def test_founding_defect_k2_is_refused():
    """Pool-level half of the founding defect: n=11,389 with two 200 s outages.

    The OLD derivation yields thresh = 10 x p99.99 = 2,000.0 from this exact pool, because p99.99
    lands ON the second outage. Measured here: r1 = 100.83, r2 = 2.05 -- an order of magnitude past
    the cut, two orders past the 1.05-1.96 the twelve production streams measure.

    The report-level reproduction uses the CARVED fixture in
    `test_report_renders_contaminated_stream_unmeasured`, NOT this pool: a `_bursty` pool spans only
    ~17 min of wall time, so through `report()` the old code books the edge_tail and the
    0.0-booked defect does not reproduce with it.
    """
    rng = random.Random(11)  # pinned: verified to satisfy the assertion below
    pool = pl.Series(_bursty(11_387, rng) + [200.0, 200.0])
    assert len(pool) == 11_389
    r1, r2 = continuity.tail_steepness(pool)
    assert max(r1, r2) >= continuity.TAIL_RATIO_CUT  # the gate condition itself


def test_second_ratio_is_load_bearing():
    """k ~= 0.002*n: p99.99 AND p99.9 both land on outages, so the FIRST ratio reads exactly 1.0 and
    sees nothing. Only p99.9/p99 still spans the cliff. Measured: r1 = 1.0, r2 = 193.66.

    Dropping the second ratio must fail exactly this test; swapping the tuple's order must fail it
    too, because the swapped r1 = 193.66 breaks the `r1 < cut` half.
    """
    rng = random.Random(12)  # pinned: verified to satisfy both assertions below
    n, k = 11_389, 23
    pool = pl.Series(_bursty(n - k, rng) + [200.0] * k)
    assert len(pool) == n
    r1, r2 = continuity.tail_steepness(pool)
    assert r1 < continuity.TAIL_RATIO_CUT
    assert r2 >= continuity.TAIL_RATIO_CUT


def test_legitimate_heavy_tails_stay_measured():
    """No false positives on legitimate spacing shapes.

    bursty-typical and bimodal are seed-INDEPENDENT properties -- swept over 200 seeds while writing
    this test they measured 1.661-2.042 and 1.813-2.267 respectively, every seed under the cut, so
    they are asserted generally over a sample of seeds rather than pinned.

    pareto alpha=1.1 and lognormal sigma=3 are PINNED to named seeds verified below the cut, because
    these families straddle it BY CONSTRUCTION: the cut IS the per-decade quantile ratio of a Pareto
    tail at alpha=1, the infinite-mean boundary, and alpha=1.1's theoretical ratio is 10^(1/1.1) =
    8.1. Swept over 200 seeds, 26 % (pareto) and 45 % (lognormal) of draws exceed the cut -- an
    unpinned seed here is a lottery that fails HEALTHY code, not a regression signal. Seeds 78 and
    117 are the widest-margin draws found in that sweep (4.93 and 6.65).
    """
    for seed in range(10):
        for name, sample in (
            ("bursty-typical", _bursty(20_000, random.Random(seed))),
            ("bimodal", _bimodal(20_000, random.Random(seed))),
        ):
            assert max(continuity.tail_steepness(pl.Series(sample))) < continuity.TAIL_RATIO_CUT, (name, seed)

    rng = random.Random(78)
    assert max(continuity.tail_steepness(pl.Series([rng.paretovariate(1.1) for _ in range(20_000)]))) < continuity.TAIL_RATIO_CUT
    rng = random.Random(117)
    assert max(continuity.tail_steepness(pl.Series([rng.lognormvariate(0, 3) for _ in range(20_000)]))) < continuity.TAIL_RATIO_CUT


def test_floor_keeps_ultra_bursty_measured_and_catches_its_outages():
    """Both arms exercise RATIO_FLOOR_S as the DENOMINATOR.

    An ultra-bursty pool has p99.9 = 0 exactly (same-millisecond bursts), so an unfloored ratio
    would divide by zero and refuse a healthy stream. The floor is not a new magic number: it is
    5.0 / 10, the spacing scale below which the existing threshold floor already declares steepness
    irrelevant. Its deliberate consequence is the second arm -- a sub-millisecond stream with two
    200 s pauses IS refused, and should be, since the alternative was scoring it against a 2,000 s
    threshold.

    (Note the max is 200 s in BOTH arms of the contaminated case by construction: a pool with a
    single 200 s max cannot be reached by p99.99 above MIN_POOL -- that is MIN_POOL's own design,
    so the refusable case needs two.)
    """
    benign = pl.Series([0.0] * 11_378 + [2.0] * 11)  # p99.9 = 0, p99.99 = 2.0
    r1, _ = continuity.tail_steepness(benign)
    assert r1 == 2.0 / continuity.RATIO_FLOOR_S == 4.0  # floored, not a ZeroDivisionError
    assert r1 < continuity.TAIL_RATIO_CUT  # ... and measured

    dirty = pl.Series([0.0] * 11_387 + [200.0] * 2)  # p99.99 lands on an outage
    r1, _ = continuity.tail_steepness(dirty)
    assert r1 == 200.0 / continuity.RATIO_FLOOR_S == 400.0
    assert r1 >= continuity.TAIL_RATIO_CUT  # refused


def test_boundary_n_5002_clean_stays_measured():
    """A pool of exactly MIN_POOL with a clean tail passes BOTH gates independently -- the two gates
    are conjunctive, so the new one must not silently re-refuse what the bound just admitted.
    Measured on this seed: r1 = 1.20, r2 = 2.00.
    """
    pool = pl.Series(_bursty(continuity.MIN_POOL, random.Random(0)))  # pinned seed, verified below the cut
    assert len(pool) == continuity.MIN_POOL == 5002
    r1, r2 = continuity.tail_steepness(pool)
    assert r1 < continuity.TAIL_RATIO_CUT
    assert r2 < continuity.TAIL_RATIO_CUT


def _full_hour(h: dt.datetime, step: float) -> list[dt.datetime]:
    n = int(3600 / step)
    return [h + dt.timedelta(seconds=j * step) for j in range(n)]


def _full_hour_carved(h: dt.datetime, step: float, windows: list[tuple[float, float]]) -> list[dt.datetime]:
    """`full_hour_with_gap`'s idiom, generalised to more than one carved window: drop the offsets
    inside each window from an otherwise FULL hour, so the only anomaly is the window itself and no
    unbooked tail hole is left behind (the trap
    `test_identical_outage_counts_the_same_on_dense_and_slow_streams` documents)."""
    n = int(3600 / step)
    offsets = [j * step for j in range(n) if not any(a <= j * step < a + length for a, length in windows)]
    return [h + dt.timedelta(seconds=o) for o in offsets]


def test_report_renders_contaminated_stream_unmeasured(tmp_path, capsys):
    """End-to-end wiring pin for the gate -- every pool-level test above passes with
    `tail_steepness` implemented but never wired into `measured`, so this test is what stands
    between that and shipping.

    The CARVED fixture: two hours at 0.6 s spacing, with two 200 s windows carved out of hour 0.
    One window is offset-aligned and one is not, so the two holes measure 201.0 s and 200.4 s.

    Reproduced against the CURRENT (pre-fix) code before this test was written: n = 11,332 (well
    past MIN_POOL), the pool's two largest intervals are 201.0 and 200.4, `quantile(0.9999)` lands
    on the SECOND-largest (index round(0.9999 x 11,331) = 11,330), so thresh_s derives to
    2,004.0 -- ten times the outage that produced it. Nothing then exceeds it: intra booked 0.0,
    gap_s 0.0, `gap% 0.0000%`, `EXIT BAR (<0.1% gap time): PASS`. The old instrument certifies a
    stream missing 401.4 s of data as perfectly clean.

    The control below (`test_single_carve_control_stays_measured_and_books_the_outage`) is the same
    geometry with ONE window: n = 11,666, p99.99 = 0.6, thresh_s = 6.0, and the 200.4 s hole is
    booked in full -- so the refusal here is caused by the contamination, not by the fixture shape.

    Five assertions, jointly the wiring proof. (e) matters as much as the rest: without it a fixture
    that accidentally landed under MIN_POOL would pass by refusing for the WRONG reason.
    """
    write_stream(
        tmp_path,
        "AAA/EUR",
        {
            H0: _full_hour_carved(H0, 0.6, [(1000.0, 200.0), (2400.0, 200.0)]),
            H1: _full_hour(H1, 0.6),
        },
    )
    rc, out = _run(tmp_path, capsys)
    assert rc == 0
    # (a) the refusal is NOT the old MIN_POOL gate -- the pool is more than twice the bound.
    assert int(_column(out, "AAA/EUR", "n")) == 11_332 >= continuity.MIN_POOL
    # (b) it is refused rather than scored against the self-inflated 2,004.0.
    assert _column(out, "AAA/EUR", "thresh_s") == "UNMEASURED"
    # (c) and the refusal reaches the verdict instead of being skipped.
    assert "*** FAIL *** (unmeasured streams: 1)" in out
    # (d) the operator is told WHICH refusal this is ...
    assert "steepens more than 10x across a decade of quantiles" in out
    # (e) ... and it is not the under-bound one.
    assert f"under the {continuity.MIN_POOL}-interval bound" not in out


def test_single_carve_control_stays_measured_and_books_the_outage(tmp_path, capsys):
    """The k=1 control on the CARVED fixture's exact geometry: one 200 s window, so p99.99 stays in
    the bulk at 0.6 s, thresh_s derives to 6.0, and the hole is booked in full at 200.4 s. This is
    what proves the gate refuses CONTAMINATION rather than the fixture's shape -- and it is the
    regime MIN_POOL was already sized for.
    """
    write_stream(
        tmp_path,
        "AAA/EUR",
        {H0: _full_hour_carved(H0, 0.6, [(1000.0, 200.0)]), H1: _full_hour(H1, 0.6)},
    )
    _, out = _run(tmp_path, capsys)
    assert float(_column(out, "AAA/EUR", "thresh_s")) == pytest.approx(6.0)
    assert float(_column(out, "AAA/EUR", "gap_s")) == pytest.approx(200.4, abs=0.05)


# --- the `tail` depth column, and naming the refusal reason on a MIXED tree -----------------------


def _mixed_tree(root: Path) -> None:
    """One contaminated stream beside one measured stream -- the shape production actually produces.

    AAA/EUR is the CARVED fixture from `test_report_renders_contaminated_stream_unmeasured`
    (n = 11,332, refused by the tail-steepness gate); DENSE/EUR is the same geometry with nothing
    carved out, so it is measured and `totals` is non-empty.
    """
    write_stream(
        root,
        "AAA/EUR",
        {H0: _full_hour_carved(H0, 0.6, [(1000.0, 200.0), (2400.0, 200.0)]), H1: _full_hour(H1, 0.6)},
    )
    write_stream(root, "DENSE/EUR", {H0: _full_hour(H0, 0.6), H1: _full_hour(H1, 0.6)})


def test_tail_depth_is_printed_and_correct(tmp_path, capsys):
    """The `tail` column, over all four of the slots it has to fill at once.

    AAA/EUR: `quantile(0.9999)` lands on the second-largest interval (200.4 s) and exactly TWO
    intervals reach it -- the visible fragility T0112's second sub-item asked for, printed on the
    UNMEASURED row, which is exactly where a reader needs it (a refused stream shows no threshold to
    judge, so the depth is all the transparency there is).

    DENSE/EUR: a synthetic stream whose every interval is the same 0.6 s, so the whole pool ties at
    p99.99 and the depth is n. That is an artifact of a perfectly uniform fixture, not what real
    data looks like -- twelve production streams measure depth 25-390 at n = 240k-3.9M -- but it
    pins that the column prints on MEASURED rows too.

    The TOTAL row's slot stays blank (depth is per pool; summing or averaging it would invent a
    number, the same reason `thresh_s` is blank there), and both rules widen with the header.
    """
    _mixed_tree(tmp_path)
    _, out = _run(tmp_path, capsys)
    assert _column(out, "AAA/EUR", "thresh_s") == "UNMEASURED"  # ... and the depth still prints:
    assert _column(out, "AAA/EUR", "tail") == "2"
    assert _column(out, "DENSE/EUR", "tail") == "11999"
    assert _column(out, "TOTAL", "tail") == ""
    lines = out.splitlines()
    header = next(line for line in lines if line.startswith("pair"))
    rules = [line for line in lines if line and set(line) == {"-"}]
    assert len(rules) == 2 and all(len(r) == len(header) for r in rules)


def test_a_one_row_hour_prints_a_blank_tail_instead_of_crashing(tmp_path, capsys):
    """`n == 0` is reachable, and it is the very signature this instrument exists to measure: an
    hour clobbered down to a single row (T0036) has no intervals at all, so its pool is empty,
    `pool.quantile(0.9999)` is None, and an unguarded `tail_depth` raises
    `TypeError: must be real number, not NoneType` -- taking the whole exit-bar run down with a
    traceback. Same failure class as
    `test_a_window_with_no_data_reports_it_instead_of_dividing_by_zero`: a verification tool that
    dies mid-table reads as broken rather than as an answer about a clobbered hour.

    Deleting the `if n else ""` guard passes every other test in both continuity files; this one is
    the only thing standing under it.
    """
    write_stream(tmp_path, "STUB/EUR", {H0: evenly(H0, 1, 1.0)})
    rc, out = _run(tmp_path, capsys)
    assert rc == 0  # judged, not crashed
    assert int(_column(out, "STUB/EUR", "n")) == 0
    assert _column(out, "STUB/EUR", "tail") == ""
    assert _column(out, "STUB/EUR", "thresh_s") == "UNMEASURED"


def test_depth_is_provably_not_a_detector():
    """THE test that documents why depth is not a gate. Anyone promoting depth into a gate must
    delete this test to do it.

    A clean and a contaminated pool of the SAME size measure the IDENTICAL depth (2): the count of
    intervals at or above p99.99 is a deterministic function of n (~ the tolerated k, plus one), not
    a function of contamination. The steepness ratios, measured on the very same two pools, separate
    them by two orders of magnitude (1.98 vs 111.16) -- which is why the gate is built on those and
    the depth is transparency only.
    """
    rng = random.Random(11)  # pinned: verified to satisfy every assertion below
    clean = pl.Series(_bursty(11_389, rng))
    dirty = pl.Series(_bursty(11_387, rng) + [200.0, 200.0])
    assert len(clean) == len(dirty) == 11_389
    assert continuity.tail_depth(clean) == continuity.tail_depth(dirty) == 2
    # ... while the statistic the gate DOES use tells them apart on the same data.
    assert max(continuity.tail_steepness(clean)) < continuity.TAIL_RATIO_CUT
    assert max(continuity.tail_steepness(dirty)) >= continuity.TAIL_RATIO_CUT


def test_the_refusal_reason_is_named_beside_measured_streams(tmp_path, capsys):
    """D4's distinguishability, on a MIXED tree -- which is where it has to work.

    Reproduced against Task 1's code, where the note block sat inside `report()`'s `if not totals:`
    branch: one measured stream beside one contaminated stream printed `n=11332 UNMEASURED` and
    `*** FAIL *** (unmeasured streams: 1)` and NO reason line anywhere. The reason appeared only on
    an ALL-unmeasured tree, and in production a contaminated stream almost always sits beside
    measured ones. The steepened-tail reason is also the less guessable of the two: a huge `n` beside
    UNMEASURED reads as "not the size bound" only to a reader who knows MIN_POOL.
    """
    _mixed_tree(tmp_path)
    _, out = _run(tmp_path, capsys)
    assert "TOTAL" in out, "the measured stream must still produce a TOTAL row"
    assert "*** FAIL *** (unmeasured streams: 1)" in out
    assert "steepens more than 10x across a decade of quantiles" in out
    assert f"under the {continuity.MIN_POOL}-interval bound" not in out
