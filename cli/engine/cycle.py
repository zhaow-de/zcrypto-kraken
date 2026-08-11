"""The shadow cycle core (spec 00041 SS the cycle core): `run_cycle` drives one 4h boundary
end-to-end -- the settle-verify store refresh (bounded by the 25-min reserve inside the ratified
30-min gate window), the raw-series staleness check, per-grid union alignment, snapshot journaling
with journal-relative paths, the record-44 fast build, intended orders against the shadow NAV, and
either the validated schema-v1 success record or the failed-cycle sidecar. Aware-UTC everywhere:
naive datetimes are rejected at the boundary (a naive/aware mix makes `validate_record`'s `!=`
checks silently always-true).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import polars as pl

from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.journal import (
    SCHEMA_VERSION,
    CycleRecord,
    SnapshotEntry,
    from_json,
    snapshot_content_hash,
    to_json,
    validate_record,
)
from cli.engine.store import GRID_INTERVALS, PAIR_KEYS, read_store_series, refresh_store
from cli.logging import get_logger
from cli.ohlc.dataset import write_parquet
from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import fetch_ohlc
from cli.portfolio import build_crossfreq_system_fast

logger = get_logger("engine.cycle")

_H4 = timedelta(hours=4)
# The 25-min retry cutoff leaves a 5-min reserve inside the ratified 30-min gate window: any
# success within the retry window still yields a gate-passable completed_at <= cycle_ts + 30 min.
_REFRESH_RESERVE = timedelta(minutes=25)
_BACKOFF_INITIAL_SECS = 5.0
_BACKOFF_MAX_SECS = 60.0

_sleep = time.sleep  # module-level so tests can stub the backoff wait
_hc_opener = urllib.request.urlopen  # module-level so tests can stub the dead-man's-switch ping

# The engine's per-cycle hook (spec 00069 D5/T4): `run()` installs this UNCONDITIONALLY -- it no
# longer depends on ZCRYPTO_METRICS_PORT, because the sink now also writes the execution ledger,
# which is a forensic artifact rather than telemetry and must not vanish when metrics are off.
# Only the gauge updates inside it are conditional on a registry existing.
# None (the default) makes every call below a no-op, so the workstation soak -- and every one-shot
# subcommand (`cycle`, `replay`, `report`, `soak-check`), none of which ever calls
# `set_metrics_sink`, since each is a fresh process -- runs unaffected. That last clause is why a
# one-shot `cycle` journals no execution record; it is registered as a deferral on the phase-6
# build-sequence topic.
_metrics_sink = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def set_metrics_sink(sink) -> None:
    """Install (or clear, with `None`) `run()`'s per-cycle metrics-update hook: called with
    `(CycleResult, completed_at, duration_seconds)` immediately after every completion artifact
    (success record or failed-cycle sidecar) is written."""
    global _metrics_sink
    _metrics_sink = sink


def _update_metrics(result: CycleResult, completed_at: datetime, duration_seconds: float) -> None:
    """Isolation invariant (spec 00069 D5): the CycleResult and its journal artifact are already
    built/written by the time this runs -- a raising sink can never affect either. Mirrors
    `_ping_healthcheck`'s wrap-and-log."""
    if _metrics_sink is None:
        return
    try:
        _metrics_sink(result, completed_at, duration_seconds)
    except Exception:
        logger.exception("metrics sink raised for cycle %s -- continuing", result.cycle_ts.isoformat())


def _ping_healthcheck(success: bool) -> None:
    """The dead-man's-switch ping (spec 00042): once a completion artifact lands, GET
    HEALTHCHECK_URL after the success record, or HEALTHCHECK_URL + "/fail" after the failed-cycle
    sidecar -- no-op when the env var is unset (the workstation soak), one attempt, 10 s timeout,
    ANY exception swallowed via logger.warning; the ping can never affect the CycleResult. The
    third completion path is pinned by design: a PROPAGATING exception (poisoned store, disk
    error) pings NOTHING -- the dead-man's switch alerts by silence once period + grace lapse, so
    an alert WITHOUT a preceding /fail ping reads "the node is up but a cycle raised -- read the
    logs, suspect the store", not "the container died"."""
    url = os.environ.get("HEALTHCHECK_URL")
    if not url:
        return
    if not success:
        url += "/fail"
    try:
        with _hc_opener(url, timeout=10):
            pass
    except Exception as exc:
        logger.warning("healthcheck ping failed url=%s error=%s", url, exc)


@dataclass(frozen=True)
class CycleResult:
    """run_cycle's outcome: a success carries record_path/targets/orders/sleeve_gross; a failure
    carries sidecar_path/reason/offending_pairs."""

    status: str  # "success" | "failed"
    cycle_ts: datetime
    record_path: Path | None
    sidecar_path: Path | None
    targets: dict[str, float] | None
    orders: list[dict] | None  # [{asset, side, quantity, notional_eur, price}]
    reason: str | None  # "stale_pair" | "refresh_deadline"
    offending_pairs: tuple[str, ...] | None
    # Per-sleeve gross ("B"/"A1"/"A2" -> sum of absolute positions) at the forming row, for the
    # occupancy gauges. Deliberately NOT part of the journal record: schema v1 is validated and
    # replayed, and this is derivable from the snapshots any replay already reads.
    sleeve_gross: dict[str, float] | None


def _normalize_cycle_ts(cycle_ts: datetime) -> datetime:
    if not isinstance(cycle_ts, datetime) or cycle_ts.tzinfo is None:
        raise EngineError(
            f"cycle_ts must be an aware datetime, got {cycle_ts!r} -- a naive/aware mix makes "
            "validate_record's != checks silently always-true"
        )
    normalized = cycle_ts.astimezone(timezone.utc)
    if normalized.hour % 4 or normalized.minute or normalized.second or normalized.microsecond:
        raise EngineError(f"cycle_ts must fall exactly on a 4h UTC boundary (00/04/08/12/16/20), got {cycle_ts!r}")
    return normalized


def _aware_clock(clock):
    def read() -> datetime:
        now = clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise EngineError(f"clock must return an aware-UTC datetime, got {now!r}")
        return now.astimezone(timezone.utc)

    return read


def _expected_tails(cycle_ts: datetime) -> dict[int, datetime]:
    """The boundary invariant's expected last stamp per grid: the 4h bar at cycle_ts - 4h, and the
    daily bar at (last midnight <= cycle_ts) - 1d."""
    midnight = cycle_ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return {240: cycle_ts - _H4, 1440: midnight - timedelta(days=1)}


def _settle_pending(store_dir: Path, cycle_ts: datetime) -> dict[str, str]:
    """The pairs whose raw tail still lacks a bar the boundary invariant expects (not yet
    committed). Both grids are checked: at non-midnight boundaries the daily expectation is already
    satisfied by construction, but at a 00:00 boundary the NEW daily bar settles exactly like the
    4h one -- checking only the 4h tail would burn the reserve and journal an avoidable stale_pair
    (the iter-083 task review's catch)."""
    expected = _expected_tails(cycle_ts)
    pending = {}
    for asset, pair_key in PAIR_KEYS.items():
        for interval, want in expected.items():
            ts, _ = read_store_series(store_dir, asset, interval)
            if not ts or ts[-1] != want:
                pending[asset] = pair_key
                break
    return pending


def _refresh_with_settle_verify(store_dir: Path, cycle_ts: datetime, *, fetch_fn, clock) -> tuple[str, ...]:
    """Refresh the store, then settle-verify: a pair whose raw 4h tail lacks the cycle_ts - 4h bar
    re-fetches with bounded backoff (a successful fetch of a not-yet-committed candle is not a
    transport error, so the OHLCError retry alone would never cover it). Transport retries and
    settle retries are both bounded by clock() <= cycle_ts + 25 min. Returns () once every pair has
    settled, or the offending assets when the reserve is exhausted."""
    deadline = cycle_ts + _REFRESH_RESERVE
    pending = dict(PAIR_KEYS)
    delay = _BACKOFF_INITIAL_SECS
    while True:
        try:
            refresh_store(store_dir, pairs=pending, fetch_fn=fetch_fn, clock=clock)
        except OHLCError as exc:
            logger.warning("run_cycle: transport error refreshing the store (%s); retrying", exc)
        else:
            pending = _settle_pending(store_dir, cycle_ts)
            if not pending:
                return ()
            logger.info(
                "run_cycle: %s still lack the bar stamped %s; re-fetching",
                ", ".join(sorted(pending)),
                (cycle_ts - _H4).isoformat(),
            )
        if clock() > deadline:
            offending = tuple(sorted(pending))
            logger.warning("run_cycle: refresh reserve exhausted with %s unsettled", ", ".join(offending))
            return offending
        _sleep(delay)
        delay = min(delay * 2.0, _BACKOFF_MAX_SECS)


def _stale_pairs(raw_series: dict, cycle_ts: datetime) -> tuple[str, ...]:
    """Staleness on each pair's RAW series (own last stamp vs the boundary invariant): the last 4h
    stamp must equal cycle_ts - 4h and the last daily stamp (the last midnight <= cycle_ts) - 1d."""
    expected = _expected_tails(cycle_ts)
    stale = {asset for (asset, interval), (ts, _) in raw_series.items() if not ts or ts[-1] != expected[interval]}
    return tuple(sorted(stale))


def _union_align(raw_series: dict, interval: int) -> tuple[list[datetime], dict[str, list[float | None]]]:
    """One shared calendar per grid -- the union of the pairs' stamps, None closes at absences --
    exactly the shape build_crossfreq_system_fast and replay_cycle require."""
    union_ts = sorted({t for (_, iv), (ts, _) in raw_series.items() if iv == interval for t in ts})
    prices = {}
    for asset in PAIR_KEYS:
        ts, closes = raw_series[(asset, interval)]
        by_ts = dict(zip(ts, closes))
        prices[asset] = [by_ts.get(t) for t in union_ts]
    return union_ts, prices


def _journal_snapshots(journal_dir: Path, cycle_ts: datetime, aligned: dict) -> tuple[SnapshotEntry, ...]:
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
    entries = []
    for interval in GRID_INTERVALS:
        union_ts, prices = aligned[interval]
        for asset in PAIR_KEYS:
            closes = prices[asset]
            rel_path = rel_dir / f"{asset}-{interval}.parquet"
            frame = pl.DataFrame({"ts": union_ts, "close": closes}, schema={"ts": pl.Datetime("us", "UTC"), "close": pl.Float64})
            write_parquet(frame, journal_dir / rel_path)
            entries.append(
                SnapshotEntry(
                    pair=asset,
                    grid=str(interval),
                    n_bars=len(union_ts),
                    first_ts=union_ts[0],
                    last_ts=union_ts[-1],
                    content_hash=snapshot_content_hash(union_ts, closes),
                    path=rel_path.as_posix(),  # relative to journal_dir: journals relocate and still replay
                )
            )
    return tuple(entries)


def _previous_success(journal_dir: Path, cycle_ts: datetime) -> tuple[datetime | None, dict[str, float] | None]:
    """The most recent successfully journaled cycle before cycle_ts -- searching back across failed
    and missing boundaries (sidecars are named failed-cycle-<HH>.json, so the glob never sees them)."""
    best = None
    for path in journal_dir.glob("*/cycle-*.json"):
        try:
            day = datetime.strptime(path.parent.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            boundary = day + timedelta(hours=int(path.stem.removeprefix("cycle-")))
        except ValueError:
            continue
        if boundary < cycle_ts and (best is None or boundary > best[0]):
            best = (boundary, path)
    if best is None:
        return None, None
    return best[0], dict(from_json(best[1].read_text()).final_targets)


def _append_orders(
    config: EngineConfig,
    day_dir: Path,
    cycle_ts: datetime,
    targets: dict[str, float],
    h4_close: dict[str, float | None],
) -> list[dict]:
    """Intended orders: delta = target - previous target (the most recent successful record's; flat
    0 only when none exists), notional = delta * shadow_nav_eur, quantity = notional / the 4h close
    of the bar stamped cycle_ts - 4h. `side` carries delta's sign; quantity and notional_eur are
    magnitudes. Appended to the day's human-readable orders.jsonl under a header line disclosing
    where the previous targets came from (first-cycle flat start, or a crossed gap)."""
    prev_boundary, prev_targets = _previous_success(config.journal_dir, cycle_ts)
    if prev_targets is None:
        note = "first cycle -- no previously journaled targets, the shadow book starts flat"
    elif prev_boundary != cycle_ts - _H4:
        note = f"previous targets cross a gap: the last successful cycle is {prev_boundary.isoformat()}, not cycle_ts - 4h"
    else:
        note = f"previous targets from {prev_boundary.isoformat()}"
    orders = []
    for asset in sorted(targets):
        delta = targets[asset] - (prev_targets or {}).get(asset, 0.0)
        if delta == 0.0:
            continue
        price = h4_close[asset]
        notional = delta * config.shadow_nav_eur
        orders.append(
            {
                "asset": asset,
                "side": "buy" if delta > 0 else "sell",
                "quantity": abs(notional) / price,
                "notional_eur": abs(notional),
                "price": price,
            }
        )
    header = {
        "cycle_ts": cycle_ts.isoformat(),
        "previous_cycle_ts": prev_boundary.isoformat() if prev_boundary else None,
        "note": note,
    }
    lines = [json.dumps(header)] + [json.dumps(order) for order in orders]
    with (day_dir / "orders.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return orders


def _failed(
    day_dir: Path,
    cycle_ts: datetime,
    started_at: datetime,
    clock,
    reason: str,
    offending: tuple[str, ...],
) -> CycleResult:
    """The failed-cycle sidecar: a shape alongside -- not a change to -- schema v1, written WITHOUT
    validate_record (which by design can never pass for a failure)."""
    completed_at = clock()
    payload = {
        "cycle_ts": cycle_ts.isoformat(),
        "attempted_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "reason": reason,
        "offending_pairs": list(offending),
    }
    day_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = day_dir / f"failed-cycle-{cycle_ts:%H}.json"
    sidecar_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _ping_healthcheck(False)
    logger.warning("run_cycle: %s failed (%s: %s); sidecar at %s", cycle_ts.isoformat(), reason, ", ".join(offending), sidecar_path)
    result = CycleResult(
        status="failed",
        cycle_ts=cycle_ts,
        record_path=None,
        sidecar_path=sidecar_path,
        targets=None,
        orders=None,
        reason=reason,
        offending_pairs=offending,
        sleeve_gross=None,  # no build ran, so the book's composition this boundary is unknown
    )
    _update_metrics(result, completed_at, (completed_at - started_at).total_seconds())
    return result


def run_cycle(cycle_ts: datetime, *, config: EngineConfig, fetch_fn=fetch_ohlc, clock=_utc_now) -> CycleResult:
    """Run one shadow cycle at the 4h boundary `cycle_ts` (spec 00041 SS the cycle core, steps 1-8).

    1. Settle-verify refresh of the store, transport + settle retries bounded by cycle_ts + 25 min;
       exhausting the reserve writes a failed-cycle sidecar (reason "refresh_deadline"). 2. Staleness
    on each pair's raw series vs the boundary invariant; a stale pair writes a sidecar (reason
    "stale_pair") and skips the build; the fresh series are then union-aligned per grid. 3. Snapshot
    parquets journaled under <YYYY-MM-DD>/snapshots/cycle-<HH>/, manifest paths relative to
    journal_dir, hashes via the one shared snapshot_content_hash. 4. build_crossfreq_system_fast
    (default config) -> the newest-row final_targets. 5. Intended orders vs the most recent
    successful record's targets, appended to the day's orders.jsonl. 6. The schema-v1 CycleRecord,
    validated before write, at <YYYY-MM-DD>/cycle-<HH>.json.

    cycle_ts must be aware and on the 4h UTC grid (normalized to UTC; naive raises EngineError), and
    the injected clock must return aware datetimes. A store data-integrity failure (refresh_store's
    EngineError -- poisoned tail / catastrophic staleness) propagates: its documented recovery is
    `zcrypto engine seed`, not a per-cycle retry.
    """
    cycle_ts = _normalize_cycle_ts(cycle_ts)
    read_clock = _aware_clock(clock)
    started_at = read_clock()
    day_dir = config.journal_dir / f"{cycle_ts:%Y-%m-%d}"

    # 1. Settle-verify refresh, bounded by the 25-min reserve.
    offending = _refresh_with_settle_verify(config.store_dir, cycle_ts, fetch_fn=fetch_fn, clock=read_clock)
    if offending:
        return _failed(day_dir, cycle_ts, started_at, read_clock, "refresh_deadline", offending)

    # 2. Staleness on the RAW series first, then union-align per grid.
    raw_series = {(a, iv): read_store_series(config.store_dir, a, iv) for a in PAIR_KEYS for iv in GRID_INTERVALS}
    stale = _stale_pairs(raw_series, cycle_ts)
    if stale:
        return _failed(day_dir, cycle_ts, started_at, read_clock, "stale_pair", stale)
    aligned = {interval: _union_align(raw_series, interval) for interval in GRID_INTERVALS}

    # 3. Journal the union-aligned snapshots.
    entries = _journal_snapshots(config.journal_dir, cycle_ts, aligned)

    # 4. Build (default config) -> the newest-row targets.
    daily_ts, daily_prices = aligned[1440]
    h4_ts, h4_prices = aligned[240]
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts)
    targets = {asset: series[result.n_periods] for asset, series in result.final_targets.items()}
    # The book's sleeve composition at the same forming row: which of the three fixed-1/3 sleeves
    # is actually carrying exposure. Two have been flat for months, so a re-arming roughly triples
    # gross -- the occupancy gauges exist so that is announced rather than discovered.
    sleeve_gross = {
        name: sum(abs(book[asset][result.n_periods]) for asset in book) for name, book in result.sleeve_positions.items()
    }

    # 5. Intended orders vs the most recent successfully journaled targets.
    orders = _append_orders(config, day_dir, cycle_ts, targets, {a: h4_prices[a][-1] for a in h4_prices})

    # 6. The validated success record.
    completed_at = read_clock()
    record = CycleRecord(
        schema_version=SCHEMA_VERSION,
        cycle_ts=cycle_ts,
        snapshots=entries,
        final_targets=targets,
        started_at=started_at,
        completed_at=completed_at,
        code_version=version("zcrypto"),
        builder_path="fast",
    )
    validate_record(record)
    record_path = day_dir / f"cycle-{cycle_ts:%H}.json"
    record_path.write_text(to_json(record) + "\n")
    _ping_healthcheck(True)
    logger.info("run_cycle: %s journaled (%d snapshots, %d order(s))", cycle_ts.isoformat(), len(entries), len(orders))
    cycle_result = CycleResult(
        status="success",
        cycle_ts=cycle_ts,
        record_path=record_path,
        sidecar_path=None,
        targets=targets,
        orders=orders,
        reason=None,
        offending_pairs=None,
        sleeve_gross=sleeve_gross,
    )
    _update_metrics(cycle_result, completed_at, (completed_at - started_at).total_seconds())
    return cycle_result
