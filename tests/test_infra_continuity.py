"""T0097 / spec 00076: the continuity instrument's measurement semantics.

Every test here constructs the defect it names and asserts the instrument reacts.
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
    # polars only, so it runs on a host without the repo installed). Registered in sys.modules
    # before exec because `dataclasses` resolves continuity.py's stringized annotations against
    # `sys.modules[cls.__module__]` -- unregistered, StreamTimeline's decoration crashes.
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
    """With polars' nearest interpolation `quantile(0.9999)` is the maximum until n exceeds 5001 --
    the degeneracy MIN_POOL is sized against (00076/D6)."""
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
    # H0 ends 2 s before its boundary, so the crossing is 2 s -- distinct from the uniform 1 s intra
    # spacing. `len(pool) == len(intra) + 1` would still hold if the crossing were double-booked into
    # `intra`, so intra's exact length and the crossing's absence from it are pinned instead.
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
    header -- the twin of `tests/test_continuity_overlay.py`'s `_column`. Every column is
    right-justified to a fixed width behind a single-space separator, so a cell always ends at its
    header token's offset; `str.split()` instead collapses blank cells (an UNMEASURED row's
    thresh_s/gap_s/gap%, the TOTAL row's n/thresh_s) and a trailing ` genesis` marker shifts every
    negative index. The header is found by its `pair` prefix, never by the first line containing
    `field`: the column names recur in the post-table reason notes, so that lookup falls through to a
    note and silently returns `''` once the column it names is gone."""
    lines = out.splitlines()
    header = next(line for line in lines if line.startswith("pair"))
    row = next(line for line in lines if line.startswith(prefix))
    tokens = list(re.finditer(r"\S+", header))
    idx = next(i for i, m in enumerate(tokens) if m.group() == field)
    lo = tokens[idx - 1].end() + 1 if idx > 0 else 0
    hi = tokens[idx].end()
    return row[lo:hi].strip()


def test_column_reads_blank_cells_on_unmeasured_and_total_rows(tmp_path, capsys):
    """`_column` reads an UNMEASURED row's blank cells and the TOTAL row, which excludes the
    unmeasured stream from its totals (T0097 Finding 3)."""
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
    """For MEASURED streams the booked outage is density-independent: the same 200 s hole counts the
    same at 0.1 s and at 0.6 s spacing.

    ONE outage among four clean hours keeps the fixture inside 00076/D6a's safe regime -- two
    outages in a ~11k pool put p99.99 ON the second one and the slow stream self-inflates by design,
    which is that decision's registered residual and not something this test may hide behind.

    The outage is CARVED out of an otherwise full hour (`n = int(3600 / step)`), never appended after
    a truncated prefix: appending leaves a second, unbooked hole at every hour's tail that swamps the
    single 200 s signal this test exists to measure.
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
    """`trunc` counts only boundary truncations -- the T0036 restart-clobber signature behind the
    `truncated hours: N` line -- never intra-hour silence, which would read as restart damage: H1's
    50 s outage lands in `gap_s` and leaves `trunc` at 0.
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
    """A `--since` window does not move genesis (D5 + D10 through `main()`, the only path where that
    defense runs): the genesis hour sits on the previous day because `--since` takes a date, so the
    window's first hour -- 400 s late -- is booked and counted as a truncation instead of inheriting
    genesis's free pass, while the 2.6 s crossing and 1.2 s tail stay under the 6.0 s threshold.
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
    # 00079/D4's attribution, pinned in BOTH directions: the under-bound reason is NAMED, and it is
    # not misattributed as a steepened tail.
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
    # covered_s on TOTAL counts only the measured stream.
    assert float(_column(out, "TOTAL", "covered_s")) == pytest.approx(float(_column(out, "DENSE/EUR", "covered_s")))
    assert "*** FAIL *** (unmeasured streams: 1)" in out


def test_all_streams_measured_keeps_the_plain_verdict(tmp_path, capsys):
    write_stream(tmp_path, "DENSE/EUR", {H0: evenly(H0, 5999, 0.6), H1: evenly(H1, 5999, 0.6)})
    _, out = _run(tmp_path, capsys)
    assert "unmeasured" not in out
    assert "EXIT BAR (<0.1% gap time): PASS" in out


def test_the_thin_stream_false_green_is_now_a_refusal_not_a_zero(tmp_path, capsys):
    """T0097's founding defect, closed by refusal: a stream sparse enough to self-calibrate into
    blindness -- 3 s spacing over two hours, with a 200 s window carved out of hour 0 -- pools under
    MIN_POOL, so the instrument refuses to score it instead of deriving a threshold from the outage
    itself and booking 0.0 s over it.
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
# Why MIN_POOL alone is not enough: `TAIL_RATIO_CUT` in `infra/scripts/continuity.py`.


def _bursty(n: int, rng: random.Random) -> list[float]:
    """T0097's measured spacing shape: same-millisecond bursts, so the pool's median is 0."""
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
    """Pool-level half of the founding defect: two 200 s outages in an 11,389-interval pool trip the
    gate, where the old 10x-p99.99 derivation would have taken its threshold from the outages.

    The report-level reproduction needs the carved fixture of
    `test_report_renders_contaminated_stream_unmeasured`: a `_bursty` pool spans too little wall time
    for the 0.0-booking defect to appear through `report()`."""
    rng = random.Random(11)  # pinned: verified to satisfy the assertion below
    pool = pl.Series(_bursty(11_387, rng) + [200.0, 200.0])
    assert len(pool) == 11_389
    r1, r2 = continuity.tail_steepness(pool)
    assert max(r1, r2) >= continuity.TAIL_RATIO_CUT  # the gate condition itself


def test_second_ratio_is_load_bearing():
    """At k ~= 0.002*n both p99.99 and p99.9 land on outages, so the first ratio reads ~1.0 and only
    p99.9/p99 still spans the cliff -- which is why `tail_steepness` returns both, in that order."""
    rng = random.Random(12)  # pinned: verified to satisfy both assertions below
    n, k = 11_389, 23
    pool = pl.Series(_bursty(n - k, rng) + [200.0] * k)
    assert len(pool) == n
    r1, r2 = continuity.tail_steepness(pool)
    assert r1 < continuity.TAIL_RATIO_CUT
    assert r2 >= continuity.TAIL_RATIO_CUT


def test_legitimate_heavy_tails_stay_measured():
    """No false positive on legitimate spacing shapes.

    bursty-typical and bimodal are seed-independent below the cut, so they are asserted over a range
    of seeds; pareto alpha=1.1 and lognormal sigma=3 straddle the cut BY CONSTRUCTION -- the cut IS a
    Pareto tail's per-decade ratio at alpha=1, and alpha=1.1's is 10^(1/1.1) = 8.1 -- so their seeds
    are pinned, an unpinned one being a lottery that fails HEALTHY code rather than a signal.
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
    """RATIO_FLOOR_S as the DENOMINATOR in both arms: a p99.9 = 0 ultra-bursty pool stays measured
    instead of dividing by zero, and the same floor refuses that pool once two 200 s pauses sit in
    it. Two pauses and not one, because above MIN_POOL p99.99 cannot reach a lone maximum (00076/D6).
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
    """End-to-end wiring pin: every pool-level test above passes with `tail_steepness` implemented
    but never wired into `measured`, so this test is what stands between that and shipping.

    Two 200 s windows carved out of hour 0 at 0.6 s spacing put p99.99 on the second-largest
    interval, the contamination the gate refuses;
    `test_single_carve_control_stays_measured_and_books_the_outage` is the same geometry with ONE
    window, so what is refused here is the contamination and not the fixture's shape.
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
    """The k=1 control on the carved fixture's geometry: with ONE 200 s window p99.99 stays in the
    bulk, the threshold derives to 6.0 s, and the hole is booked in full.
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
    """The carved, gate-refused stream beside an uncarved measured one -- the mixed shape production
    produces, where a non-empty `totals` coexists with a refusal."""
    write_stream(
        root,
        "AAA/EUR",
        {H0: _full_hour_carved(H0, 0.6, [(1000.0, 200.0), (2400.0, 200.0)]), H1: _full_hour(H1, 0.6)},
    )
    write_stream(root, "DENSE/EUR", {H0: _full_hour(H0, 0.6), H1: _full_hour(H1, 0.6)})


def test_tail_depth_is_printed_and_correct(tmp_path, capsys):
    """The `tail` column in all four slots at once: 2 on the refused stream, where the depth is the
    only transparency a reader gets because no threshold is shown; n on a perfectly uniform fixture;
    blank on TOTAL, since depth is per pool and summing it would invent a number, as for `thresh_s`;
    and both rules widen with the header.
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
    """A one-row hour (the T0036 clobber signature) has an empty pool, so `tail_depth` must print a
    blank rather than take the whole run down on `pool.quantile(0.9999)` being None.
    """
    write_stream(tmp_path, "STUB/EUR", {H0: evenly(H0, 1, 1.0)})
    rc, out = _run(tmp_path, capsys)
    assert rc == 0  # judged, not crashed
    assert int(_column(out, "STUB/EUR", "n")) == 0
    assert _column(out, "STUB/EUR", "tail") == ""
    assert _column(out, "STUB/EUR", "thresh_s") == "UNMEASURED"


def test_depth_is_provably_not_a_detector():
    """Depth is not a contamination detector (00079/D5): a clean and a contaminated pool of the same
    size measure the identical depth, while the steepness ratios the gate does use separate them by
    two orders of magnitude.
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
    """00079/D4's distinguishability on a MIXED tree, which is where it has to work: a contaminated
    stream beside a measured one still names its refusal reason, since in production the two sit
    together and a huge `n` beside UNMEASURED reads as "not the size bound" only to a reader who
    knows MIN_POOL.
    """
    _mixed_tree(tmp_path)
    _, out = _run(tmp_path, capsys)
    assert "TOTAL" in out, "the measured stream must still produce a TOTAL row"
    assert "*** FAIL *** (unmeasured streams: 1)" in out
    assert "steepens more than 10x across a decade of quantiles" in out
    assert f"under the {continuity.MIN_POOL}-interval bound" not in out
