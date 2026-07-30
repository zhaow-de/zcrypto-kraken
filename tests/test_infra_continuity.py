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
