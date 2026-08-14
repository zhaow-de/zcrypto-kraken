"""A twelve-symbol BASKET fixture built for the REAL builder (spec 00094).

Schema 2 cannot be exercised with a stubbed builder: a stub keyed by whatever it is handed accepts
the twelve-symbol panel the real builder REFUSES, so it cannot see the widening's defect at all --
which is exactly how the `PortfolioError` in `cli/engine/feeders.py` reached a merged branch behind
38 green tests. Everything here therefore feeds `build_crossfreq_system_fast` for real; the series
are sized and shaped so the ten model targets come out non-zero AND pairwise distinct, so a value
carried through a pipeline can never be mistaken for the structural zero the two `/BTC` legs get.

Consumers: tests/test_engine_feeders.py, tests/test_engine_soak.py. (tests/test_engine_concordance.py
keeps its own straddle fixture -- it journals per-cycle snapshot parquets over a growing window,
which nothing else needs.)
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from cli.engine.cycle import _expand_to_basket
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash
from cli.engine.store import BASKET
from cli.portfolio.crossfreq_system import build_crossfreq_system_fast

CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
N_DAILY = 320  # > the longest daily lookback in play (A2's 240 arm); shorter makes every target 0.0
N_H4 = 520

Grids = dict[int, tuple[list[datetime], dict[str, list[float]]]]


def _closes(symbol: str, n: int, scale: int) -> list[float]:
    """A distinct trending-plus-cycling path per symbol. The constants are tuned, not arbitrary --
    they are what makes the ten EUR targets non-zero and pairwise distinct."""
    k = BASKET.index(symbol)
    level, amplitude, period = 100.0 * (1 + k), 0.10 + 0.03 * k, (37 + 7 * k) * scale
    return [level * (1.0 + amplitude * math.sin(2 * math.pi * i / period) + 0.003 * i / scale) for i in range(n)]


def grids(cycle_ts: datetime = CYCLE_TS, *, n_daily: int = N_DAILY, n_h4: int = N_H4) -> Grids:
    """`{interval: (ts, {symbol: closes})}` over all twelve BASKET symbols, ONE calendar per grid,
    with each grid's last stamp satisfying the journal's snapshot-boundary invariant for `cycle_ts`."""
    return {
        interval: ([last - (n - 1 - i) * step for i in range(n)], {s: _closes(s, n, scale) for s in BASKET})
        for interval, last, n, step, scale in (
            (1440, cycle_ts.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1), n_daily, timedelta(days=1), 1),
            (240, cycle_ts - timedelta(hours=4), n_h4, timedelta(hours=4), 6),
        )
    }


def model_inputs(g: Grids) -> tuple[dict[str, list[float]], list[datetime], dict[str, list[float]], list[datetime]]:
    """The ten EUR legs, base-keyed, in `build_crossfreq_system_fast`'s argument order -- the same
    contraction `select_model_inputs` performs, spelled out here so a test that pins the contraction
    is not comparing it against itself."""
    eur = [s for s in BASKET if s.endswith("/EUR")]
    daily_ts, daily = g[1440]
    h4_ts, h4 = g[240]
    return (
        {s.split("/")[0]: daily[s] for s in eur},
        daily_ts,
        {s.split("/")[0]: h4[s] for s in eur},
        h4_ts,
    )


def build(g: Grids):
    """The REAL ten-asset build over `g`. Returns the builder's own result object."""
    return build_crossfreq_system_fast(*model_inputs(g))


def targets_at(result, k: int, schema_version: int) -> dict[str, float]:
    """Row `k` of a build's `final_targets`, in `schema_version`'s key space: base-keyed for 1, and
    expanded onto the twelve-symbol basket by the cycle's own `_expand_to_basket` for 2."""
    row = {base: series[k] for base, series in result.final_targets.items()}
    return row if schema_version == 1 else _expand_to_basket(row)


def snapshot_entries(g: Grids, *, schema_version: int) -> tuple[SnapshotEntry, ...]:
    """One SnapshotEntry per pair x grid, in the schema's own key space: the ten model bases for
    schema 1, the twelve full symbols for schema 2 (what `validate_record` requires of each)."""
    entries = []
    for interval, (ts, by_symbol) in g.items():
        keep = {s.split("/")[0]: c for s, c in by_symbol.items() if s.endswith("/EUR")} if schema_version == 1 else by_symbol
        for pair, closes in keep.items():
            entries.append(
                SnapshotEntry(
                    pair=pair,
                    grid=str(interval),
                    n_bars=len(ts),
                    first_ts=ts[0],
                    last_ts=ts[-1],
                    content_hash=snapshot_content_hash(ts, closes),
                    path=f"{pair.replace('/', '-')}-{interval}",
                )
            )
    return tuple(entries)


def reader(g: Grids):
    """A snapshot reader over `g`, routing by the entry's own grid and pair."""

    def read(entry: SnapshotEntry):
        ts, by_symbol = g[int(entry.grid)]
        key = entry.pair if entry.pair in by_symbol else f"{entry.pair}/EUR"
        return list(ts), list(by_symbol[key])

    return read


def record(g: Grids, *, schema_version: int, cycle_ts: datetime = CYCLE_TS, result=None) -> CycleRecord:
    """A journalable CycleRecord for `cycle_ts` at `schema_version`, whose `final_targets` are the
    REAL build's forming row in that schema's key space -- exactly what `run_cycle` writes."""
    result = result if result is not None else build(g)
    return CycleRecord(
        schema_version=schema_version,
        cycle_ts=cycle_ts,
        snapshots=snapshot_entries(g, schema_version=schema_version),
        final_targets=targets_at(result, result.n_periods, schema_version),
        started_at=cycle_ts,
        completed_at=cycle_ts + timedelta(minutes=1),
        code_version="test",
        builder_path="fast",
    )
