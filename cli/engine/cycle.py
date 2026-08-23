"""The shadow cycle core (spec 00041 SS the cycle core): `run_cycle` drives one 4h boundary
end-to-end -- the settle-verify store refresh (bounded by the 25-min reserve inside the ratified
30-min gate window), the raw-series staleness check, per-grid union alignment, snapshot journaling
with journal-relative paths, the record-44 fast build, intended orders against the shadow NAV, and
either the validated success record (the current `SCHEMA_VERSION`) or the failed-cycle sidecar.
Aware-UTC everywhere: naive datetimes are rejected at the boundary (a naive/aware mix makes
`validate_record`'s `!=` checks silently always-true).

Twelve legs, ten of them modelled (spec 00094 D1/D2). The store, the journaled snapshots, the
targets and the orders all key by full symbol; the MODEL does not widen. `select_model_inputs`
contracts the twelve-symbol store down to the ten `/EUR` legs on their own calendar before the
builder runs, and `_expand_to_basket` maps the ten base-keyed outputs back onto the twelve-symbol
basket with `ETH/BTC` and `SOL/BTC` at exactly `0.0`. Both functions are shared, not copied: the
gate replay and the soak's loaders import them from here.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.instruments import INSTRUMENT_IDS
from cli.engine.journal import (
    SCHEMA_VERSION,
    CycleRecord,
    SnapshotEntry,
    from_json,
    snapshot_content_hash,
    to_json,
    validate_record,
)
from cli.engine.store import BASKET, GRID_INTERVALS, PAIR_KEYS, read_store_series, refresh_store
from cli.logging import get_logger
from cli.ohlc.dataset import write_parquet
from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import fetch_ohlc
from cli.portfolio import build_crossfreq_system_fast
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, apply_whole_book_limits
from cli.risk import apply_position_caps

if TYPE_CHECKING:
    # Typing only: cli.engine.venuestate imports nautilus_trader at module level (~1s), and this
    # module is imported eagerly by cli.engine.command -- `zcrypto --help` must never pay that cost.
    # The actual runtime imports (write_venue_record, runtime_concordance) are local to
    # _record_venue_state, paid only when a cycle with venue truth actually runs.
    from cli.engine.venuestate import ConcordanceVerdict, VenueState

logger = get_logger("engine.cycle")

_H4 = timedelta(hours=4)
# The 25-min retry cutoff leaves a 5-min reserve inside the ratified 30-min gate window: any
# success within the retry window still yields a gate-passable completed_at <= cycle_ts + 30 min.
_REFRESH_RESERVE = timedelta(minutes=25)
_BACKOFF_INITIAL_SECS = 5.0
_BACKOFF_MAX_SECS = 60.0

_sleep = time.sleep  # module-level so tests can stub the backoff wait
_hc_opener = urllib.request.urlopen  # module-level so tests can stub the dead-man's-switch ping

# The model's universe: the ten `/EUR` members of the ratified basket, derived from BASKET so a
# basket change moves exactly one place. The two `/BTC` legs are deliberately absent -- no sleeve
# ever sees them (spec 00094 D1).
_MODEL_SYMBOLS: tuple[str, ...] = tuple(symbol for symbol in BASKET if symbol.endswith("/EUR"))

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


def _code_version() -> str:
    """`version("zcrypto")`, plus `+{first 12 chars of ZCRYPTO_BUILD_REVISION}` when that env var is
    non-empty (T0130, D8) -- the cycle record and the venue record both take their value from this
    one function, so the two artifacts never disagree. The env var is populated by a build arg
    (00089 Task 8); until then it is unset and this is bare."""
    base = version("zcrypto")
    revision = os.environ.get("ZCRYPTO_BUILD_REVISION")
    if not revision:
        return base
    return f"{base}+{revision[:12]}"


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
    # The venue-truth summary for this boundary (00089 Task 4): {"loaded", "expected", "failures",
    # "snapshot_at"}, or None when no VenueState was available. In-memory only, for the metrics sink
    # -- like sleeve_gross, deliberately NOT part of the journal record; the full snapshot lives in
    # venue-<HH>.json. Defaults to None so call sites built before this field existed keep working.
    venue: dict | None = None
    # Whether any wired whole-book limit moved this boundary's intended book (T0121). None means
    # "no answer": a failed cycle ran no build, and a False there would read as a measured quiet
    # book. In-memory only, like sleeve_gross. Defaults to None so call sites built before this
    # field existed keep working.
    limit_bound: bool | None = None


def _limits_bound(result) -> bool:
    """True iff the wired limit stack (caps -> gross -> net band -> margin floor; the governor is a
    returns overlay, deliberately outside) moved the combined book at the forming row. Mirrors
    cli/engine/feeders.py::replay_stages' recomputation exactly -- chained adds, one-element series."""
    c = CrossfreqSystemConfig()
    n = result.n_periods
    third = 1 / 3
    sleeves = {name: {a: result.sleeve_positions[name][a][n] for a in c.assets} for name in ("B", "A1", "A2")}
    combined = {a: third * sleeves["B"][a] + third * sleeves["A1"][a] + third * sleeves["A2"][a] for a in c.assets}
    limited = apply_whole_book_limits(
        apply_position_caps({a: [combined[a]] for a in c.assets}, long_cap=c.long_cap, short_cap=c.short_cap)
    )
    return any(limited[a][0] != combined[a] for a in c.assets)


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
    for symbol, pair_key in PAIR_KEYS.items():
        for interval, want in expected.items():
            ts, _ = read_store_series(store_dir, symbol, interval)
            if not ts or ts[-1] != want:
                pending[symbol] = pair_key
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
    stale = {symbol for (symbol, interval), (ts, _) in raw_series.items() if not ts or ts[-1] != expected[interval]}
    return tuple(sorted(stale))


def _union_align(raw_series: dict, interval: int) -> tuple[list[datetime], dict[str, list[float | None]]]:
    """One shared calendar per grid over ALL TWELVE symbols -- the union of their stamps, None
    closes at absences. This is the JOURNALED evidence shape (and what replay_cycle's assembly
    requires); the builder's own inputs are the narrower `select_model_inputs` contraction."""
    union_ts = sorted({t for (_, iv), (ts, _) in raw_series.items() if iv == interval for t in ts})
    prices = {}
    for symbol in PAIR_KEYS:
        ts, closes = raw_series[(symbol, interval)]
        by_ts = dict(zip(ts, closes))
        prices[symbol] = [by_ts.get(t) for t in union_ts]
    return union_ts, prices


def select_model_inputs(
    series: dict[str, tuple[list[datetime], list[float | None]]],
) -> tuple[list[datetime], dict[str, list[float | None]]]:
    """The builder-input contraction (spec 00094 D2) -- ONE implementation, three consumers: this
    cycle, the gate replay, and the soak's parallel loaders. Never copied.

    `series` is ONE grid's `{symbol: (ts, closes)}`. Returns `(union_ts, {base: closes})` covering
    the ten `/EUR` legs only, re-keyed by base for `CrossfreqSystemConfig`.

    The calendar is unioned over THE TEN EUR PAIRS ONLY: a stamp enters it iff at least one EUR leg
    carries a non-None close there. A `/BTC` stamp the EUR legs lack must never shift an EUR
    SMA/stdev window -- today the `/BTC` stamps happen to be subsets of the EUR union, but nothing
    constructs that, so this does.

    Defining the calendar by "some EUR leg has data" rather than by the input's raw stamp lists is
    also what makes it idempotent over union alignment: raw store series and the SAME series already
    aligned onto the twelve-symbol union (where every EUR leg carries None at a `/BTC`-only stamp)
    produce identical output. The cycle reads the store and the replay reads the journal -- they
    must reach the builder with the same grid or every replay is a mismatch.
    """
    missing = [symbol for symbol in _MODEL_SYMBOLS if symbol not in series]
    if missing:
        raise EngineError(f"select_model_inputs: the model's EUR leg(s) {missing} are absent from the series map")
    present = {symbol: series[symbol] for symbol in _MODEL_SYMBOLS}
    union_ts = sorted({t for ts, closes in present.values() for t, close in zip(ts, closes) if close is not None})
    prices = {}
    for symbol, (ts, closes) in present.items():
        by_ts = dict(zip(ts, closes))
        prices[symbol.split("/")[0]] = [by_ts.get(t) for t in union_ts]
    # The base re-key above is lossy by construction: only `_MODEL_SYMBOLS`' `/EUR` filter keeps two
    # quotes of one base apart. Were it ever widened to admit `ETH/BTC`, `prices["ETH"]` would be
    # overwritten silently and the survivor's ten keys would still satisfy `_validate_grid` -- a
    # wrong grid the builder cannot refuse. Three consumers share this seam; one line closes it.
    assert len(prices) == len(_MODEL_SYMBOLS), f"select_model_inputs: two model symbols share a base -- {sorted(present)}"
    return union_ts, prices


def _expand_to_basket(model_targets: dict[str, float]) -> dict[str, float]:
    """Base-keyed ten in, symbol-keyed twelve out (spec 00094 D1): each model base carries its value
    onto `<base>/EUR`, and every BASKET member the model produced nothing for -- `ETH/BTC`,
    `SOL/BTC` -- emits exactly `0.0`.

    The widening is STRUCTURAL and strictly downstream of the model: no sleeve computes a `/BTC`
    weight, so a traded basket of twelve carries no strategy change. A model base with no
    `<base>/EUR` in BASKET raises rather than being dropped -- a silently discarded target is a
    position the engine believes it holds and never trades.
    """
    expanded = dict.fromkeys(BASKET, 0.0)
    for base, value in model_targets.items():
        symbol = f"{base}/EUR"
        if symbol not in expanded:
            raise EngineError(f"_expand_to_basket: model asset {base!r} has no {symbol!r} leg in the ratified basket")
        expanded[symbol] = value
    return expanded


def symbol_keyed_targets(record: CycleRecord) -> dict[str, float]:
    """A journaled record's `final_targets` in the CURRENT symbol key space: schema 2 as-is, schema 1
    (base-keyed, `"BTC"`) mapped `base -> base/EUR`. THE cross-schema normalizer -- the cycle's
    previous-targets read and the soak's record loaders share this one.

    Without it the first schema-2 cycle after the deploy reads a base-keyed predecessor, every
    `.get(symbol, 0.0)` misses, and the engine writes a full from-flat rebalance into orders.jsonl
    and the exec ledger -- silently, because the gate never reads orders.

    The GATE deliberately does not use this (spec 00094 D3): each record replays and compares in its
    own native key space, and normalizing v1 replay output against a base-keyed record would turn
    every v1 record into a structural mismatch.

    No BASKET-membership check: this reads a PREDECESSOR, not the current basket, so a v1 record
    naming an asset since dropped must stay readable. Callers iterate the current basket, which
    leaves such a key simply unconsulted -- exactly the pre-re-key behaviour.
    """
    if record.schema_version == 1:
        return {f"{asset}/EUR": value for asset, value in record.final_targets.items()}
    return dict(record.final_targets)


def _journal_snapshots(journal_dir: Path, cycle_ts: datetime, aligned: dict) -> tuple[SnapshotEntry, ...]:
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
    entries = []
    for interval in GRID_INTERVALS:
        union_ts, prices = aligned[interval]
        for symbol in PAIR_KEYS:
            closes = prices[symbol]
            # The '/' is replaced, never kept: it would turn each symbol into a subdirectory and the
            # day's snapshots/ must stay flat. Nothing parses these names -- the NAS journal pull is
            # `rsync -a` (cli/archive/command.py::_run_rsync) and every reader follows the record's
            # own `entry.path` string.
            rel_path = rel_dir / f"{symbol.replace('/', '-')}-{interval}.parquet"
            frame = pl.DataFrame({"ts": union_ts, "close": closes}, schema={"ts": pl.Datetime("us", "UTC"), "close": pl.Float64})
            write_parquet(frame, journal_dir / rel_path)
            entries.append(
                SnapshotEntry(
                    pair=symbol,
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
    and missing boundaries (sidecars are named failed-cycle-<HH>.json, so the glob never sees them).
    Its targets come back symbol-keyed whatever schema wrote them."""
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
    # Normalized to the current symbol key space: a schema-1 predecessor is base-keyed, and an
    # un-normalized read makes every delta below a from-flat rebalance (symbol_keyed_targets).
    return best[0], symbol_keyed_targets(from_json(best[1].read_text()))


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
    where the previous targets came from (first-cycle flat start, or a crossed gap).

    Emission is delta-driven, which is what keeps the two `/BTC` legs structurally silent: their
    target is `0.0` by construction and their previous target is `0.0` too, so no row is ever
    written for them. `h4_close` is each symbol's own quote-currency close, so `notional_eur` is
    EUR-true only for the ten `/EUR` legs -- whoever first sizes a real `/BTC` order owns the
    conversion (`cli.engine.instruments.fx_eur_notional`, spec 00094 D4/D5)."""
    prev_boundary, prev_targets = _previous_success(config.journal_dir, cycle_ts)
    if prev_targets is None:
        note = "first cycle -- no previously journaled targets, the shadow book starts flat"
    elif prev_boundary != cycle_ts - _H4:
        note = f"previous targets cross a gap: the last successful cycle is {prev_boundary.isoformat()}, not cycle_ts - 4h"
    else:
        note = f"previous targets from {prev_boundary.isoformat()}"
    orders = []
    for symbol in sorted(targets):
        delta = targets[symbol] - (prev_targets or {}).get(symbol, 0.0)
        if delta == 0.0:
            continue
        price = h4_close[symbol]
        notional = delta * config.shadow_nav_eur
        orders.append(
            {
                "asset": symbol,
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


def _record_venue_state(config: EngineConfig, cycle_ts: datetime, venue_state: VenueState | None) -> dict | None:
    """Journal this boundary's venue-truth evidence FIRST (00089 D7), before any target computation
    below -- a cycle that dies later in the settle-verify refresh or the build still leaves this
    record behind. `venue_state` is READ-ONLY evidence: consulted only here, for the ledger and the
    CycleResult summary the metrics sink reads -- never for targets or orders.

    `venue_state=None` normally journals an error record -- EXCEPT when this boundary's
    venue-<HH>.json already reads status "ok". That record is exactly the write-first design's own
    evidence: the CLI's `cycle --replace` (cli/engine/command.py) calls run_cycle with no
    venue_state at all, so without this guard a manual re-run of an already-journaled boundary would
    silently clobber the live engine's own soak evidence for it -- or, worse, destroy a crashed
    boundary's only surviving evidence by re-running it (without --replace) once the venue record is
    the sole artifact on disk. Left alone in that case; the return value stays None either way, since
    no fresh snapshot was taken this cycle.

    Local imports: cli.engine.venueledger pulls in cli.engine.venuestate, which imports
    nautilus_trader (~1s) at module level -- deferred to here (paid only when a cycle actually runs)
    so cli.engine.command's module-level import of this module stays nautilus-free (`zcrypto --help`).
    """
    from cli.engine.venueledger import read_venue_record, venue_record_path, write_venue_record
    from cli.engine.venuestate import runtime_concordance

    code_version = _code_version()
    if venue_state is None:
        existing_path = venue_record_path(config.journal_dir, cycle_ts)
        if existing_path.exists() and read_venue_record(existing_path).get("status") == "ok":
            logger.info("run_cycle: venue_state=None but %s already reads status 'ok' -- leaving it alone", existing_path)
            return None
        write_venue_record(
            config.journal_dir,
            cycle_ts,
            state=None,
            concordance=None,
            code_version=code_version,
            error="no venue snapshot available for this cycle",
        )
        return None
    verdict: ConcordanceVerdict = runtime_concordance(venue_state)
    write_venue_record(config.journal_dir, cycle_ts, state=venue_state, concordance=verdict, code_version=code_version)
    return {
        "loaded": len(venue_state.instruments),
        "expected": len(INSTRUMENT_IDS),  # derived, never a literal -- a basket re-ratification moves one place
        "failures": len(verdict.failures),
        "snapshot_at": venue_state.snapshot_at.isoformat(),
    }


def _narrow_held(venue_state: VenueState | None) -> dict[str, float] | None:
    """The venue's book narrowed to the model's BASE key space over the /EUR legs.

    None whenever the venue cannot supply a usable book -- a failed read, or a non-finite quantity.
    Absence is the honest answer there; a zeroed book would read as FLAT, which is a real position.
    A non-finite quantity must not become a journaled value: `validate_record` runs AFTER
    `_append_orders`, so refusing it there would leave an orders block with no cycle record behind
    it -- and venue truth never blocks the cycle.
    """
    if venue_state is None:
        return None
    held = {}
    for symbol, qty in venue_state.positions.items():
        if not symbol.endswith("/EUR"):
            # A /BTC leg's base is already carried by that base's /EUR leg; folding it in
            # would double-count.
            continue
        if not math.isfinite(qty):
            logger.warning("run_cycle: venue position for %s is not finite (%r) -- journaling no held book", symbol, qty)
            return None
        held[symbol.split("/")[0]] = qty
    return held


def _failed(
    day_dir: Path,
    cycle_ts: datetime,
    started_at: datetime,
    clock,
    reason: str,
    offending: tuple[str, ...],
    venue: dict | None,
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
        venue=venue,
    )
    _update_metrics(result, completed_at, (completed_at - started_at).total_seconds())
    return result


def run_cycle(
    cycle_ts: datetime,
    *,
    config: EngineConfig,
    fetch_fn=fetch_ohlc,
    clock=_utc_now,
    venue_state: VenueState | None = None,
) -> CycleResult:
    """Run one shadow cycle at the 4h boundary `cycle_ts` (spec 00041 SS the cycle core, steps 1-8).

    0. `venue_state` (00089 Task 4), if given, is run through `runtime_concordance` and journaled to
       venue-<HH>.json FIRST -- before anything below -- so a cycle that dies later still leaves this
    boundary's venue evidence; `venue_state=None` journals an error record instead. Either way
    `venue_state` is READ-ONLY: it is never consulted for targets or orders, only journaled and
    summarized onto `CycleResult.venue`. 1. Settle-verify refresh of the store, transport + settle
    retries bounded by cycle_ts + 25 min; exhausting the reserve writes a failed-cycle sidecar
    (reason "refresh_deadline"). 2. Staleness on each pair's raw series vs the boundary invariant; a
    stale pair writes a sidecar (reason "stale_pair") and skips the build; the fresh series are then
    union-aligned per grid over all twelve symbols. 3. Snapshot parquets journaled under
    <YYYY-MM-DD>/snapshots/cycle-<HH>/, manifest paths relative to journal_dir, hashes via the one
    shared snapshot_content_hash. 4. select_model_inputs contracts to the ten EUR legs on their own
    calendar -> build_crossfreq_system_fast (default config) -> the newest-row targets ->
    _expand_to_basket back onto the twelve symbols, the two /BTC legs at exactly 0.0; the ten bases'
    forming-row closes come off that same contraction for the record, and a missing one raises.
    5. Intended orders vs the most recent successful record's targets (symbol-normalized whatever
    schema wrote them), appended to the day's orders.jsonl. 6. The CycleRecord at the current
    SCHEMA_VERSION, validated before write, at <YYYY-MM-DD>/cycle-<HH>.json -- carries NO venue
    field; the full snapshot lives only in venue-<HH>.json.

    cycle_ts must be aware and on the 4h UTC grid (normalized to UTC; naive raises EngineError), and
    the injected clock must return aware datetimes. A store data-integrity failure (refresh_store's
    EngineError -- poisoned tail / catastrophic staleness) propagates: its documented recovery is
    `zcrypto engine seed`, not a per-cycle retry.
    """
    cycle_ts = _normalize_cycle_ts(cycle_ts)
    read_clock = _aware_clock(clock)
    started_at = read_clock()
    day_dir = config.journal_dir / f"{cycle_ts:%Y-%m-%d}"

    # 0. Venue truth: journaled FIRST, before target computation -- read-only from here on.
    venue = _record_venue_state(config, cycle_ts, venue_state)

    # 1. Settle-verify refresh, bounded by the 25-min reserve.
    offending = _refresh_with_settle_verify(config.store_dir, cycle_ts, fetch_fn=fetch_fn, clock=read_clock)
    if offending:
        return _failed(day_dir, cycle_ts, started_at, read_clock, "refresh_deadline", offending, venue)

    # 2. Staleness on the RAW series first, then union-align per grid.
    raw_series = {(s, iv): read_store_series(config.store_dir, s, iv) for s in PAIR_KEYS for iv in GRID_INTERVALS}
    stale = _stale_pairs(raw_series, cycle_ts)
    if stale:
        return _failed(day_dir, cycle_ts, started_at, read_clock, "stale_pair", stale, venue)
    aligned = {interval: _union_align(raw_series, interval) for interval in GRID_INTERVALS}

    # 3. Journal the union-aligned snapshots.
    entries = _journal_snapshots(config.journal_dir, cycle_ts, aligned)

    # 4. Build (default config) over the TEN EUR legs on their own calendar, then expand the ten
    #    base-keyed outputs onto the twelve-symbol basket (spec 00094 D1/D2). The contraction is fed
    #    the raw store reads; `select_model_inputs` is idempotent over the twelve-symbol alignment
    #    above, so the replay reading the journaled snapshots reaches the builder with this grid.
    model_daily_ts, model_daily = select_model_inputs({s: raw_series[(s, 1440)] for s in PAIR_KEYS})
    model_h4_ts, model_h4 = select_model_inputs({s: raw_series[(s, 240)] for s in PAIR_KEYS})
    # The forming row's close per model base, journaled onto the record below so drift is measurable
    # at a boundary without replaying the cycle.
    #
    # This introduces a NEW refusal onto the trade path -- it does not relocate an existing one. The
    # gate's `replay_cycle` extracts no closes at all, so a cycle with an unusable forming close
    # replays and passes cleanly; only `feeders.replay_stages` refuses, and that is the reports path,
    # on a workstation where a refusal costs nothing. Four reasons the new refusal is right:
    #   * The condition is CORRUPT STORE DATA, not the delisted tail `_dummy_close` tolerates. The
    #     staleness check above has already pinned every leg's ts[-1] == cycle_ts - 4h, so a null
    #     here is a null at a stamp that provably exists -- the builder's tolerance applied to a
    #     condition it was not written for.
    #   * The old code already killed most such cycles anyway, just later and by accident:
    #     `_append_orders` computes `abs(notional) / price` and raises TypeError on a None price
    #     INSIDE the loop, so orders.jsonl was never written. The real behaviour delta is only the
    #     sub-case where the un-priceable asset happens to have exactly zero delta.
    #   * The construction is WHOLE-BOOK -- basket vol target, governor, whole-book limits -- so one
    #     leg's silently-zeroed forming return moves all twelve targets. There is no "eleven good
    #     legs" outcome to preserve.
    #   * The failure is loud and recoverable: `node._invoke_cycle` catches it and leaves the
    #     boundary journal-absent WITH NO SIDECAR, which is exactly the state `startup_action`
    #     re-runs inside [B, B+25 min]; `_ping_healthcheck(True)` never fires, so the dead-man
    #     surfaces it either way.
    #
    # The refusal set is a SUPERSET of validate_record's closes checks, deliberately. Those run at
    # the CycleRecord below -- after _append_orders has already written orders.jsonl -- so a
    # negative or non-finite close caught only there produces the precise state this placement
    # exists to prevent: an orders block with no cycle-<HH>.json behind it, which the next
    # boundary's `_previous_success` silently globs past.
    model_closes = {}
    for base, series in model_h4.items():
        value = series[-1]
        if value is None or not math.isfinite(value) or value <= 0:
            raise EngineError(
                f"the forming row's close is missing or unusable for asset={base!r} at cycle_ts={cycle_ts}: {value!r}"
            )
        model_closes[base] = float(value)
    result = build_crossfreq_system_fast(model_daily, model_daily_ts, model_h4, model_h4_ts)
    targets = _expand_to_basket({base: series[result.n_periods] for base, series in result.final_targets.items()})
    # The book's sleeve composition at the same forming row: which of the three fixed-1/3 sleeves
    # is actually carrying exposure. Two were flat for months; the occupancy gauges exist so a re-arming is
    # announced rather than discovered nine months later. They do NOT tell you gross moved: measured at the
    # 2026-08-22 reversal, the count went 1 -> 3 while the final book rose only x1.15 and then fell below its
    # starting point, because the incumbent sleeve's own gross dropped as the other two armed.
    sleeve_gross = {
        name: sum(abs(book[asset][result.n_periods]) for asset in book) for name, book in result.sleeve_positions.items()
    }
    # Did any §10 whole-book limit actually move that book (T0121). Wrapped because it is telemetry
    # and telemetry may never cost a cycle (spec 00069 D5's isolation invariant): unlike the gross
    # sum above, the limit stack VALIDATES its input and raises on anything non-finite, so an
    # unwrapped call here would turn a journalled-and-fine cycle into a dead one. `None` is the
    # value that already means "no answer".
    try:
        limit_bound = _limits_bound(result)
    except Exception:
        logger.exception("run_cycle: the limit recomputation raised for %s -- reporting no answer", cycle_ts.isoformat())
        limit_bound = None

    # 5. Intended orders vs the most recent successfully journaled targets.
    # Prices come from the TWELVE-symbol alignment, not the model's contraction: every basket leg
    # needs a close, and its last stamp is cycle_ts - 4h for all twelve (the staleness check above).
    _, h4_closes = aligned[240]
    orders = _append_orders(config, day_dir, cycle_ts, targets, {s: h4_closes[s][-1] for s in PAIR_KEYS})

    # 6. The validated success record.
    completed_at = read_clock()
    record = CycleRecord(
        schema_version=SCHEMA_VERSION,
        cycle_ts=cycle_ts,
        snapshots=entries,
        final_targets=targets,
        started_at=started_at,
        completed_at=completed_at,
        code_version=_code_version(),
        builder_path="fast",
        closes=model_closes,
        # T0150: the other two terms a drift measurement needs. NAV is journaled because it sets
        # BOTH halves -- a target is `weight * nav / close` and the drift divides by nav -- so a
        # week scored after a `shadow_nav_eur` change would otherwise be re-scored against a
        # denominator nobody traded under. `held` is the venue's real book, narrowed to the model's
        # BASE key space over the /EUR legs (VenueState is symbol-keyed, and folding a /BTC leg in
        # would double-count that base). None when the venue read failed: absence is the honest
        # answer, where a zeroed book would read as FLAT, which is a real position.
        nav=config.shadow_nav_eur,
        held=_narrow_held(venue_state),
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
        venue=venue,
        limit_bound=limit_bound,
    )
    _update_metrics(cycle_result, completed_at, (completed_at - started_at).total_seconds())
    return cycle_result
