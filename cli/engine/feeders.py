"""Read-only measurements over the journaled shadow cycles: `decompose_report` attributes a cycle's
gross across the pipeline's stages, `accumulation_report` measures the drift floor Kraken's venue
minimums impose. Both go through `replay_stages`, which proves each recomputed stage against the
builder's own output, so a builder change raises instead of rendering a silently wrong table."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from cli.engine.cycle import _expand_to_basket, select_model_inputs
from cli.engine.errors import EngineError
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, validate_record
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, apply_whole_book_limits, build_crossfreq_system_fast
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
    # After the §10 whole-book limits, before the governor multiply -- `_check_stage_identity` enforces
    # `final == multiplier * limited`; without this stage the table charges the limits' share to the governor.
    limited: dict[str, float]
    final: dict[str, float]
    multiplier: float
    closes: dict[str, float]  # the 4h close used for the forming row, per asset
    cap_bound: bool
    # The NAV this cycle priced against, when the record journaled one (T0150); None otherwise, where
    # `realized_drift` falls back to the caller's scalar.
    nav: float | None = None


def stage_grosses(sleeve_positions: dict[str, dict[str, float]]) -> dict[str, float]:
    """Gross (sum of absolute positions) for each sleeve."""
    return {name: sum(abs(v) for v in book.values()) for name, book in sleeve_positions.items()}


def cancellation_ratio(sleeve_positions: dict[str, dict[str, float]]) -> tuple[float, float, float]:
    """Return `(ratio, combined_gross, mean_sleeve_gross)`, the ratio being how much of the sleeves'
    exposure survives the 1/3 combination -- which nets opposing positions asset by asset, so the
    combined gross is NOT the mean of the sleeve grosses. NaN on a flat book (0/0), since reporting
    1.0 there would claim an agreement the cycle never demonstrated."""
    assets = {a for book in sleeve_positions.values() for a in book}
    third = 1 / 3
    combined_gross = sum(abs(sum(third * book.get(a, 0.0) for book in sleeve_positions.values())) for a in assets)
    grosses = stage_grosses(sleeve_positions)
    mean_sleeve_gross = sum(grosses.values()) / len(grosses) if grosses else 0.0
    ratio = combined_gross / mean_sleeve_gross if mean_sleeve_gross else math.nan
    return ratio, combined_gross, mean_sleeve_gross


def _check_stage_identity(multiplier: float, limited: dict[str, float], final: dict[str, float], *, cycle_ts) -> None:
    """Raise unless `multiplier * limited[a] == final[a]` exactly, for every asset -- `limited`, never
    `capped`, or the identity breaks the first time a whole-book limit binds. Exact equality is right,
    not float-fragile: the replay reruns the builder's own arithmetic on the builder's own floats in
    the same order, so any difference means the recomputation genuinely diverged."""
    for a, target in final.items():
        if multiplier * limited[a] != target:
            raise EngineError(
                f"stage identity broken for asset={a!r} at cycle_ts={cycle_ts}: "
                f"multiplier*limited={multiplier * limited[a]!r} != builder final_targets={target!r} -- "
                "the recomputed combination, cap or whole-book limit no longer matches the builder"
            )


def replay_stages(record: CycleRecord, reader: Reader, *, config: CrossfreqSystemConfig | None = None) -> CycleStages:
    """Rebuild one journaled cycle and return its forming-row book at every pipeline stage, BASE-keyed whatever the
    record's schema, since `accumulation_payload` looks its floors up by base. Both schemas rebuild here (spec 00094
    D2/D3): a schema-2 record's full symbols reach the builder only through `select_model_inputs` -- imported from the
    cycle, never copied, so a replay cannot diverge -- since raw they raise a `PortfolioError` no per-record catch holds."""
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

    if record.schema_version == 1:
        model_daily_ts, model_daily = daily_ts, daily_prices
        model_h4_ts, model_h4 = h4_ts, h4_prices
    else:
        model_daily_ts, model_daily = select_model_inputs(by_grid["1440"])
        model_h4_ts, model_h4 = select_model_inputs(by_grid["240"])

    result = build_crossfreq_system_fast(model_daily, model_daily_ts, model_h4, model_h4_ts, config=c)
    n = result.n_periods

    sleeves = {name: {a: result.sleeve_positions[name][a][n] for a in c.assets} for name in SLEEVES}
    third = 1 / 3
    # The builder's own chained-add expression, NOT sum(): since 3.12 sum() compensates (Neumaier) and
    # differs by an ulp, and the identity below compares exactly -- a sum() here fires on correct cycles.
    combined = {a: third * sleeves["B"][a] + third * sleeves["A1"][a] + third * sleeves["A2"][a] for a in c.assets}
    # The forming row replays as a one-element series: both stacks take {asset: series}, and every limit is per-bar.
    capped_series = apply_position_caps({a: [combined[a]] for a in c.assets}, long_cap=c.long_cap, short_cap=c.short_cap)
    limited_series = apply_whole_book_limits(capped_series)
    capped = {a: capped_series[a][0] for a in c.assets}
    limited = {a: limited_series[a][0] for a in c.assets}
    multiplier = result.multipliers[n]
    final = {a: result.final_targets[a][n] for a in c.assets}

    _check_stage_identity(multiplier, limited, final, cycle_ts=record.cycle_ts)

    # The journal identity, which the internal one structurally cannot catch: a self-consistent rebuild
    # that diverged from what the engine traded would agree with itself. Compared in the key space the
    # RECORD was written in, so a schema-2 record's twelve symbols meet the cycle's own expansion.
    journaled_space = final if record.schema_version == 1 else _expand_to_basket(final)
    if set(journaled_space) != set(record.final_targets):
        raise EngineError(
            f"rebuilt asset set differs from the journaled one at cycle_ts={record.cycle_ts}: "
            f"{sorted(set(journaled_space) ^ set(record.final_targets))}"
        )
    for a, journaled in record.final_targets.items():
        if journaled_space[a] != journaled:
            raise EngineError(
                f"replay disagrees with the journal for asset={a!r} at cycle_ts={record.cycle_ts}: "
                f"rebuilt={journaled_space[a]!r} != journaled={journaled!r} -- this cycle's rebuild does not "
                "describe the book the engine traded"
            )

    closes = {}
    for a in c.assets:
        series = model_h4[a]
        value = series[-1]
        if value is None:
            raise EngineError(f"the forming row's close is missing for asset={a!r} at cycle_ts={record.cycle_ts}")
        closes[a] = float(value)

    return CycleStages(
        cycle_ts=record.cycle_ts,
        sleeve_positions=sleeves,
        combined=combined,
        capped=capped,
        limited=limited,
        final=final,
        multiplier=multiplier,
        closes=closes,
        cap_bound=any(abs(capped[a] - combined[a]) > 1e-15 for a in c.assets),
        # The number a human bands and the number the engine trips on must come from the same NAV
        # (`executor._stage` carries it for that reason); omitting it bands the report at the LIVE value.
        nav=record.nav,
    )


def _median(values: list[float]) -> float:
    """Median of the non-NaN values, NaN when none remain."""
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
    "limited_gross",
    "limited_ratio",
    "multiplier",
    "governed_ratio",
    "final_gross",
)


def decompose_payload(stages: list[CycleStages]) -> dict:
    """Per-cycle attribution rows plus their aggregates. Pure -- no I/O, no replay.

    Each consecutive-stage ratio is carried PER CYCLE and aggregated as the median of those per-cycle
    values, never as a ratio of the stage medians, which divides two numbers from different cycles."""
    rows = []
    for s in stages:
        ratio, combined_gross, mean_sleeve_gross = cancellation_ratio(s.sleeve_positions)
        capped_gross = sum(abs(v) for v in s.capped.values())
        limited_gross = sum(abs(v) for v in s.limited.values())
        # Denominator is the BUILDER's combined book, not `cancellation_ratio`'s sleeve-side
        # recomputation: both grosses must be summed off the same floats, or an unbound cycle reports
        # gross growing THROUGH the caps and a float-flat book divides one ulp-scale gross by another.
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
                "limited_gross": limited_gross,
                # Same-floats rule as capped_ratio: both grosses come off the builder's own books.
                "limited_ratio": limited_gross / capped_gross if capped_gross else math.nan,
                "multiplier": s.multiplier,
                # `final` is multiplier * the LIMITED book, so this is the governor's own share and nothing else.
                "governed_ratio": s.multiplier,
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
        f"{'capped':>8} {'limited':>8} {'mult':>5} {'final':>8} {'act':>3} {'cap?':>4}"
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
            f"{_pct(r['capped_gross'])} {_pct(r['limited_gross'])} {_ratio(r['multiplier'])} {_pct(r['final_gross'])} "
            f"{r['n_active']:>3} {'yes' if r['cap_bound'] else 'no':>4}"
        )
    m = payload["median"]
    lines.append("-" * len(header))
    lines.append(
        f"{'MEDIAN':<16} {'':>8} {'':>8} {'':>8} "
        f"{_pct(m['combined_gross'])} {_ratio(m['cancellation_ratio'])} "
        f"{_pct(m['capped_gross'])} {_pct(m['limited_gross'])} {_ratio(m['multiplier'])} {_pct(m['final_gross'])} "
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
        f"  capped -> limited         {_ratio(m['limited_ratio'])}   fraction left by the whole-book limits",
        f"  limited -> final          {_ratio(m['governed_ratio'])}   fraction left by the volatility governor (its multiplier)",
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

    A record whose replay fails is named and counted, never silently dropped: a missing cycle would
    bias every aggregate below it with nothing on the page to say so."""
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
    """95th percentile by nearest rank -- always an OBSERVED value, never interpolated; NaN is dropped
    and an empty input gives NaN, as in `_median`."""
    clean = sorted(v for v in values if not math.isnan(v))
    if not clean:
        return math.nan
    return clean[math.ceil(0.95 * len(clean)) - 1]


def load_minimums(path: Path) -> tuple[dict[str, tuple[float, float]], str]:
    """Per-asset `(ordermin_base, costmin)` for the EUR book, plus the snapshot's fetched_at stamp. From
    the snapshot's normalised `universe`, never `raw.assetpairs` where Kraken spells DOGE `XDG/EUR` and
    BTC `XBT/EUR`; the `quote == "EUR"` filter is load-bearing, since `universe` also carries ETH/BTC and
    SOL/BTC, which key the same bases with a costmin denominated in BTC."""
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
    """Mean drift per ISO week, with each week's cycle count and an incompleteness flag. No weekly p95,
    deliberately (spec 00081 D6): over a window this thin a p95 is the maximum wearing a percentile's
    name, and this number becomes a live-trading gate band, so the weeks are read one by one instead."""
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
    """Replay the accumulate-until-placeable policy at each NAV -- pure, no I/O and no replay. Held state
    is in BASE UNITS (spec 00081 D4), since in EUR a pure price move would report zero drift; the two
    floors are INDEPENDENT gates, a quantity and euros, never a max over mixed units; and each NAV prices
    the whole window, so a drifting one cannot fold return into a venue-minimum measurement."""
    bad_navs = [n for n in navs if not math.isfinite(n) or n <= 0]
    if bad_navs:
        raise EngineError(
            f"NAV must be finite and positive, got {bad_navs} -- zero divides, and a negative one "
            "silently signs every drift_bps that the reported median and p95 are read from"
        )
    # The policy carries state across cycles: an out-of-order stage accumulates against the wrong held quantity.
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
                # A measurement, not execution logic: these `>=` comparisons are float-exact, so a
                # delta landing on a floor is representation-dependent -- harmless over journaled
                # data, not at a venue about to accept or reject on that same boundary.
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

    A record whose replay fails is named and counted, never silently dropped: a missing cycle would
    break the accumulation chain below it with nothing on the page to say so."""
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
