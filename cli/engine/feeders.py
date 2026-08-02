"""Read-only measurements over the journaled shadow cycles, feeding the go-live sizing questions.

Two reports share one replay: `decompose_report` attributes a cycle's gross across the pipeline's
stages (per-sleeve -> combined -> capped -> governed), and `accumulation_report` simulates an
accumulate-until-placeable order policy against Kraken's venue minimums to measure the drift floor
those minimums impose. Neither writes anything, and neither touches the builder: every stage is
recomputed from public parts and then PROVEN against the builder's own output (see
`replay_stages`), so a builder change surfaces as a raised error rather than a silently wrong table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from cli.engine.errors import EngineError
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, validate_record
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, build_crossfreq_system_fast
from cli.risk import apply_position_caps

SLEEVES = ("B", "A1", "A2")

Reader = Callable[[SnapshotEntry], tuple[list[datetime], list[float | None]]]


@dataclass(frozen=True)
class CycleStages:
    """One cycle's forming-row book at each pipeline stage, plus the governor multiplier."""

    cycle_ts: datetime
    sleeve_positions: dict[str, dict[str, float]]  # per sleeve, per asset
    combined: dict[str, float]
    capped: dict[str, float]
    final: dict[str, float]
    multiplier: float
    closes: dict[str, float]  # the 4h close used for the forming row, per asset
    cap_bound: bool


def stage_grosses(sleeve_positions: dict[str, dict[str, float]]) -> dict[str, float]:
    """Gross (sum of absolute positions) for each sleeve."""
    return {name: sum(abs(v) for v in book.values()) for name, book in sleeve_positions.items()}


def cancellation_ratio(sleeve_positions: dict[str, dict[str, float]]) -> tuple[float, float, float]:
    """Return `(ratio, combined_gross, mean_sleeve_gross)`.

    The 1/3 combination nets opposing sleeve positions away asset by asset, so the combined book's
    gross is NOT the mean of the sleeve grosses. The ratio names how much of the sleeves' exposure
    survives the combination: 1.0 = they agree and nothing cancels; well below 1.0 = disagreement
    is where gross is going. NaN on a flat book (0/0) -- reporting 1.0 there would claim agreement
    that was never demonstrated.
    """
    assets = {a for book in sleeve_positions.values() for a in book}
    third = 1 / 3
    combined_gross = sum(abs(sum(third * book.get(a, 0.0) for book in sleeve_positions.values())) for a in assets)
    grosses = stage_grosses(sleeve_positions)
    mean_sleeve_gross = sum(grosses.values()) / len(grosses) if grosses else 0.0
    ratio = combined_gross / mean_sleeve_gross if mean_sleeve_gross else math.nan
    return ratio, combined_gross, mean_sleeve_gross


def _check_stage_identity(multiplier: float, capped: dict[str, float], final: dict[str, float], *, cycle_ts) -> None:
    """Raise unless `multiplier * capped[a] == final[a]` exactly, for every asset.

    Exact equality is correct here, not float-fragile: the harness reruns the builder's own
    arithmetic on the builder's own floats in the same order (`sleeve_positions` stores the
    already-4h-expanded series, and apply_position_caps is a pure per-element clip), so any
    difference means the recomputation genuinely diverged.
    """
    for a, target in final.items():
        if multiplier * capped[a] != target:
            raise EngineError(
                f"stage identity broken for asset={a!r} at cycle_ts={cycle_ts}: "
                f"multiplier*capped={multiplier * capped[a]!r} != builder final_targets={target!r} -- "
                "the recomputed combination or cap no longer matches the builder"
            )


def replay_stages(record: CycleRecord, reader: Reader, *, config: CrossfreqSystemConfig | None = None) -> CycleStages:
    """Rebuild one journaled cycle and return its forming-row book at every pipeline stage.

    Two identities, both per cycle, because they catch different failures. INTERNAL:
    `multiplier * capped[a]` must equal the builder's own `final_targets[a]` exactly -- evidence
    the recomputed intermediate IS the builder's, so a changed combination or cap raises instead of
    reporting a wrong attribution. JOURNAL: the rebuilt targets must equal the RECORD's own
    `final_targets` -- which the internal one structurally cannot catch, since a self-consistent
    rebuild that diverges from what the engine actually traded would agree with itself all the way
    and both reports would describe a book that never existed.
    """
    c = config or CrossfreqSystemConfig()
    validate_record(record)  # no-peek + snapshot-boundary discipline, before any snapshot is read
    by_grid: dict[str, dict[str, tuple[list[datetime], list[float | None]]]] = {"1440": {}, "240": {}}
    for entry in record.snapshots:
        ts, closes = reader(entry)
        if snapshot_content_hash(ts, closes) != entry.content_hash:
            raise EngineError(f"content hash mismatch for pair={entry.pair!r} grid={entry.grid!r} -- corrupt evidence")
        if len(ts) != entry.n_bars or ts[0] != entry.first_ts or ts[-1] != entry.last_ts:
            raise EngineError(
                f"pair={entry.pair!r} grid={entry.grid!r}: read data disagrees with its own journaled metadata -- "
                f"n_bars={len(ts)} vs {entry.n_bars!r}, first_ts={ts[0]!r} vs {entry.first_ts!r}, "
                f"last_ts={ts[-1]!r} vs {entry.last_ts!r}"
            )
        by_grid[entry.grid][entry.pair] = (ts, closes)

    def assemble(grid: str) -> tuple[list[datetime], dict[str, list[float | None]]]:
        shared: list[datetime] | None = None
        prices: dict[str, list[float | None]] = {}
        for pair, (ts, closes) in by_grid[grid].items():
            if shared is None:
                shared = ts
            elif ts != shared:
                raise EngineError(f"pair={pair!r} grid={grid!r} ts calendar disagrees with the grid's shared calendar")
            prices[pair] = closes
        if shared is None:
            raise EngineError(f"no snapshots for grid={grid!r}")
        return shared, prices

    daily_ts, daily_prices = assemble("1440")
    h4_ts, h4_prices = assemble("240")

    expected_h4_last = record.cycle_ts - timedelta(hours=4)
    if h4_ts[-1] != expected_h4_last:
        raise EngineError(
            f"the builder's grid does not contain the cycle_ts interval: h4_ts[-1]={h4_ts[-1]!r} != "
            f"cycle_ts - 4h ({expected_h4_last!r})"
        )

    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=c)
    n = result.n_periods

    sleeves = {name: {a: result.sleeve_positions[name][a][n] for a in c.assets} for name in SLEEVES}
    third = 1 / 3
    # The builder's own chained-add expression, NOT sum(): since 3.12 sum() uses Neumaier
    # compensated summation, which differs by an ulp on ~18% of triples -- and the identity
    # below compares exactly, so a sum() here would fire on cycles that are in fact correct.
    combined = {a: third * sleeves["B"][a] + third * sleeves["A1"][a] + third * sleeves["A2"][a] for a in c.assets}
    capped_series = apply_position_caps({a: [combined[a]] for a in c.assets}, long_cap=c.long_cap, short_cap=c.short_cap)
    capped = {a: capped_series[a][0] for a in c.assets}
    multiplier = result.multipliers[n]
    final = {a: result.final_targets[a][n] for a in c.assets}

    _check_stage_identity(multiplier, capped, final, cycle_ts=record.cycle_ts)

    # The journal identity: what we rebuilt must be what the engine actually traded.
    if set(final) != set(record.final_targets):
        raise EngineError(
            f"rebuilt asset set differs from the journaled one at cycle_ts={record.cycle_ts}: "
            f"{sorted(set(final) ^ set(record.final_targets))}"
        )
    for a, journaled in record.final_targets.items():
        if final[a] != journaled:
            raise EngineError(
                f"replay disagrees with the journal for asset={a!r} at cycle_ts={record.cycle_ts}: "
                f"rebuilt={final[a]!r} != journaled={journaled!r} -- this cycle's rebuild does not "
                "describe the book the engine traded"
            )

    closes = {}
    for a in c.assets:
        series = h4_prices[a]
        value = series[-1]
        if value is None:
            raise EngineError(f"the forming row's close is missing for asset={a!r} at cycle_ts={record.cycle_ts}")
        closes[a] = float(value)

    return CycleStages(
        cycle_ts=record.cycle_ts,
        sleeve_positions=sleeves,
        combined=combined,
        capped=capped,
        final=final,
        multiplier=multiplier,
        closes=closes,
        cap_bound=any(abs(capped[a] - combined[a]) > 1e-15 for a in c.assets),
    )
