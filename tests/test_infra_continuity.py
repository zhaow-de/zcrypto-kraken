"""T0097 / spec 00076: the continuity instrument's measurement semantics.

Every test here constructs the defect it names and asserts the instrument reacts -- reading the
assertion is not verification (`.claude/rules/agent-ops.md`).
"""

import datetime as dt
import importlib.util
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
