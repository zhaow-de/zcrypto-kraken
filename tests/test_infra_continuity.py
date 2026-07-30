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
