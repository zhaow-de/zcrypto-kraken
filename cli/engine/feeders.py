"""Read-only measurements over the journaled shadow cycles, feeding the go-live sizing questions.

Two reports share one replay: `decompose_report` attributes a cycle's gross across the pipeline's
stages (per-sleeve -> combined -> capped -> governed), and `accumulation_report` simulates an
accumulate-until-placeable order policy against Kraken's venue minimums to measure the drift floor
those minimums impose. Neither writes anything, and neither touches the builder: every stage is
recomputed from public parts and then PROVEN against the builder's own output (see
`replay_stages`), so a builder change surfaces as a raised error rather than a silently wrong table.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
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


def _median(values: list[float]) -> float:
    """Median of the non-NaN values, NaN when none remain.

    Dropping NaN is deliberate: a flat cycle's ratio is 0/0, and counting it as 1.0 would claim
    agreement the cycle never demonstrated.
    """
    clean = sorted(v for v in values if not math.isnan(v))
    if not clean:
        return math.nan
    mid = len(clean) // 2
    return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2


_MEDIAN_KEYS = (
    "mean_sleeve_gross",
    "combined_gross",
    "cancellation_ratio",
    "capped_gross",
    "capped_ratio",
    "multiplier",
    "governed_ratio",
    "final_gross",
)


def decompose_payload(stages: list[CycleStages]) -> dict:
    """Per-cycle attribution rows plus their aggregates. Pure -- no I/O, no replay.

    Each of the three consecutive-stage ratios is carried PER CYCLE (`cancellation_ratio`,
    `capped_ratio`, `governed_ratio`) and aggregated as the median of those per-cycle values --
    never as a ratio of the stage medians. The two differ materially once the governor multiplier
    varies across the window, and only the per-cycle basis answers "what fraction survives a
    typical cycle"; a ratio of medians divides two numbers that need not come from the same cycle.
    """
    rows = []
    for s in stages:
        ratio, combined_gross, mean_sleeve_gross = cancellation_ratio(s.sleeve_positions)
        capped_gross = sum(abs(v) for v in s.capped.values())
        # This ratio's denominator is the BUILDER's combined book, not cancellation_ratio's
        # sleeve-side recomputation: numerator and denominator must be summed off the same floats.
        # Mixed, an unbound cycle reports 1.0000000000000002 -- gross growing THROUGH the caps,
        # which cannot happen -- and a book flat in reals but not in floats divides one ulp-scale
        # gross by another, giving O(1) garbage that the NaN filter cannot catch.
        combined_gross_builder = sum(abs(v) for v in s.combined.values())
        rows.append(
            {
                "cycle_ts": s.cycle_ts.isoformat(),
                "sleeve_gross": stage_grosses(s.sleeve_positions),
                "mean_sleeve_gross": mean_sleeve_gross,
                "combined_gross": combined_gross,
                "cancellation_ratio": ratio,
                "capped_gross": capped_gross,
                "capped_ratio": capped_gross / combined_gross_builder if combined_gross_builder else math.nan,
                "multiplier": s.multiplier,
                "governed_ratio": s.multiplier,  # final = multiplier * capped, exactly (see replay_stages)
                "final_gross": sum(abs(v) for v in s.final.values()),
                "n_active": sum(1 for v in s.final.values() if v != 0.0),
                "cap_bound": s.cap_bound,
            }
        )

    return {
        "n_cycles": len(rows),
        "cycles": rows,
        "median": {key: _median([r[key] for r in rows]) for key in _MEDIAN_KEYS},
    }


def _pct(value: float) -> str:
    return f"{'n/a':>8}" if math.isnan(value) else f"{100 * value:8.3f}"


def _ratio(value: float) -> str:
    return f"{'n/a':>5}" if math.isnan(value) else f"{value:5.3f}"


def _render_decompose(payload: dict) -> str:
    """Fixed-width attribution table: one line per cycle, a median line, then the summary."""
    header = (
        f"{'cycle':<16} {'B':>8} {'A1':>8} {'A2':>8} {'combined':>8} {'ratio':>5} "
        f"{'capped':>8} {'mult':>5} {'final':>8} {'act':>3} {'cap?':>4}"
    )
    lines = [
        "Gross attribution per cycle (gross columns are % of NAV; ratio = combined / mean sleeve gross)",
        "",
        header,
        "-" * len(header),
    ]
    for r in payload["cycles"]:
        g = r["sleeve_gross"]
        lines.append(
            f"{r['cycle_ts'][:16]:<16} {_pct(g['B'])} {_pct(g['A1'])} {_pct(g['A2'])} "
            f"{_pct(r['combined_gross'])} {_ratio(r['cancellation_ratio'])} "
            f"{_pct(r['capped_gross'])} {_ratio(r['multiplier'])} {_pct(r['final_gross'])} "
            f"{r['n_active']:>3} {'yes' if r['cap_bound'] else 'no':>4}"
        )
    m = payload["median"]
    lines.append("-" * len(header))
    lines.append(
        f"{'MEDIAN':<16} {'':>8} {'':>8} {'':>8} "
        f"{_pct(m['combined_gross'])} {_ratio(m['cancellation_ratio'])} "
        f"{_pct(m['capped_gross'])} {_ratio(m['multiplier'])} {_pct(m['final_gross'])} "
        f"{'':>3} {'':>4}"
    )

    n_cap_bound = sum(1 for r in payload["cycles"] if r["cap_bound"])
    lines += [
        "(every MEDIAN cell is that column's own median, so the ratio cells are medians of the",
        " per-cycle ratios -- do not divide one median gross by another, they need not share a cycle)",
        "",
        f"Where the gross goes, across {payload['n_cycles']} cycles (each ratio is the median of the per-cycle ratios):",
        f"  median mean sleeve gross  {_pct(m['mean_sleeve_gross'])} % of NAV",
        f"  sleeve -> combined        {_ratio(m['cancellation_ratio'])}   fraction of the sleeves' average gross left after combining them",
        f"  combined -> capped        {_ratio(m['capped_ratio'])}   fraction left after the position caps",
        f"  capped -> final           {_ratio(m['governed_ratio'])}   fraction left by the volatility governor (its multiplier)",
        f"  cap-bound cycles: {n_cap_bound} of {payload['n_cycles']}",
    ]
    if payload.get("n_failed"):
        lines += ["", f"Cycles failed to replay: {payload['n_failed']} (excluded from every number above)"]
        lines += [f"  {f['cycle_ts']}  {f['error']}" for f in payload["failures"]]
    return "\n".join(lines)


def decompose_report(
    records: list[CycleRecord], reader: Reader, *, config: CrossfreqSystemConfig | None = None
) -> tuple[str, dict]:
    """Replay every record and render the gross attribution across the pipeline's stages.

    A record whose replay fails is named and counted, never silently dropped -- a missing cycle
    would bias every aggregate below it with nothing on the page to say so.
    """
    stages: list[CycleStages] = []
    failures: list[dict] = []
    for record in sorted(records, key=lambda r: r.cycle_ts):
        try:
            stages.append(replay_stages(record, reader, config=config))
        except EngineError as exc:
            failures.append({"cycle_ts": record.cycle_ts.isoformat(), "error": str(exc)})
    payload = decompose_payload(stages)
    payload["n_failed"] = len(failures)
    payload["failures"] = failures
    return _render_decompose(payload), payload


# --- the accumulation drift floor ---------------------------------------------------------------

# One ISO week of 4-hourly cycles: 6 per day x 7 days. A week holding fewer is incomplete, and its
# mean is not comparable to a full week's -- derived from the count, never from a week number.
_CYCLES_PER_FULL_WEEK = 6 * 7


def _p95(values: list[float]) -> float:
    """95th percentile by nearest rank -- always an OBSERVED value, never an interpolated one.

    NaN is dropped and an empty input gives NaN, matching `_median`.
    """
    clean = sorted(v for v in values if not math.isnan(v))
    if not clean:
        return math.nan
    return clean[math.ceil(0.95 * len(clean)) - 1]


def load_minimums(path: Path) -> tuple[dict[str, tuple[float, float]], str]:
    """Per-asset `(ordermin_base, costmin)` for the EUR book, plus the snapshot's fetched_at stamp.

    Sourced from the snapshot's `universe` block, which is already normalised to base/quote --
    NOT from `raw.assetpairs`, where Kraken lists DOGE as `XDG/EUR` (there is no `DOGE/EUR`
    wsname at all) and BTC as `XBT/EUR`, so a `<ASSET>/EUR` match silently loses assets.
    The `quote == "EUR"` filter is load-bearing: `universe` also carries ETH/BTC and SOL/BTC
    whose costmin is 0.00002 BTC, and keying by base without it would overwrite ETH's and
    SOL's EUR floors with a BTC-denominated number read as euros.
    """
    payload = json.loads(path.read_text())
    out: dict[str, tuple[float, float]] = {}
    for entry in payload["universe"]:
        if entry.get("quote") != "EUR":
            continue
        base = entry["base"]
        if base in out:
            raise EngineError(f"duplicate EUR pair for base={base!r} in {path} -- ambiguous minimums")
        out[base] = (float(entry["ordermin"]), float(entry["costmin"]))
    return out, payload["fetched_at"]


def _weekly_drift(stages: list[CycleStages], rows: list[dict]) -> list[dict]:
    """Mean drift per ISO week, with each week's cycle count and an incompleteness flag.

    Mean and count only -- deliberately no weekly p95 (spec D6): the window is four ISO weeks, and
    a p95 over four points is the maximum wearing a percentile's name. This number becomes a
    live-trading gate band, so the weeks are printed and read individually instead.
    """
    buckets: dict[tuple[int, int], list[float]] = {}
    for stage, row in zip(stages, rows, strict=True):
        iso = stage.cycle_ts.isocalendar()
        buckets.setdefault((iso.year, iso.week), []).append(row["drift_bps"])
    return [
        {
            "iso_year": year,
            "iso_week": week,
            "n_cycles": len(values),
            "mean_drift_bps": sum(values) / len(values),
            "partial": len(values) < _CYCLES_PER_FULL_WEEK,
        }
        for (year, week), values in sorted(buckets.items())
    ]


def accumulation_payload(stages: list[CycleStages], minimums: dict[str, tuple[float, float]], navs: list[float]) -> dict:
    """Replay the accumulate-until-placeable policy at each NAV. Pure -- no I/O, no replay.

    Held state is carried in BASE UNITS, never EUR (spec D4). `ordermin` is natively a quantity, so
    the floor comparison is direct rather than converted, and mark-to-market falls out for free: a
    held quantity is simply worth `held_qty * close` at any later cycle. A EUR-denominated held
    state would instead compare a price-stale "held" against a freshly priced "target", and would
    report zero drift across a pure price move that placed no order.

    The two floors are INDEPENDENT gates, never a max over mixed units: `ordermin_base` is a
    quantity (20 ADA, 50 DOGE, 0.00005 BTC) and `costmin` is euros (0.45 across the EUR book).

    NAV is held constant across the window on purpose: this measures the PLACEMENT floor, not P&L,
    and a drifting NAV would fold return into a number that must be pure venue-minimum.
    """
    bad_navs = [n for n in navs if not math.isfinite(n) or n <= 0]
    if bad_navs:
        raise EngineError(
            f"NAV must be finite and positive, got {bad_navs} -- zero divides, and a negative one "
            "silently signs every drift_bps that the reported median and p95 are read from"
        )
    # The policy is state-carrying across cycles, so chronological order is load-bearing, not
    # cosmetic: an out-of-order stage would accumulate against the wrong held quantity.
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    for s in ordered:
        missing = sorted(set(s.final) - set(minimums))
        if missing:
            raise EngineError(
                f"no venue minimums for asset(s) {missing} at cycle_ts={s.cycle_ts.isoformat()} -- "
                "a silently absent floor would place every delta and understate the drift"
            )

    by_nav: dict[float, dict] = {}
    for nav in navs:
        held_qty: dict[str, float] = {a: 0.0 for a in minimums}
        rows: list[dict] = []
        for s in ordered:
            target_qty: dict[str, float] = {}
            drift_eur = 0.0
            placed = False
            for a, weight in s.final.items():
                close = s.closes[a]
                target = (weight * nav) / close
                delta = target - held_qty[a]
                ordermin_base, costmin = minimums[a]
                # Two caveats for anyone reusing this as EXECUTION logic rather than as a
                # measurement (the executor's delta formula is the intended reader):
                #   - these `>=` comparisons are float-exact, so a delta landing precisely on a
                #     floor is representation-dependent. Harmless when measuring over journaled
                #     data, where deltas never sit exactly on a floor; not harmless when a venue
                #     is about to reject or accept the order on that same boundary.
                #   - an asset key-absent from a later cycle's `final` would freeze its held_qty
                #     and stop contributing drift. Unreachable here (every journaled cycle carries
                #     the full universe, and weight-0.0 liquidation is handled correctly), but a
                #     live book whose universe shrinks mid-run would hit it.
                if abs(delta) >= ordermin_base and abs(delta) * close >= costmin:
                    held_qty[a] = target  # full fill at the journaled close
                    placed = True
                target_qty[a] = target
                # Drift is measured AFTER the decision, so a placing asset contributes exactly 0.
                drift_eur += abs(target - held_qty[a]) * close
            rows.append(
                {
                    "cycle_ts": s.cycle_ts.isoformat(),
                    "placed": placed,
                    "target_qty": target_qty,
                    "drift_eur": drift_eur,
                    "drift_bps": 10_000 * drift_eur / nav,
                }
            )
        drift_bps = [r["drift_bps"] for r in rows]
        by_nav[nav] = {
            "nav": nav,
            "cycles": rows,
            "n_placed": sum(1 for r in rows if r["placed"]),
            "median_drift_bps": _median(drift_bps),
            "p95_drift_bps": _p95(drift_bps),
            "weeks": _weekly_drift(ordered, rows),
        }
    return {"n_cycles": len(ordered), "navs": list(navs), "by_nav": by_nav}


def _bps(value: float) -> str:
    return f"{'n/a':>11}" if math.isnan(value) else f"{value:11.1f}"


def _render_accumulation(payload: dict) -> str:
    """Per-NAV drift summary and the per-week table, stamped with the minimums' fetch date."""
    navs = payload["navs"]
    lines = [
        "Accumulation drift floor: what the venue's order minimums cost at each portfolio size",
        f"Venue minimums read {payload['minimums_fetched_at']} -- these floors move, so a band "
        "quoted from an older table is stale, not conservative.",
        "",
        f"Per cycle, across {payload['n_cycles']} cycles (drift is bps of NAV, measured after the placement decision)",
        "",
    ]
    header = f"{'NAV':>9} {'placed':>10} {'median_bps':>11} {'p95_bps':>11}"
    lines += [header, "-" * len(header)]
    for nav in navs:
        row = payload["by_nav"][nav]
        placed = f"{row['n_placed']}/{payload['n_cycles']}"
        lines.append(f"{nav:>9,.0f} {placed:>10} {_bps(row['median_drift_bps'])} {_bps(row['p95_drift_bps'])}")

    lines += [
        "",
        "Per ISO week (mean drift, bps of NAV). There is no weekly p95 here and there will not be:",
        "the window is four ISO weeks, and a p95 over four points is the maximum wearing a",
        "percentile's name. The weeks are printed with their counts and read individually.",
        "",
    ]
    week_header = f"{'week':<10} {'cycles':>7}" + "".join(f"{nav:>11,.0f}" for nav in navs)
    lines += [week_header, "-" * len(week_header)]
    means = {nav: {(w["iso_year"], w["iso_week"]): w["mean_drift_bps"] for w in payload["by_nav"][nav]["weeks"]} for nav in navs}
    weeks = payload["by_nav"][navs[0]]["weeks"] if navs else []
    for w in weeks:
        key = (w["iso_year"], w["iso_week"])
        cells = "".join(_bps(means[nav][key]) for nav in navs)
        lines.append(f"{key[0]}-W{key[1]:02d}   {w['n_cycles']:>6}{'*' if w['partial'] else ' '}{cells}")
    if any(w["partial"] for w in weeks):
        lines.append(
            f"* fewer than {_CYCLES_PER_FULL_WEEK} cycles (6 per day x 7 days): a partial week, "
            "whose mean is not comparable to a full week's."
        )

    if payload.get("n_failed"):
        lines += ["", f"Cycles failed to replay: {payload['n_failed']} (excluded from every number above)"]
        lines += [f"  {f['cycle_ts']}  {f['error']}" for f in payload["failures"]]
    return "\n".join(lines)


def accumulation_report(
    records: list[CycleRecord],
    reader: Reader,
    minimums: dict[str, tuple[float, float]],
    navs: list[float],
    *,
    fetched_at: str,
    config: CrossfreqSystemConfig | None = None,
) -> tuple[str, dict]:
    """Replay every record and render the drift the venue minimums impose, as a function of NAV.

    A record whose replay fails is named and counted, never silently dropped -- a missing cycle
    would break the accumulation chain below it with nothing on the page to say so.
    """
    stages: list[CycleStages] = []
    failures: list[dict] = []
    for record in sorted(records, key=lambda r: r.cycle_ts):
        try:
            stages.append(replay_stages(record, reader, config=config))
        except EngineError as exc:
            failures.append({"cycle_ts": record.cycle_ts.isoformat(), "error": str(exc)})
    payload = accumulation_payload(stages, minimums, navs)
    payload["minimums_fetched_at"] = fetched_at
    payload["n_failed"] = len(failures)
    payload["failures"] = failures
    return _render_accumulation(payload), payload
