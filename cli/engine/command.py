"""The `zcrypto engine` Typer sub-app (spec 00041). Config errors and EngineErrors surface as clean one-line exits, never
tracebacks; nautilus-trader (~1 s of import time) is imported lazily inside the bodies that need it (`venueledger` carries it too),
so `zcrypto --help` never pays it."""

from __future__ import annotations

import asyncio
import faulthandler
import json
import math
import os
import shutil
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
from prometheus_client import Counter, Gauge

from cli.config import AppConfig, ConfigError, EngineConfig, load_config
from cli.engine.concordance import CycleOutcome, GateStatus, HashMismatchError, compare_targets, evaluate_gate, replay_cycle
from cli.engine.cycle import CycleResult, run_cycle, set_metrics_sink
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.execgate import LEVEL_CODE, ExecutionGate, GateVerdict, write_restart_hold
from cli.engine.execledger import ledgered_plan_ids, read_exec_record, validate_exec_record, write_exec_record
from cli.engine.feeders import (
    CycleStages,
    accumulation_payload,
    accumulation_report,
    decompose_report,
    load_minimums,
    replay_stages,
)
from cli.engine.gate_cache import (
    GateCache,
    due_for_reverification,
    evidence_fingerprint,
    load_cache,
    oldest_verification_age,
    replay_fingerprint,
    save_cache,
)
from cli.engine.instruments import INSTRUMENT_IDS, _floor_to_step
from cli.engine.journal import CycleRecord, SnapshotEntry, from_json
from cli.engine.probeplan import ProbePlanError, parse_plan, plan_refusals
from cli.engine.soak import soak_report
from cli.engine.store import BASKET, GRID_INTERVALS, _store_path, seed_store
from cli.engine.tracking import Fill, cost_blend, extract_fills, read_ledger_export, reconcile_ledger, weekly_tracking
from cli.engine.venue import read_system_status
from cli.logging import get_logger
from cli.obs.metrics import build_registry, metrics_port_from_env, start_metrics_server
from cli.ohlc.dataset import read_parquet
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

logger = get_logger("engine.command")

CANONICAL_DIR = Path("data/ohlc-full")
DEFAULT_NAVS = (500.0, 1000.0, 2500.0, 5000.0, 10000.0)
# The two variables carrying the trade credentials (`engine.env.j2` renders both), named here so a refusal can say WHICH is
# missing without ever touching a value. Duplicated from `cli/engine/node.py` rather than imported: importing them would
# pull nautilus in and defeat this module's lazy import.
_API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
_API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"
_REFDATA_GLOB = "kraken-refdata-*.json"
_urlopen = urllib.request.urlopen  # module-level so tests can stub the gate-export healthcheck ping

engine_app = typer.Typer(
    no_args_is_help=True,
    help="The shadow engine: store seeding, the node, manual cycles, journal replay, the gate report, and gate export.",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _abort(message: str) -> typer.Exit:
    """A clean one-line error (logged, no traceback) + exit code 1; usage: `raise _abort(...)`.

    LOGS rather than `typer.echo`s: the line has to carry a level, or Alloy cannot label it at ingest
    (infra/nas/config.alloy) and the level-based alerting never sees it (T0041)."""
    logger.error(message)
    return typer.Exit(code=1)


def _load_app_config() -> AppConfig:
    try:
        return load_config()
    except ConfigError as exc:
        raise _abort(str(exc)) from exc


def _load_engine_config() -> EngineConfig:
    return _load_app_config().engine


def _parse_at(raw: str) -> datetime:
    try:
        at = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise _abort(f"--at {raw!r} is not an ISO-8601 timestamp") from exc
    if at.tzinfo is None:
        raise _abort(f"--at {raw!r} is naive -- pass an aware timestamp (e.g. 2026-07-10T08:00:00+00:00)")
    at = at.astimezone(timezone.utc)
    if at.hour % 4 or at.minute or at.second or at.microsecond:
        raise _abort(f"--at {raw!r} is off the 4h boundary grid -- cycles run at 00/04/08/12/16/20 UTC exactly")
    if at > _utc_now():
        raise _abort(f"--at {raw!r} has not elapsed yet -- a future cycle would journal a spurious failure")
    return at


def _journal_artifacts(journal_dir: Path, pattern: str, name_glob: str) -> list[tuple[datetime, Path]]:
    """(boundary, path) pairs for `<pattern>/<name_glob>` under the journal, sorted by boundary;
    files whose day-dir/hour names don't parse are skipped (mirrors the cycle core's back-search)."""
    out = []
    for path in journal_dir.glob(f"{pattern}/{name_glob}"):
        try:
            day = datetime.strptime(path.parent.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            boundary = day + timedelta(hours=int(path.stem.rsplit("-", 1)[-1]))
        except ValueError:
            continue
        out.append((boundary, path))
    return sorted(out)


def _snapshot_reader(journal_dir: Path):
    """replay_cycle's reader closure: SnapshotEntry.path is journal-relative, resolved here."""

    def reader(entry: SnapshotEntry) -> tuple[list[datetime], list[float | None]]:
        path = journal_dir / entry.path
        if not path.exists():
            raise EngineJournalError(f"journaled snapshot missing on disk: {path}")
        try:
            frame = read_parquet(path)
            return frame["ts"].to_list(), frame["close"].to_list()
        except Exception as exc:  # a corrupt/truncated parquet (e.g. a partial rsync) is bad evidence, not a crash
            raise EngineJournalError(f"journaled snapshot unreadable: {path}: {exc}") from exc

    return reader


def _sidecar_fields(boundary: datetime, path: Path) -> tuple[datetime, datetime, str]:
    """(cycle_ts, completed_at, reason) from a failed-cycle sidecar, falling back to the
    path-derived boundary when the JSON is unreadable -- the sweep classifies, never crashes."""
    try:
        payload = json.loads(path.read_text())
        cycle_ts = datetime.fromisoformat(payload["cycle_ts"])
        completed_at = datetime.fromisoformat(payload["completed_at"])
        reason = str(payload["reason"])
        offending = ", ".join(payload.get("offending_pairs", []))
        return cycle_ts, completed_at, f"{reason}: {offending}" if offending else reason
    except json.JSONDecodeError, KeyError, TypeError, ValueError, OSError:
        return boundary, boundary, "unreadable sidecar"


@dataclass(frozen=True)
class JournalCounts:
    """_evaluate_journal's per-outcome tallies, in the order `report` echoes them."""

    replayed_ok: int
    mismatches: int
    validation_failures: int
    sidecar_count: int


@dataclass(frozen=True)
class CacheStats:
    """_evaluate_journal's per-run scoring-cache tally (spec 00060 D8): with `cache_path` None, `replayed` counts the full replay
    and the rest read 0/False/None, so a degrading cache reads as degrading rather than as a working one. A forced re-verification
    (spec 00062 D4) counts in `replayed`, never `from_cache` -- its failure is a real gate failure, not a cache event -- and
    `oldest_verification_age` is seconds since the least-recently verified entry in the post-run cache, else None."""

    replayed: int
    from_cache: int
    invalidated: bool
    oldest_verification_age: float | None


_EVALUATE_JOURNAL_REPLAY_PATH = "fast"  # threaded into replay_fingerprint() below (spec 00060 D3)


def _replay_one(record: CycleRecord, reader) -> CycleOutcome:
    """Replay one journaled success record and classify the outcome -- factored out so a cache hit
    and a fresh replay produce the same CycleOutcome shape, from which `_evaluate_journal` derives
    its counters in one place, so neither path can silently undercount."""
    try:
        replayed = replay_cycle(record, reader, path=_EVALUATE_JOURNAL_REPLAY_PATH)
    except HashMismatchError:
        return CycleOutcome(cycle_ts=record.cycle_ts, completed_at=record.completed_at, mismatch=True)
    except EngineJournalError:
        return CycleOutcome(cycle_ts=record.cycle_ts, completed_at=record.completed_at, validation_failed=True)
    verdict = compare_targets(record.final_targets, replayed)
    return CycleOutcome(cycle_ts=record.cycle_ts, completed_at=record.completed_at, compare_passed=verdict.passed)


def _evaluate_journal(
    journal_root: Path, *, cache_path: Path | None = None, now: datetime
) -> tuple[list[CycleOutcome], JournalCounts, datetime | None, CacheStats]:
    """Replay every journaled cycle and classify every sidecar; absent boundaries are never fabricated (`evaluate_gate` scores them
    missing). `cache_path` (spec 00060) is opt-in: with None neither `replay_fingerprint` nor `evidence_fingerprint` runs, so no bug
    in either reaches a no-cache caller; a caught raise degrades that run or record to a plain replay, anything else propagates.
    `due_for_reverification` (spec 00062 D2-D4) re-replays the run's slice on a hit: only a replay re-hashes parquet bytes."""
    reader = _snapshot_reader(journal_root)

    cache_active = cache_path is not None
    cache = GateCache(replay_fp="", entries={})
    replay_fp = ""
    if cache_active:
        try:
            replay_fp = replay_fingerprint(path=_EVALUATE_JOURNAL_REPLAY_PATH)
        except OSError as exc:
            logger.warning(
                "gate-export cache: replay_fingerprint failed (%s); degrading this run to a full replay without a cache",
                exc,
            )
            cache_active = False
        else:
            cache = load_cache(cache_path, replay_fp)

    record_outcomes: list[CycleOutcome] = []
    updated_entries: dict[datetime, tuple[str, CycleOutcome, datetime]] = {}
    replayed_count = from_cache_count = 0
    for boundary, record_path in _journal_artifacts(journal_root, "*", "cycle-*.json"):
        try:
            record = from_json(record_path.read_text())
        except EngineJournalError:
            record_outcomes.append(CycleOutcome(cycle_ts=boundary, completed_at=boundary, validation_failed=True))
            continue

        fp = None
        if cache_active:
            try:
                fp = evidence_fingerprint(record)
            except (OSError, TypeError, AttributeError) as exc:
                logger.warning(
                    "gate-export cache: evidence_fingerprint failed for %s (%s); replaying this cycle uncached",
                    record.cycle_ts,
                    exc,
                )
        cached_entry = cache.entries.get(record.cycle_ts) if fp is not None else None
        reverify = due_for_reverification(record.cycle_ts, now)
        if cached_entry is not None and cached_entry[0] == fp and not reverify:
            outcome, verified_at = cached_entry[1], cached_entry[2]  # carry verified_at forward
            from_cache_count += 1
        else:
            outcome, verified_at = _replay_one(record, reader), now  # stamp on real verification
            replayed_count += 1
        if fp is not None:
            updated_entries[record.cycle_ts] = (fp, outcome, verified_at)
        record_outcomes.append(outcome)

    # Derived from the outcome, never from the branch that produced it: a cache hit must count as its replay would.
    replayed_ok = sum(1 for o in record_outcomes if not o.validation_failed and not o.mismatch and o.compare_passed)
    mismatches = sum(1 for o in record_outcomes if not o.validation_failed and (o.mismatch or not o.compare_passed))
    validation_failures = sum(1 for o in record_outcomes if o.validation_failed)

    entries = list(record_outcomes)
    sidecar_count = 0
    for boundary, sidecar_path in _journal_artifacts(journal_root, "*", "failed-cycle-*.json"):
        cycle_ts, completed_at, _ = _sidecar_fields(boundary, sidecar_path)
        entries.append(CycleOutcome(cycle_ts=cycle_ts, completed_at=completed_at, validation_failed=True))
        sidecar_count += 1

    newest_ts = max((entry.cycle_ts for entry in entries), default=None)
    oldest_age = None
    if cache_active:
        final_cache = GateCache(replay_fp=replay_fp, entries=updated_entries)
        save_cache(cache_path, final_cache)
        oldest_age = oldest_verification_age(final_cache, now)
    cache_stats = CacheStats(
        replayed=replayed_count, from_cache=from_cache_count, invalidated=cache.rejected, oldest_verification_age=oldest_age
    )
    return entries, JournalCounts(replayed_ok, mismatches, validation_failures, sidecar_count), newest_ts, cache_stats


def _gate_ping(url: str, success: bool) -> None:
    """The gate-export dead-man's-switch ping (spec 00042): GET `url` on a clean gate, GET
    `url + "/fail"` otherwise -- one attempt, any exception swallowed, because the ping can never be
    allowed to fail the export."""
    ping_url = url if success else url + "/fail"
    try:
        with _urlopen(ping_url, timeout=10):
            pass
    except Exception as exc:
        logger.warning("gate-export healthcheck ping failed url=%s error=%s", ping_url, exc)


def _write_prom_textfile(
    path: Path,
    *,
    status: GateStatus,
    lag_seconds: float | None,
    mismatch_total: int,
    cache_stats: CacheStats,
    now: datetime,
    duration_seconds: float,
) -> None:
    """Atomically write the gate-export Prometheus textfile metrics: a `.tmp` sibling then `os.replace`, so a scrape never observes
    a partial file. The cache metrics are always emitted -- hits 0 and invalidated 0 when `--cache` was omitted -- so a degrading
    cache is visible, except `_oldest_verification_age_seconds`, omitted like `_journal_pull_lag_seconds` when there is nothing to
    report; `_replayed`/`_hits` carry no `_total`: they are per-run gauges, and enabling the cache would read as a counter reset."""
    lines = [
        "# HELP zcrypto_gate_status 1 if the >=14-clean-day gate is MET else 0",
        f"zcrypto_gate_status {1 if status.gate_met else 0}",
        f"zcrypto_gate_streak_days {status.streak}",
    ]
    if lag_seconds is not None:
        lines.append(f"zcrypto_gate_journal_pull_lag_seconds {lag_seconds}")
    lines.append(
        "# HELP zcrypto_gate_mismatch_total journaled cycles that broke a clean day: "
        "replay mismatches + corrupt records + failed-cycle sidecars"
    )
    lines.append(f"zcrypto_gate_mismatch_total {mismatch_total}")
    lines.append(
        "# HELP zcrypto_gate_cache_replayed cycles actually replayed this run (cache miss, forced "
        "rotation re-verification, or no --cache)"
    )
    lines.append(f"zcrypto_gate_cache_replayed {cache_stats.replayed}")
    lines.append("# HELP zcrypto_gate_cache_hits cycles served from the incremental scoring cache this run")
    lines.append(f"zcrypto_gate_cache_hits {cache_stats.from_cache}")
    lines.append("# HELP zcrypto_gate_cache_invalidated 1 if the cache file was discarded wholesale this run, else 0")
    lines.append(f"zcrypto_gate_cache_invalidated {1 if cache_stats.invalidated else 0}")
    if cache_stats.oldest_verification_age is not None:
        lines.append(
            "# HELP zcrypto_gate_cache_oldest_verification_age_seconds seconds since the least-recently "
            "actually-replayed cached cycle was last verified"
        )
        lines.append(f"zcrypto_gate_cache_oldest_verification_age_seconds {cache_stats.oldest_verification_age}")
    lines.append(
        "# HELP zcrypto_gate_export_duration_seconds wall time to evaluate the journal "
        "(excludes writing this textfile and the healthcheck ping)"
    )
    lines.append(f"zcrypto_gate_export_duration_seconds {duration_seconds}")
    lines.append(f"zcrypto_gate_export_timestamp_seconds {now.timestamp()}")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n")
    os.replace(tmp_path, path)


@engine_app.command()
def seed() -> None:
    """Seed/refresh the live price store from the canonical dataset plus a Kraken REST gap-fill
    (idempotent; also the documented repair for a poisoned store tail)."""
    config = _load_engine_config()
    try:
        report = seed_store(config.store_dir, CANONICAL_DIR)
    except EngineError as exc:
        raise _abort(str(exc)) from exc
    typer.echo(f"seeded {config.store_dir} from {CANONICAL_DIR} + REST gap-fill; seam QA per pair x grid:")
    typer.echo(f"{'pair':<6} {'grid':>5} {'overlap_bars':>12} {'appended':>9} {'replaced':>9}")
    for entry in report.entries:
        typer.echo(
            f"{entry.pair:<6} {entry.interval:>5} {entry.overlap_bars:>12} {entry.appended:>9} {entry.replaced_tail_rows:>9}"
        )
    appended = sum(entry.appended for entry in report.entries)
    replaced = sum(entry.replaced_tail_rows for entry in report.entries)
    typer.echo(
        f"{len(report.entries)} series passed seam QA; appended {appended} bar(s), replaced {replaced} divergent tail row(s)"
    )


class _CycleGauges:
    """The engine's cumulative gauge/counter state (spec 00069 D5): `run()` builds one on the SAME
    registry the exporter serves, then installs `.update` as `cycle.py`'s metrics sink, called after
    every cycle whether it succeeded or failed. `cycle_success`, `cycle_duration` and `active_sleeves`
    are registered lazily -- an absent series is honest where a published 0 would be a claim."""

    def __init__(self, registry) -> None:
        self._registry = registry
        self.target_weight = Gauge(
            "zcrypto_engine_target_weight", "Latest per-asset target portfolio weight.", ["asset"], registry=registry
        )
        self._last_weight_assets: set[str] = set()  # last cycle's label set, so a dropped asset can be `.remove()`d
        self.orders_total = Counter(
            "zcrypto_engine_orders_total", "Intended orders emitted, across every cycle.", registry=registry
        )
        # Intent-prefixed on purpose (T0121): the §10 whole-book limits bind on the INTENT book, the
        # one this cycle just built, not on anything the executor did with it.
        self.limit_bound = Counter(
            "zcrypto_engine_limit_bound_total", "Cycles where a book-level limit changed the intended book.", registry=registry
        )
        # A Gauge, not a Counter: the pinned name (spec 00069 D5) carries no `_total` suffix and
        # `Counter` would silently add one, while `Gauge` exposes exactly the name given and `.inc()`
        # still makes it cumulative. It carries only counter SEMANTICS, though -- `rate()`/`increase()`
        # are undefined over it, and a restart drops it to 0 with no reset marker.
        self.order_notional_eur = Gauge(
            "zcrypto_engine_order_notional_eur", "Intended order notional (EUR), summed across every cycle.", registry=registry
        )
        self.cycle_success: Gauge | None = None  # lazy -- see seed_cycle_success (cold-review I4)
        self.cycle_completed_at = Gauge(
            "zcrypto_engine_cycle_completed_at_seconds", "Unix timestamp the most recent cycle completed at.", registry=registry
        )
        # Lazy, and deliberately not seeded from the journal either, unlike `cycle_completed_at`: the
        # artifact does carry the endpoints, but a previous process's duration is not this process's,
        # so `update()` is the only place it is honestly known.
        self.cycle_duration: Gauge | None = None
        self.sleeve_gross = Gauge(
            "zcrypto_engine_sleeve_gross",
            "Latest per-sleeve gross exposure (sum of absolute target weights).",
            ["sleeve"],
            registry=registry,
        )
        # Lazy, unlike the LABELLED `sleeve_gross` above, which publishes nothing until `.labels()`
        # is first called: this one is unlabelled, so registering it eagerly would publish 0.0 from
        # process start -- "no sleeve is carrying exposure" is a claim, and it would be the baseline
        # the composition-changed alert reads the first real cycle against.
        self.active_sleeves: Gauge | None = None

    def seed_cycle_success(self, success: bool) -> None:
        """Register (if not already) and set `zcrypto_engine_cycle_success` (spec 00069 D5) -- called
        at startup from the newest journal artifact's outcome, and from `update()` after every cycle.
        Left UNREGISTERED until a value is actually known: a fresh `Gauge` reads 0.0, which would
        claim "the last cycle failed" for the up-to-4h until the next one."""
        if self.cycle_success is None:
            self.cycle_success = Gauge(
                "zcrypto_engine_cycle_success", "1 if the most recent cycle succeeded, else 0.", registry=self._registry
            )
        self.cycle_success.set(1.0 if success else 0.0)

    def update(self, result: CycleResult, completed_at: datetime, duration_seconds: float) -> None:
        self.seed_cycle_success(result.status == "success")
        self.cycle_completed_at.set(completed_at.timestamp())
        if self.cycle_duration is None:
            self.cycle_duration = Gauge(
                "zcrypto_engine_cycle_duration_seconds",
                "Wall time the most recent cycle took, in seconds.",
                registry=self._registry,
            )
        self.cycle_duration.set(duration_seconds)
        if result.targets is not None:
            for asset, weight in result.targets.items():
                self.target_weight.labels(asset=asset).set(weight)
            # Retire assets that left the target set -- a label left behind publishes its last value for the life of the process.
            # `remove()`, not `set(0)`: a zero weight and a not-in-the-book asset are different states and the executor must tell
            # them apart.
            for asset in self._last_weight_assets - set(result.targets):
                self.target_weight.remove(asset)
            self._last_weight_assets = set(result.targets)
        if result.orders is not None:
            self.orders_total.inc(len(result.orders))
            self.order_notional_eur.inc(sum(order["notional_eur"] for order in result.orders))
        # Truthiness, so `None` -- a failed cycle, which ran no build and therefore has no answer --
        # counts as no bind rather than as one.
        if result.limit_bound:
            self.limit_bound.inc()
        if result.sleeve_gross is not None:  # None on a failed cycle: no build ran, so leave both as they were
            for sleeve, gross in result.sleeve_gross.items():
                self.sleeve_gross.labels(sleeve=sleeve).set(gross)
            if self.active_sleeves is None:
                self.active_sleeves = Gauge(
                    "zcrypto_engine_active_sleeves",
                    "Number of sleeves with non-zero gross in the most recent cycle.",
                    registry=self._registry,
                )
            self.active_sleeves.set(sum(1 for gross in result.sleeve_gross.values() if gross > 0.0))


class _ExecGauges:
    """The execution envelope's published state, updated from the gate's verdict every cycle. `gate_level` and the presence gauges
    are eager and seeded at 0 -- "nothing may be submitted" is true before anything is evaluated -- and `run()` evaluates once at
    startup so none sits at that default: a `kill_tripped` reading 0 beside an existing kill file is a false statement.
    `last_evaluation` is lazy: the staleness alert reads it, and a seeded 0 would claim the epoch and page every fresh process."""

    def __init__(self, registry) -> None:
        self._registry = registry
        self.gate_level = Gauge(
            "zcrypto_exec_gate_level",
            "What the engine may submit right now: 0 = nothing, 1 = reducing orders only, 2 = anything.",
            registry=registry,
        )
        self.armed = Gauge(
            "zcrypto_exec_armed",
            "Whether both arming keys are present (the config flag and the arm file on the host).",
            registry=registry,
        )
        self.kill_tripped = Gauge("zcrypto_exec_kill_tripped", "Whether the kill switch file is present.", registry=registry)
        self.restart_hold = Gauge(
            "zcrypto_exec_restart_hold",
            "Whether this process is still held at reducing-only after a restart.",
            registry=registry,
        )
        self.venue_ok = Gauge(
            "zcrypto_exec_venue_ok", "Whether the last venue reading said the exchange is online.", registry=registry
        )
        # The envelope's heartbeat, and the ONLY series that can answer "is the gate still being evaluated at all". An age gauge was
        # rejected: evaluations are hours apart and the snapshot bound is 30 s, so every one re-reads and the age would publish ~0
        # forever -- a constant in measurement's clothes.
        self.last_evaluation: Gauge | None = None

    def update(self, verdict: GateVerdict, *, evaluated_at: datetime) -> None:
        i = verdict.inputs
        self.gate_level.set(LEVEL_CODE[verdict.level])
        self.armed.set(1 if (i["armed_in_config"] and i["arm_file"]) else 0)
        self.kill_tripped.set(1 if i["kill_file"] else 0)
        self.restart_hold.set(1 if i["restart_hold"] else 0)
        self.venue_ok.set(1 if i["venue_status"] == "online" else 0)
        if self.last_evaluation is None:
            self.last_evaluation = Gauge(
                "zcrypto_exec_last_evaluation_timestamp_seconds",
                "Unix timestamp the execution gate was last evaluated.",
                registry=self._registry,
            )
        self.last_evaluation.set(evaluated_at.timestamp())


# Every outcome `cli/engine/executor.py`'s `_inc_order` can emit, pinned against that module's own
# call sites by tests/test_engine_metrics.py. `ambiguous` must never be folded into `refused`:
# "refused" asserts that no order exists, and after a submission whose venue outcome was never
# established that claim is unavailable.
_EXEC_ORDER_OUTCOMES = ("submitted", "accepted", "rejected", "venue_canceled", "canceled", "filled", "refused", "ambiguous")
# Every name the venue's own `LiquiditySide` can produce, lower-cased -- pinned against the real enum
# by tests/test_engine_metrics.py rather than derived here, since importing nautilus-trader at module
# level would put ~1 s on `zcrypto --help`. `no_liquidity_side` is deliberate and pre-registered: a
# fill the venue did not attribute is still a fill, and counting it as taker would fake the split.
_EXEC_LIQUIDITY_SIDES = ("maker", "taker", "no_liquidity_side")
# Every disposition `cli/engine/executor.py`'s `_inc_external` can emit, pinned against that module's
# own call sites by tests/test_engine_metrics.py. `unmatched` is the load-bearing one: an order event
# belonging to no order this engine's ledger vouches for is counted and ignored, and this counter is
# the only trace it leaves.
_EXEC_EXTERNAL_DISPOSITIONS = ("matched", "unmatched")


class _ExecutionMetrics:
    """What the executor did, not `_ExecGauges`' what it was ALLOWED to do; on telemetry hooks that cannot alter or stop a
    submission. Counter label children are eager: a Counter's zero is a MEASURED fact where a Gauge's would be an unmeasured claim,
    and a series born at the first rejection gives `rate()` no baseline. `realized_pnl` is a Gauge because realized PnL falls, eager
    at 0, never seeded from disk: a restart mid-probe reads 0 until the next fill, accepted because probe windows are attended."""

    def __init__(self, registry) -> None:
        self._registry = registry
        self.orders = Counter("zcrypto_exec_orders_total", "Executor orders by outcome.", ["outcome"], registry=registry)
        self.fills = Counter("zcrypto_exec_fills_total", "Order fills by liquidity side.", ["liquidity"], registry=registry)
        self.fees = Counter("zcrypto_exec_fees_eur_total", "Trading fees paid, in EUR.", registry=registry)
        self.position = Gauge(
            "zcrypto_exec_position", "Net position quantity by symbol, in base units.", ["symbol"], registry=registry
        )
        self.resting_order_age = Gauge(
            "zcrypto_exec_resting_order_age_seconds",
            "How long the engine's current resting order has been at the venue, in seconds, by plan "
            "mode; zero when none rests. This is the engine's own belief, not a venue read: if a "
            "cancel could not reach the venue the engine gives up on the order and this reads zero "
            "while it may still rest at Kraken. Nothing is published while the engine is down.",
            ["mode"],
            registry=registry,
        )
        self.realized_pnl = Gauge("zcrypto_exec_realized_pnl_eur", "Realized profit and loss, in EUR.", registry=registry)
        self.external_events = Counter(
            "zcrypto_exec_external_events_total",
            "Order events arriving on the external strategy topic, by disposition: matched means the "
            "event belonged to a restart-adopted order this engine's ledger vouches for; unmatched "
            "means it belonged to no such order and was acted on nowhere -- the account owner's own "
            "hand settle, activity nobody sanctioned, or a fill on an order the startup pass could "
            "not see.",
            ["disposition"],
            registry=registry,
        )
        # Registered on first use: every value this gauge can take means something, so a series that
        # existed before the first boundary was scored could only publish 0 -- a code outside that
        # alphabet, read as a legitimate verdict rather than as "nothing has been scored yet".
        self.tracking_state: Gauge | None = None
        for outcome in _EXEC_ORDER_OUTCOMES:
            self.orders.labels(outcome=outcome)
        for liquidity in _EXEC_LIQUIDITY_SIDES:
            self.fills.labels(liquidity=liquidity)
        for disposition in _EXEC_EXTERNAL_DISPOSITIONS:
            self.external_events.labels(disposition=disposition)

    def inc_order(self, outcome: str) -> None:
        self.orders.labels(outcome=outcome).inc()

    def set_resting_age(self, mode: str, seconds: float) -> None:
        self.resting_order_age.labels(mode=mode).set(seconds)

    def inc_external(self, disposition: str) -> None:
        self.external_events.labels(disposition=disposition).inc()

    def inc_fill(self, liquidity: str, fee_eur: float | None) -> None:
        """`fee_eur is None` means the caller could not denominate the commission in EUR. The fill
        still counts -- it happened -- and the fee does not: this total is EUR by name, and adding a
        differently-denominated commission to it would produce a number with no unit."""
        self.fills.labels(liquidity=liquidity).inc()
        if fee_eur is not None:
            self.fees.inc(fee_eur)

    def set_position(self, symbol: str, qty: float) -> None:
        self.position.labels(symbol=symbol).set(qty)

    def set_realized(self, value: float) -> None:
        self.realized_pnl.set(value)

    def set_tracking_state(self, state: int) -> None:
        """What the last 4-hourly boundary decided about the most recently closed week. The help text
        carries the whole alphabet because this gauge is read on a board, where a bare number means nothing."""
        if self.tracking_state is None:
            self.tracking_state = Gauge(
                "zcrypto_exec_tracking_state",
                "The most recently closed week's tracking-error verdict: 1 = no band is configured, "
                "so nothing is measured against one; 2 = the week could not be scored; 3 = the week's "
                "mean drift is inside the band; 4 = it is outside the band and the kill switch latched.",
                registry=self._registry,
            )
        self.tracking_state.set(state)


class _VenueGauges:
    """The venue-truth family (spec 00089 D6), updated when `CycleResult.venue` is present, seeded at startup by
    `_seed_venue_state`: unseeded, a restart strands every gauge at its eager default until the NEXT boundary cycle, false-paging
    `zcrypto-venue-snapshot-stale`. The snapshot gauge is a TIMESTAMP: an age would freeze healthy-looking when its writer dies,
    while 0.0 reads as ancient, never a false "just now". `instruments_expected` derives from `INSTRUMENT_IDS`, never a literal."""

    def __init__(self, registry) -> None:
        self.snapshot_timestamp = Gauge(
            "zcrypto_venue_snapshot_timestamp_seconds",
            "Unix timestamp of the last successful venue-truth snapshot.",
            registry=registry,
        )
        self.instruments_loaded = Gauge(
            "zcrypto_venue_instruments_loaded",
            "Ratified instruments successfully loaded from the venue in the last snapshot.",
            registry=registry,
        )
        self.instruments_expected = Gauge(
            "zcrypto_venue_instruments_expected",
            "Ratified instruments the venue is expected to carry.",
            registry=registry,
        )
        self.instruments_expected.set(len(INSTRUMENT_IDS))
        self.concordance_failures = Gauge(
            "zcrypto_venue_concordance_failures",
            "Ratified instruments that failed runtime concordance in the last snapshot.",
            registry=registry,
        )

    def update(self, venue: dict | None) -> None:
        # None (00089 D7): no snapshot this cycle -- move NOTHING, not even the timestamp, so a dead
        # writer's last real reading keeps aging honestly instead of being masked by a fresh update.
        if venue is None:
            return
        self.snapshot_timestamp.set(datetime.fromisoformat(venue["snapshot_at"]).timestamp())
        self.instruments_loaded.set(venue["loaded"])
        self.instruments_expected.set(venue["expected"])
        self.concordance_failures.set(venue["failures"])


def _seed_cycle_state(journal_dir: Path) -> tuple[datetime, bool | None]:
    """The startup seed for `zcrypto_engine_cycle_completed_at_seconds` and `zcrypto_engine_cycle_success` (spec 00069 D5):
    the newest journal artifact's own `completed_at` and outcome, a failed-cycle sidecar scoring False, so a routine restart
    leaves neither series false-firing. Falls back to process start on a journal holding nothing yet, where the success half
    has no honest answer at all and comes back None -- the caller must then leave that gauge UNREGISTERED."""
    newest: tuple[datetime, bool] | None = None
    for _, path in _journal_artifacts(journal_dir, "*", "cycle-*.json"):
        try:
            record = from_json(path.read_text())
        except EngineJournalError:
            continue
        if newest is None or record.completed_at > newest[0]:
            newest = (record.completed_at, True)
    for boundary, path in _journal_artifacts(journal_dir, "*", "failed-cycle-*.json"):
        _, completed_at, _ = _sidecar_fields(boundary, path)
        if newest is None or completed_at > newest[0]:
            newest = (completed_at, False)
    return newest if newest is not None else (_utc_now(), None)


def _seed_completed_at(journal_dir: Path) -> datetime:
    """`_seed_cycle_state`'s completed_at half alone."""
    return _seed_cycle_state(journal_dir)[0]


def _seed_venue_state(journal_dir: Path) -> dict | None:
    """The startup seed for `_VenueGauges` (spec 00089 D6): the newest `venue-<HH>.json` whose `status` is `"ok"`, in the shape
    `CycleResult.venue` carries, or None when the journal holds no readable `ok` record yet; an `"error"` record is skipped, never
    treated as newer, so the last REAL snapshot keeps aging honestly. No try/except of its own, and `validate_venue_record` runs
    BEFORE `status` is read (T0140 D9): a record that fails it propagates to the caller's guard, which owns telemetry isolation."""
    from cli.engine.venueledger import read_venue_record, validate_venue_record

    newest: tuple[datetime, dict] | None = None
    for _, path in _journal_artifacts(journal_dir, "*", "venue-*.json"):
        doc = read_venue_record(path)
        validate_venue_record(doc)
        if doc.get("status") != "ok":
            continue
        cycle_ts = datetime.fromisoformat(doc["cycle_ts"])
        if newest is None or cycle_ts > newest[0]:
            newest = (cycle_ts, doc)
    if newest is None:
        return None
    doc = newest[1]
    return {
        "loaded": len(doc["state"]["instruments"]),
        "expected": len(INSTRUMENT_IDS),
        "failures": len(doc["concordance"]["failures"]),
        "snapshot_at": doc["state"]["snapshot_at"],
    }


def _seed_exec_positions(journal_dir: Path) -> dict[str, float] | None:
    """The startup seed for the symbol-labelled positions gauge: the newest `venue-<HH>.json` that is
    both `"ok"` and `schema_version == 2`. A base-keyed v1 record is skipped even when `"ok"`, never
    coerced, because it cannot honestly produce a symbol label. Same no-try/except and
    validate-before-`status` contract as `_seed_venue_state`."""
    from cli.engine.venueledger import read_venue_record, validate_venue_record

    newest: tuple[datetime, dict] | None = None
    for _, path in _journal_artifacts(journal_dir, "*", "venue-*.json"):
        doc = read_venue_record(path)
        validate_venue_record(doc)
        if doc.get("status") != "ok" or doc.get("schema_version") != 2:
            continue
        cycle_ts = datetime.fromisoformat(doc["cycle_ts"])
        if newest is None or cycle_ts > newest[0]:
            newest = (cycle_ts, doc)
    if newest is None:
        return None
    return dict(newest[1]["state"]["positions"])


def _make_exec_sink(gate, journal_dir: Path, cycle_gauges, exec_gauges, venue_gauges):
    """`run()`'s per-cycle metrics sink, at module level rather than inline so a test can reach the closure and prove the ORDER
    inside it: a failing ledger write starves the heartbeat rather than being masked by a gauge that keeps ticking."""

    def _sink(result, completed_at, duration_seconds):
        # The ledger is a forensic artifact, not a metric: compute the verdict and write it before
        # either gauge group is touched, so a raising gauge update can never cost this cycle's record.
        verdict = gate.evaluate(completed_at)
        write_exec_record(journal_dir, result.cycle_ts, verdict, evaluated_at=completed_at)
        if cycle_gauges is not None:
            cycle_gauges.update(result, completed_at, duration_seconds)
        if exec_gauges is not None:
            exec_gauges.update(verdict, evaluated_at=completed_at)
        if venue_gauges is not None:
            venue_gauges.update(result.venue)

    return _sink


@engine_app.command()
def run() -> None:
    """Run the shadow node in the foreground (the soak's systemd user service runs this).
    Fails fast on a missing zcrypto.toml (when ZCRYPTO_REQUIRE_CONFIG is set) or a missing/empty
    store -- a node without them is always misconfigured, never a healthy default."""
    if os.environ.get("ZCRYPTO_REQUIRE_CONFIG") and not Path("zcrypto.toml").exists():
        raise _abort(
            "ZCRYPTO_REQUIRE_CONFIG is set but no zcrypto.toml exists in the working directory -- a default-config "
            "node (exec off, journal under the CWD) would run indistinguishably from a healthy one; fix the bind-mount"
        )
    config = _load_engine_config()
    # Every start latches reduce-only. Deliberately unconditional: an engine that has just come
    # up must not be able to widen its own permission.
    write_restart_hold(config.journal_dir.parent, _utc_now())
    # Membership, not a glob: `refresh_store` reads every BASKET leg on both grids at each boundary,
    # so a glob over one quote directory passes on a store missing exactly the legs a widening added.
    missing = [
        f"{symbol}@{interval}"
        for symbol in BASKET
        for interval in GRID_INTERVALS
        if not _store_path(config.store_dir, symbol, interval).exists()
    ]
    if missing:
        raise _abort(
            f"store_dir {config.store_dir} is missing {len(missing)} of the {len(BASKET) * len(GRID_INTERVALS)} "
            f"basket series a cycle reads: {', '.join(missing)} -- a node without a complete store is always "
            "misconfigured; fix the bind-mount or run `zcrypto engine seed`"
        )
    logger.info(
        "engine run: exec_enabled=%s, store_dir=%s, journal_dir=%s", config.exec_enabled, config.store_dir, config.journal_dir
    )

    # Opt-in exporter (spec 00069 D5): unset ZCRYPTO_METRICS_PORT means no server, no gauges --
    # but the sink and the execution ledger are installed regardless (see below).
    port = metrics_port_from_env()
    registry = None
    cycle_gauges = None
    venue_gauges = None
    if port is not None:
        registry = build_registry()
        # Startup seeding reads arbitrary on-disk journal artifacts and can raise OUTSIDE
        # EngineJournalError (a PermissionError, a naive/aware comparison): telemetry may never kill
        # the engine daemon (spec 00069 D5), so serve process metrics regardless.
        try:
            cycle_gauges = _CycleGauges(registry)
            completed_at, success = _seed_cycle_state(config.journal_dir)
            cycle_gauges.cycle_completed_at.set(completed_at.timestamp())
            if success is not None:  # None => empty/unreadable journal -- leave cycle_success absent
                cycle_gauges.seed_cycle_success(success)
        except Exception:
            logger.exception("engine metrics setup failed -- continuing with process metrics only")
        # Its own guard, isolated from the cycle seed above (spec 00089 D6): an unreadable or absent
        # venue-<HH>.json must never prevent the engine from starting.
        try:
            venue_gauges = _VenueGauges(registry)
            seed = _seed_venue_state(config.journal_dir)
            if seed is not None:  # None => no readable "ok" record yet -- leave every gauge eager
                venue_gauges.update(seed)
        except Exception:
            logger.exception("venue metrics setup failed -- continuing with process metrics only")
        start_metrics_server(port, registry)

    # Built regardless of telemetry: the ledger is a forensic artifact, not a metric. `venue_reader`
    # is passed explicitly so a test can substitute this module's `read_system_status`.
    gate = ExecutionGate(armed_in_config=config.exec_armed, state_dir=config.journal_dir.parent, venue_reader=read_system_status)
    exec_gauges = _ExecGauges(registry) if registry is not None else None

    exec_metrics = None
    if registry is not None:
        # Its own isolation guard, the `_VenueGauges` pattern. The families are registered BEFORE the
        # seed, so a failed seed costs the starting values, never the series.
        try:
            exec_metrics = _ExecutionMetrics(registry)
            positions = _seed_exec_positions(config.journal_dir)
            if positions is not None:  # None => no readable v2 "ok" record yet -- publish no symbol
                for symbol, qty in positions.items():
                    exec_metrics.position.labels(symbol=symbol).set(qty)
        except Exception:
            logger.exception("execution metrics setup failed -- continuing without them")

    set_metrics_sink(_make_exec_sink(gate, config.journal_dir, cycle_gauges, exec_gauges, venue_gauges))

    # Lazy: cli.engine.executor imports nautilus-trader (~1 s); `zcrypto --help` must never pay it.
    from cli.engine import executor

    # Installed whether or not the exporter is on -- with both hooks None when it is off, which is
    # exactly what the executor's own None-safe wrappers expect.
    executor.set_executor_hooks(
        publish_verdict=(exec_gauges.update if exec_gauges is not None else None),
        metrics=exec_metrics,
    )

    # One evaluation at startup so no latch gauge sits at its seeded default, inside the sink's isolation.
    if exec_gauges is not None:
        try:
            now = _utc_now()
            exec_gauges.update(gate.evaluate(now), evaluated_at=now)
        except Exception:  # noqa: BLE001 -- telemetry must never prevent the engine from starting
            logger.exception("startup execution-gate evaluation failed")

    # Lazy: cli.engine.node imports nautilus-trader (~1 s); `zcrypto --help` must never pay it.
    from cli.engine.node import build_shadow_node

    node = build_shadow_node(config)
    # The only thing arming faulthandler (nothing else sets PYTHONFAULTHANDLER): without it a native abort (a Rust panic, the pyo3
    # unsendable assertion) kills the engine with exit 134 and NOTHING on stderr. `disable()` first: `enable()` installs the
    # fatal-signal handlers only while faulthandler considers itself disabled. `file=2` so the dump reaches fd 2; the default
    # `sys.stderr` form raises with no `fileno()`, which after `disable()` leaves the engine unarmed; an fd cannot fail that way.
    faulthandler.disable()
    faulthandler.enable(file=2)
    logger.info("shadow node starting (exec_enabled=%s, journal_dir=%s)", config.exec_enabled, config.journal_dir)
    # `node.run()` returns on a clean shutdown and RAISES on a start it cannot complete -- a client that never connects, a
    # startup reconciliation that never finishes. Nothing here may catch that raise: the node has already stopped by the
    # time it escapes, `cli/__main__.py` logs it at ERROR and compose's restart policy is the recovery, and a swallowed
    # start failure is a live-looking node that will never trade.
    try:
        node.run()
    finally:
        node.dispose()


def _echo_cycle_result(result: CycleResult) -> None:
    typer.echo(f"cycle {result.cycle_ts.isoformat()}: {result.status}")
    if result.status == "success":
        typer.echo(f"  record: {result.record_path}")
        for asset in sorted(result.targets):
            typer.echo(f"  target {asset}: {result.targets[asset]:+.6f}")
        if result.orders:
            for order in result.orders:
                typer.echo(
                    f"  order: {order['side']} {order['quantity']:.8f} {order['asset']} "
                    f"(~{order['notional_eur']:.2f} EUR @ {order['price']})"
                )
        else:
            typer.echo("  orders: none (targets unchanged vs the previous journaled cycle)")
    else:
        typer.echo(f"  sidecar: {result.sidecar_path}")
        typer.echo(f"  reason: {result.reason} ({', '.join(result.offending_pairs)})")


@engine_app.command()
def cycle(
    at: Optional[str] = typer.Option(
        None,
        "--at",
        help="Run the cycle at this aware ISO-8601 timestamp, exactly on the 4h grid (00/04/08/12/16/20 UTC). "
        "Defaults to the most recent elapsed boundary.",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Delete the boundary's existing record/sidecar and snapshots, then re-run it. Without this flag an "
        "already-journaled boundary is refused.",
    ),
) -> None:
    """Run one shadow cycle manually; exits non-zero when the cycle fails (sidecar written)."""
    config = _load_engine_config()
    if at is None:
        # Lazy: cli.engine.node imports nautilus-trader (~1 s); `zcrypto --help` must never pay it.
        from cli.engine.node import most_recent_boundary

        boundary = most_recent_boundary(_utc_now())
    else:
        boundary = _parse_at(at)

    day_dir = config.journal_dir / f"{boundary:%Y-%m-%d}"
    existing = [
        path for path in (day_dir / f"cycle-{boundary:%H}.json", day_dir / f"failed-cycle-{boundary:%H}.json") if path.exists()
    ]
    if existing and not replace:
        raise _abort(
            f"{boundary.isoformat()} is already journaled ({', '.join(str(p) for p in existing)}) -- "
            "pass --replace to overwrite; journaled soak evidence is never silently clobbered"
        )
    if replace:
        for path in existing:
            path.unlink()
        snapshots_dir = day_dir / "snapshots" / f"cycle-{boundary:%H}"
        if snapshots_dir.exists():
            shutil.rmtree(snapshots_dir)
        if existing:
            logger.warning("cycle --replace: deleted %s's journaled artifact(s) before re-running", boundary.isoformat())

    try:
        result = run_cycle(boundary, config=config)
    except EngineError as exc:
        raise _abort(str(exc)) from exc
    _echo_cycle_result(result)
    if result.status != "success":
        raise typer.Exit(code=1)


@engine_app.command()
def replay(
    date: Optional[str] = typer.Option(
        None, "--date", help="Replay only this UTC day's journaled cycles (YYYY-MM-DD). Defaults to every journaled day."
    ),
    path: str = typer.Option("fast", "--path", help="Builder path: 'fast' (default) or 'verified' (the daily oracle spot replay)."),
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
) -> None:
    """Replay journaled success cycles through the builder and compare targets against the record;
    mismatches and validation failures are classified (never crash the sweep) and exit non-zero."""
    if path not in ("fast", "verified"):
        raise _abort(f"--path must be 'fast' or 'verified', got {path!r}")
    if date is not None:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise _abort(f"--date {date!r} is not a YYYY-MM-DD date") from exc
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    pattern = date if date is not None else "*"
    reader = _snapshot_reader(journal_root)

    records = _journal_artifacts(journal_root, pattern, "cycle-*.json")
    sidecars = _journal_artifacts(journal_root, pattern, "failed-cycle-*.json")
    if not records and not sidecars:
        typer.echo("no journaled cycles found")
        return

    ok = mismatches = validation_failures = 0
    for boundary, record_path in records:
        try:
            record = from_json(record_path.read_text())
            replayed = replay_cycle(record, reader, path=path)
        except HashMismatchError as exc:
            mismatches += 1
            typer.echo(f"{boundary.isoformat()}  MISMATCH (corrupt evidence): {exc}")
            continue
        except EngineJournalError as exc:
            validation_failures += 1
            typer.echo(f"{boundary.isoformat()}  VALIDATION-FAILED: {exc}")
            continue
        verdict = compare_targets(record.final_targets, replayed)
        if verdict.passed:
            ok += 1
            typer.echo(f"{boundary.isoformat()}  ok (worst |diff| {verdict.worst_abs_diff:.2e})")
        else:
            mismatches += 1
            detail = (
                "structural (asset sets differ)"
                if verdict.structural_mismatch
                else f"worst {verdict.worst_asset} |diff| {verdict.worst_abs_diff:.2e}"
            )
            typer.echo(f"{boundary.isoformat()}  MISMATCH: {detail}")
    for boundary, sidecar_path in sidecars:
        _, _, reason = _sidecar_fields(boundary, sidecar_path)
        typer.echo(f"{boundary.isoformat()}  failed cycle ({reason})")

    typer.echo(
        f"replayed {len(records)} success record(s) via the {path} path: {ok} ok, {mismatches} mismatch(es), "
        f"{validation_failures} validation failure(s); {len(sidecars)} failed cycle(s) (sidecars)"
    )
    if mismatches or validation_failures:
        raise typer.Exit(code=1)


@engine_app.command()
def report(
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
) -> None:
    """Evaluate the ratified >= 14-clean-day gate over the whole journal (replay-on-demand, fast
    path): streak length, gate status, and the most recent failure."""
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    now = _utc_now()
    entries, counts, _, _ = _evaluate_journal(journal_root, cache_path=None, now=now)

    try:
        status = evaluate_gate(entries, now=now)
    except EngineError as exc:
        raise _abort(str(exc)) from exc

    typer.echo(
        f"{len(entries)} journaled outcome(s): {counts.replayed_ok} replayed ok, {counts.mismatches} mismatch(es), "
        f"{counts.validation_failures} validation failure(s), {counts.sidecar_count} failed cycle(s) (sidecars)"
    )
    typer.echo(f"streak: {status.streak} consecutive clean day(s)")
    typer.echo(f"gate (>= 14 clean days): {'MET' if status.gate_met else 'not met'}")
    if status.last_failure is None:
        typer.echo("last failure: none")
    else:
        typer.echo(f"last failure: {status.last_failure.cycle_ts.isoformat()} -- {status.last_failure.reason}")


@engine_app.command(name="soak-check")
def soak_check(
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
    store_dir: Optional[Path] = typer.Option(
        None, "--store-dir", help="Live price store to read instead of the configured store_dir."
    ),
    canonical_dir: Path = typer.Option(
        CANONICAL_DIR,
        "--canonical-dir",
        help="Frozen canonical dataset root used to rebuild the backtest null; absent skips the null and any verdict.",
    ),
    registry: Path = typer.Option(
        Path("docs/reference/trial-registry.jsonl"),
        "--registry",
        help="Trial-registry JSON-lines file the instrument self-test reproduces the ratified record against.",
    ),
    fee_per_side: float = typer.Option(
        0.006, "--fee-per-side", help="Per-side cost rate applied to both the realized series and the backtest null."
    ),
    band: float = typer.Option(
        0.90, "--band", help="Two-sided outer band width used to judge each structural metric against its null distribution."
    ),
    floor: int = typer.Option(30, "--floor", help="Minimum scored realized bars required before any metric verdict is attempted."),
    null_mode: str = typer.Option(
        "both",
        "--null",
        help="Backtest null construction(s) to judge each metric against: 'windows' (overlapping-window "
        "reference), 'block-bootstrap' (an independently resampled reference), or 'both' (judge under each "
        "and reconcile the two verdicts, surfacing any disagreement between them).",
    ),
    path: str = typer.Option(
        "fast",
        "--path",
        help="Builder path used to rebuild the backtest null and its identity self-check: 'fast' (default) or "
        "'verified' (the much slower daily oracle spot replay, for re-reading a suspicious result without editing code).",
    ),
    json_out: Optional[Path] = typer.Option(
        None, "--json", help="Write the full report payload as JSON to this path (atomic write)."
    ),
) -> None:
    """Compare the realized shadow-engine journal against its backtest null and render a soak-check
    report -- read-only decision-support, never the concordance gate or a stand-alone validation
    exercise, and it consumes no holdout budget."""
    if null_mode not in ("windows", "block-bootstrap", "both"):
        raise _abort(f"--null must be 'windows', 'block-bootstrap', or 'both', got {null_mode!r}")
    if path not in ("fast", "verified"):
        raise _abort(f"--path must be 'fast' or 'verified', got {path!r}")

    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    store_root = store_dir if store_dir is not None else config.store_dir

    try:
        text, payload = soak_report(
            journal_dir=journal_root,
            store_dir=store_root,
            canonical_dir=canonical_dir,
            registry_path=registry,
            fee=fee_per_side,
            band=band,
            floor=floor,
            null_mode=null_mode,
            path=path,
        )
    except EngineError as exc:
        raise _abort(str(exc)) from exc

    typer.echo(text)

    if json_out is not None:
        tmp_path = json_out.with_suffix(json_out.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp_path, json_out)

    self_test = payload.get("self_test")
    if self_test is not None and self_test.get("void"):
        # A ran-and-failed instrument/identity/reconcile check means the tool itself cannot be
        # trusted -- distinct from a "no verdict" refusal, which exits 0 like any successful emit.
        raise typer.Exit(code=1)


@engine_app.command(name="gate-export")
def gate_export(
    textfile: Path = typer.Option(
        ..., "--textfile", help="Prometheus node-exporter textfile-collector path to atomically write the gate metrics to."
    ),
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
    healthcheck_url: Optional[str] = typer.Option(
        None,
        "--healthcheck-url",
        help="Dead-man's-switch base URL: GET on a clean gate, GET <url>/fail otherwise. Omit to skip the ping.",
    ),
    lag_fail_seconds: float = typer.Option(
        21600.0,
        "--lag-fail-seconds",
        help="Journal-pull staleness threshold in seconds beyond which the ping counts as unclean (default 21600, 6h).",
    ),
    cache: Optional[Path] = typer.Option(
        None,
        "--cache",
        help="Incremental scoring cache path: reuse prior replay outcomes for unchanged cycles instead of "
        "re-replaying the whole journal every run. Omit for today's full replay, unchanged.",
    ),
) -> None:
    """Emit the >= 14-clean-day gate as machine-readable Prometheus metrics (atomic textfile write)
    and ping an independent dead-man's-switch healthcheck. Exits 0 on a successful emit even when the
    gate has a mismatch or the journal is stale -- those are findings, reported through the metrics
    and a /fail ping -- and non-zero only on an operational failure."""
    export_started = time.monotonic()
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    now = _utc_now()
    entries, counts, newest_ts, cache_stats = _evaluate_journal(journal_root, cache_path=cache, now=now)

    try:
        status = evaluate_gate(entries, now=now)
    except EngineError as exc:
        raise _abort(str(exc)) from exc

    lag = (now - newest_ts).total_seconds() if newest_ts is not None else None
    # Every not-clean outcome that breaks a gate day, failed-cycle sidecars included: they break the
    # streak but are tallied separately, so omitting them would let this metric read 0 and the
    # dead-man ping "clean" through a real gate failure.
    mismatch_total = counts.mismatches + counts.validation_failures + counts.sidecar_count

    duration_seconds = time.monotonic() - export_started
    try:
        _write_prom_textfile(
            textfile,
            status=status,
            lag_seconds=lag,
            mismatch_total=mismatch_total,
            cache_stats=cache_stats,
            now=now,
            duration_seconds=duration_seconds,
        )
    except OSError as exc:
        raise _abort(f"could not write gate textfile {textfile}: {exc}") from exc

    if healthcheck_url:
        # The dead-man reflects the gate's CURRENT health across every break reason, not just the counted mismatch_total:
        # streak>0 means the last complete day is clean, streak==0 with no last_failure means no complete day is evaluable
        # yet (liveness only, not a break), and streak==0 WITH one means the most recent complete day broke. A recovered
        # gate reads clean, matching Grafana's windowed increase().
        gate_healthy = status.streak > 0 or status.last_failure is None
        clean = gate_healthy and lag is not None and lag <= lag_fail_seconds
        _gate_ping(healthcheck_url, clean)


# --- the two sizing measurements (spec 00081): gross attribution + the venue-minimum drift floor --


def _parse_day(raw: str | None, flag: str) -> date | None:
    if raw is None:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise _abort(f"{flag} {raw!r} is not a YYYY-MM-DD date") from exc


def _window_records(journal_root: Path, since: str | None, until: str | None) -> list[CycleRecord]:
    """Every journaled success record whose boundary falls in the inclusive [--since, --until] UTC day
    window. An unreadable record ABORTS rather than being skipped: both measurements aggregate across
    the whole window, so a quietly dropped cycle biases every number below it with nothing on the page
    to say so, and --since/--until are the escape hatch for a journal carrying a known-bad day."""
    since_day = _parse_day(since, "--since")
    until_day = _parse_day(until, "--until")
    records: list[CycleRecord] = []
    for boundary, path in _journal_artifacts(journal_root, "*", "cycle-*.json"):
        if (since_day is not None and boundary.date() < since_day) or (until_day is not None and boundary.date() > until_day):
            continue
        try:
            records.append(from_json(path.read_text()))
        except EngineJournalError as exc:
            raise _abort(
                f"unreadable cycle record {path}: {exc} -- every number here aggregates the whole window, so "
                "skipping it would silently bias the result; repair the record or exclude its day with --since/--until"
            ) from exc
    if not records:
        raise _abort(f"no cycle records found under {journal_root} in the requested window")
    return records


def _resolve_minimums(flag_value: Path | None) -> Path:
    """`--minimums`, else the newest venue reference-data snapshot under the configured data dir --
    newest BY FILENAME, whose fixed-width UTC stamp orders lexicographically as it orders in time."""
    if flag_value is not None:
        return flag_value
    snapshots_dir = (_load_app_config().data_dir or Path("data")) / "snapshots"
    candidates = sorted(snapshots_dir.glob(_REFDATA_GLOB))
    if not candidates:
        raise _abort(
            f"no {_REFDATA_GLOB} found under {snapshots_dir} -- pass --minimums <path> to name the venue "
            "snapshot the order minimums are read from"
        )
    return candidates[-1]


def _payload_json(payload: dict) -> str:
    """The report payload as STRICTLY valid JSON: every non-finite float becomes `null`, every mapping key a string. `json.dumps`
    writes a NaN as the bare token `NaN`, which the JSON grammar has no room for, and emitting invalid JSON from a `--json` flag is
    worse than losing the NaN/None distinction, which only the rendered text keeps (`no data` vs `n/a`). The drift payload's float
    NAV keys are spelled here, not left to `json.dumps`' coercion; the numeric NAVs stay in `navs` and each row's `nav`."""

    def convert(value):
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    # allow_nan=False makes the conversion self-checking: a non-finite that escaped it raises here
    # rather than being emitted as an invalid token.
    return json.dumps(convert(payload), indent=2, sort_keys=True, allow_nan=False)


def _emit_report(text: str, payload: dict, *, as_json: bool) -> None:
    """Print the report, then exit non-zero if anything in it failed -- `n_failed` is the count. A
    failed replay means an identity guard fired, so the aggregates above it describe a smaller window
    than was asked for; a caller may count other failures of the same weight. Every one is named in
    the rendered text and in the payload, and the exit code is what a script notices."""
    typer.echo(_payload_json(payload) if as_json else text)
    if payload["n_failed"]:
        raise typer.Exit(code=1)


@engine_app.command(name="decompose")
def decompose(
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
    since: Optional[str] = typer.Option(None, "--since", help="Only cycles on or after this UTC day (YYYY-MM-DD)."),
    until: Optional[str] = typer.Option(None, "--until", help="Only cycles on or before this UTC day (YYYY-MM-DD)."),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit the full payload as JSON on stdout instead of the table. A non-finite value (a flat cycle's "
        "0/0 cancellation ratio) is emitted as null.",
    ),
) -> None:
    """Attribute each journaled cycle's gross across the pipeline stages."""
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    records = _window_records(journal_root, since, until)
    try:
        text, payload = decompose_report(records, _snapshot_reader(journal_root))
    except EngineError as exc:
        raise _abort(str(exc)) from exc
    _emit_report(text, payload, as_json=json_out)


@engine_app.command(name="accum-replay")
def accum_replay(
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
    since: Optional[str] = typer.Option(None, "--since", help="Only cycles on or after this UTC day (YYYY-MM-DD)."),
    until: Optional[str] = typer.Option(None, "--until", help="Only cycles on or before this UTC day (YYYY-MM-DD)."),
    minimums: Optional[Path] = typer.Option(
        None,
        "--minimums",
        help=f"Venue reference-data snapshot the per-asset order minimums are read from. Defaults to the newest "
        f"{_REFDATA_GLOB} under the configured data dir's snapshots/ directory.",
    ),
    nav: Optional[list[float]] = typer.Option(
        None,
        "--nav",
        help="Portfolio size in EUR to measure the drift at; repeatable, e.g. --nav 1000 --nav 5000. Defaults to "
        + ", ".join(f"{value:,.0f}" for value in DEFAULT_NAVS)
        + ".",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit the full payload as JSON on stdout instead of the tables. A non-finite value is emitted as "
        "null, and the per-size drift table's keys are strings.",
    ),
) -> None:
    """Measure the position drift the venue's order minimums impose at each portfolio size."""
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    records = _window_records(journal_root, since, until)
    minimums_path = _resolve_minimums(minimums)
    try:
        floors, fetched_at = load_minimums(minimums_path)
    # TypeError belongs in here beside the others: a snapshot carrying `"ordermin": null` reaches
    # `float(None)` -- malformed evidence, answered with a clean one-line exit, never a traceback.
    except (OSError, KeyError, TypeError, ValueError, EngineError) as exc:
        raise _abort(f"could not read the venue order minimums from {minimums_path}: {exc}") from exc
    try:
        text, payload = accumulation_report(
            records,
            _snapshot_reader(journal_root),
            floors,
            list(nav) if nav else list(DEFAULT_NAVS),
            fetched_at=fetched_at,
        )
    except EngineError as exc:
        raise _abort(str(exc)) from exc
    _emit_report(text, payload, as_json=json_out)


# --- the weekly tracking comparison: what the book held against the floor, and what it cost -------


def _window_exec_records(journal_root: Path, since: str | None, until: str | None) -> list[dict]:
    """Every journaled execution record in the same inclusive UTC day window `_window_records` uses.
    An unreadable or schema-invalid record ABORTS rather than being skipped: the fills it carries move
    `held` for every LATER cycle, so dropping one quietly overstates the drift of the whole window."""
    since_day = _parse_day(since, "--since")
    until_day = _parse_day(until, "--until")
    out: list[dict] = []
    for boundary, path in _journal_artifacts(journal_root, "*", "exec-*.json"):
        if (since_day is not None and boundary.date() < since_day) or (until_day is not None and boundary.date() > until_day):
            continue
        try:
            doc = read_exec_record(path)
            validate_exec_record(doc)
        except (OSError, ValueError, EngineJournalError) as exc:
            raise _abort(
                f"unreadable execution record {path}: {exc} -- its fills move the position every later cycle "
                "is measured against, so skipping it would overstate the drift of the rest of the window; "
                "repair the record or exclude its day with --since/--until"
            ) from exc
        out.append(doc)
    return out


def _parse_gate_from(raw: str | None) -> str | None:
    """Validate `--gate-from` as a fixed-width ISO week label, or abort naming the form. Fixed width
    is load-bearing: `rung_by_week` compares week labels as STRINGS, and a one-digit week would sort
    `2026-W9` after `2026-W10` and hand the wrong weeks a rung."""
    if raw is None:
        return None
    year, sep, week = raw.partition("-W")
    if not (len(year) == 4 and year.isdigit() and sep and len(week) == 2 and week.isdigit() and 1 <= int(week) <= 53):
        raise _abort(f"--gate-from {raw!r} is not an ISO week of the form YYYY-Www, e.g. 2026-W29")
    return raw


def _rung_by_week(stages: list[CycleStages], gate_from: str | None) -> dict[str, int]:
    """Every window week labelled rung 3 from `gate_from` onward, rung 2 before it. Absent the flag
    this is EMPTY and `weekly_tracking` decides nothing: the operator names the boundary, because the
    first week that counts is a decision about the deployment, not a property of the journal."""
    if gate_from is None:
        return {}
    labels = {f"{s.cycle_ts.isocalendar().year}-W{s.cycle_ts.isocalendar().week:02d}" for s in stages}
    return {label: (3 if label >= gate_from else 2) for label in labels}


def _simulated_fills(stages: list[CycleStages], floor_cycles: list[dict], minimums: dict[str, tuple[float, float]]) -> list[Fill]:
    """The drift floor's own placements, dressed as fills at the journaled close -- the true-positive for the whole realized half,
    since with zero journaled fills every refusal in the tracking module is indistinguishable from a guard that always refuses. Fees
    are MODELLED at the builder's own maker rate, so the fee this yields is the current one by construction -- real-shaped, never a
    recalibration input."""
    cfg = CrossfreqSystemConfig()
    held: dict[str, float] = {}
    out: list[Fill] = []
    for stage, row in zip(sorted(stages, key=lambda s: s.cycle_ts), floor_cycles, strict=True):
        for asset, target in row["target_qty"].items():
            delta = target - held.get(asset, 0.0)
            ordermin_base, costmin = minimums[asset]
            close = stage.closes[asset]
            # The floor policy's own two independent gates, and its own assignment (`= target`,
            # never `+= delta`), so the simulated book tracks `accumulation_payload`'s held exactly.
            if abs(delta) < ordermin_base or abs(delta) * close < costmin:
                continue
            held[asset] = target
            out.append(
                Fill(
                    boundary=stage.cycle_ts,
                    at=stage.cycle_ts,
                    base=asset,
                    side="buy" if delta > 0 else "sell",
                    qty=abs(delta),
                    px=close,
                    fee=cfg.fee_per_side * abs(delta) * close,
                    liquidity="MAKER",  # the ladder places maker-first
                    # Unmistakable for a venue trade id, which matters because a ledger
                    # reconciliation matches on exactly this field.
                    trade_id=f"simulated:{asset}:{stage.cycle_ts.isoformat()}",
                )
            )
    return out


def _cost_over(fills: list[Fill], reconciliation: dict | None) -> dict:
    """The realized blend, with the PROPOSAL withdrawn when the ledger did not reconcile. The measurement stays -- it is
    what an operator investigates with -- but `proposed_fee_per_side` is the one number a `--json` consumer reads straight
    out without ever looking at `n_failed`, and a rate computed over a book the reconciliation has just declared incomplete
    must not be there to read. `basis` carries the reason in the PAYLOAD, not only in the rendered text."""
    cost = cost_blend(fills)
    if reconciliation is None or reconciliation["status"] != "FAILED":
        return cost
    return {
        **cost,
        "proposed_fee_per_side": None,
        "basis": f"{len(reconciliation['unmatched'])} ledger trade row(s) matched no journaled fill -- no rate "
        "proposed over a book the ledger could not reconcile",
    }


def _tracking_cell(value: float | None) -> str:
    """A drift cell: `no data` for a week whose realized series never started, `n/a` for a NaN."""
    if value is None:
        return f"{'no data':>11}"
    return f"{'n/a':>11}" if math.isnan(value) else f"{value:11.1f}"


def _tracking_note(week: dict) -> str:
    """Why a week carries no verdict, spelled out. The branches are exhaustive because `gate_eligible`
    is exactly `complete and rung == 3 and not straddles` and each one below eliminates a conjunct, so
    what reaches the straddle branch can only be straddling -- and an operator should not have to
    infer that from three flags."""
    if not week["complete"]:
        return "partial week"
    if week["rung"] is None:
        return "no gate boundary -- pass --gate-from"
    if week["rung"] != 3:
        return "before the gate boundary"
    if not week["gate_eligible"]:
        return "straddles the first fill"
    if week["realized_mean_bps"] is None:
        return "no realized data yet"
    return ""


def _render_tracking(payload: dict) -> str:
    """The weekly comparison, the window-wide floor, and the realized cost blend."""
    tracking, floor, cost = payload["tracking"], payload["floor"], payload["cost"]
    lines = [
        "Weekly tracking error: what the book actually held, against the drift floor the venue's minimums impose",
        f"Venue minimums read {payload['minimums_fetched_at']} -- these floors move, so a band quoted from an "
        "older table is stale, not conservative.",
        f"Portfolio size {payload['nav']:,.0f} EUR, held constant across the window.",
    ]
    if payload["simulated"]:
        lines += [
            "",
            "SIMULATED FILLS -- the realized half below is the floor policy's own placements at each journaled "
            "close, not trading that happened. Every number is real-shaped and none of it is real.",
        ]
    if len(payload["schema_versions"]) > 1:
        lines += [
            "",
            f"This window straddles a journal schema change (record schema {', '.join(str(v) for v in payload['schema_versions'])}): "
            "the older records key their targets by asset, the newer ones by traded symbol. Both replay, and the "
            "comparison below is in one key space -- but a week spanning the change mixes two recording regimes.",
        ]

    header = f"{'week':<10} {'cycles':>7} {'floor_p95':>11} {'real_mean':>11} {'within':>7}  note"
    lines += [
        "",
        "Per ISO week (bps of NAV): the floor's p95 over that week's cycles against the realized mean.",
        "",
        header,
        "-" * len(header),
    ]
    for week in tracking["weeks"]:
        within = "-" if week["within_band"] is None else ("yes" if week["within_band"] else "NO")
        lines.append(
            f"{week['iso_week']:<10} {week['cycles']:>7} {_tracking_cell(week['floor_p95_bps'])} "
            f"{_tracking_cell(week['realized_mean_bps'])} {within:>7}  {_tracking_note(week)}"
        )
    lines += [
        "-" * len(header),
        f"Verdict: {tracking['verdict']} at {payload['nav']:,.0f} EUR -- "
        f"{tracking['complete_gate_eligible_weeks']} decided week(s); a verdict needs at least 3, and a week is "
        "decided only when it is complete, sits on or after the gate boundary, and does not straddle the first fill.",
    ]
    if payload["gate_from"] is None:
        lines.append(
            "No gate boundary was named, so NOTHING above is decided whatever the numbers say -- pass "
            "--gate-from <YYYY-Www> naming the first week that counts. Every week's floor p95 and realized "
            "mean above are measured and unaffected by this."
        )
    else:
        lines.append(f"Gate boundary: weeks from {payload['gate_from']} onward count; earlier weeks are measured only.")
    lines += [
        "",
        f"Across the whole window, {payload['n_cycles']} cycles: floor median {_tracking_cell(floor['median_drift_bps']).strip()} bps, "
        f"floor p95 {_tracking_cell(floor['p95_drift_bps']).strip()} bps, placed on {floor['n_placed']} of them.",
    ]

    def rate(value: float | None) -> str:
        return "no data" if value is None else f"{10_000 * value:.1f} bps"

    lines += [
        "",
        "Realized cost, weighted by notional:",
        f"  fills {cost['n_fills']} ({cost['n_priced']} priced)",
        f"  maker {_share(cost['maker_share'])} / taker {_share(cost['taker_share'])} -- of the PRICEABLE book only; a "
        "fill the venue gave no side for is counted but has no side to split.",
        f"  fee per side: realized {rate(cost['realized_fee_per_side'])}, currently assumed "
        f"{rate(cost['current_fee_per_side'])} (plus {rate(cost['current_spread_per_side'])} of spread, priced separately)",
        f"  per fill: min {rate(cost['per_fill_min'])}, median {rate(cost['per_fill_median'])}, max {rate(cost['per_fill_max'])}",
        f"  basis: {cost['basis']}",
    ]
    if payload["simulated"]:
        lines.append("  the fees above are modelled at the assumed maker rate, so this blend cannot recalibrate anything.")

    reconciliation = payload["reconciliation"]
    if reconciliation is not None:
        lines += [
            "",
            f"Ledger export: {reconciliation['status']} -- {reconciliation['n_rows']} row(s) read, of which "
            f"{reconciliation['matched']} ledger trade row(s) matched a journaled fill.",
        ]
        if payload["simulated"]:
            lines.append(
                "  SIMULATED FILLS were compared against a real export, so every ledger trade row below is unmatched "
                "by construction -- a modelled fill carries no venue trade id. Nothing in this block is a finding."
            )
        lines.append(
            f"  rollover fees {reconciliation['rollover_fees_eur']:,.2f} EUR -- charged against the POSITION rather "
            "than against a fill, so no execution record carries them and the blend above omits them."
        )
        if reconciliation["ignored"]:
            lines.append(
                "  row types this reader places nowhere: "
                + ", ".join(f"{kind} {count}" for kind, count in sorted(reconciliation["ignored"].items()))
                + " -- counted, never matched. A margin position writes rows sharing its trade's id, and what those "
                "mean is settled against a real export rather than guessed here."
            )
        if reconciliation["unmatched"]:
            lines += [
                "  The account traded what this journal does not know about. Every id below is a venue trade with no "
                "journaled fill behind it, so the cost above is measured over an incomplete book:",
            ] + [f"    {refid}" for refid in reconciliation["unmatched"]]

    if payload["notes"]:
        lines += ["", "Notes that disabled part of the report:"] + [f"  {note}" for note in payload["notes"]]
    # Gated on `failures`, never on `n_failed`: the latter also carries a failed ledger
    # reconciliation, which is not a cycle and would be announced here as one.
    if payload["failures"]:
        lines += ["", f"Cycles failed to replay: {len(payload['failures'])} (excluded from every number above)"]
        lines += [f"  {f['cycle_ts']}  {f['error']}" for f in payload["failures"]]
    return "\n".join(lines)


def _share(value: float | None) -> str:
    return "no data" if value is None else f"{100 * value:.1f}%"


@engine_app.command(name="tracking-report")
def tracking_report(
    journal_dir: Optional[Path] = typer.Option(
        None, "--journal-dir", help="Journal root to read instead of the configured journal_dir (e.g. a pulled VPS journal)."
    ),
    since: Optional[str] = typer.Option(None, "--since", help="Only cycles on or after this UTC day (YYYY-MM-DD)."),
    until: Optional[str] = typer.Option(None, "--until", help="Only cycles on or before this UTC day (YYYY-MM-DD)."),
    minimums: Optional[Path] = typer.Option(
        None,
        "--minimums",
        help=f"Venue reference-data snapshot the per-asset order minimums are read from. Defaults to the newest "
        f"{_REFDATA_GLOB} under the configured data dir's snapshots/ directory.",
    ),
    nav: Optional[float] = typer.Option(
        None,
        "--nav",
        help="Portfolio size in EUR to compare at. Single-valued, unlike accum-replay's sweep: this command issues "
        "one verdict, and the sibling's list starts at a size whose floor is far wider than the ratified basis, "
        "so a bare run there could only ever read too kindly. Defaults to the configured shadow portfolio size, "
        "which is also the size the engine itself trips at.",
    ),
    gate_from: Optional[str] = typer.Option(
        None,
        "--gate-from",
        metavar="YYYY-Www",
        help="The first ISO week that counts toward the verdict (e.g. 2026-W29); earlier weeks are measured but "
        "never decided. Absent, NO week is decided -- eligibility fails closed, because a week nobody has "
        "declared in-scope must not be able to produce a pass.",
    ),
    simulated_fills: bool = typer.Option(
        False,
        "--simulated-fills",
        help="Replace the journaled fills with the drift floor's own modelled placements, so the whole comparison "
        "can be exercised before any real fill exists. Every figure it produces is labelled and none of it is real.",
    ),
    ledger_export: Optional[Path] = typer.Option(
        None,
        "--ledger-export",
        help="A Kraken ledger export (CSV, from History -> Export -> Ledgers) to reconcile the window's fills "
        "against. It is the only place a margin position's rollover fee appears -- the venue charges it against "
        "the POSITION, so no fill carries it and a cost basis built from fills alone omits it. Absent, the report "
        "simply omits the reconciliation: the export is a hand-made artifact and most runs will not have one.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit the full payload as JSON on stdout instead of the tables. A non-finite value is emitted as null.",
    ),
) -> None:
    """Compare each ISO week's realized drift against the venue-minimum floor, and reprice the cost."""
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    records = _window_records(journal_root, since, until)
    minimums_path = _resolve_minimums(minimums)
    try:
        floors, fetched_at = load_minimums(minimums_path)
    except (OSError, KeyError, TypeError, ValueError, EngineError) as exc:
        raise _abort(f"could not read the venue order minimums from {minimums_path}: {exc}") from exc
    # `shadow_nav_eur`, never DEFAULT_NAVS[0]: component C trips at the configured size, so taking any
    # other default here would band the human at one NAV while the engine trips at another.
    nav_value = nav if nav is not None else config.shadow_nav_eur
    gate_week = _parse_gate_from(gate_from)

    reader = _snapshot_reader(journal_root)
    stages: list[CycleStages] = []
    failures: list[dict] = []
    for record in sorted(records, key=lambda r: r.cycle_ts):
        try:
            stages.append(replay_stages(record, reader))
        except EngineError as exc:
            failures.append({"cycle_ts": record.cycle_ts.isoformat(), "error": str(exc)})

    notes: list[str] = []
    # Both halves inside one catch: `accumulation_report` drops a record whose replay raises, a fill
    # journaled under that dropped boundary then orphans, and `realized_drift` refuses rather than
    # overstating every later cycle -- that refusal must surface as a clean one-line exit.
    try:
        floor = accumulation_payload(stages, floors, [nav_value])["by_nav"][nav_value]
        if simulated_fills:
            fills = _simulated_fills(stages, floor["cycles"], floors)
        else:
            fills, notes = extract_fills(_window_exec_records(journal_root, since, until))
        tracking = weekly_tracking(stages, fills, floors, nav_value, rung_by_week=_rung_by_week(stages, gate_week))
    except EngineError as exc:
        raise _abort(str(exc)) from exc

    # An export whose HEADER cannot be mapped aborts, unlike an unmatched row: nothing was read, so
    # there is no reconciliation to report either way. Most runs have no export at all.
    reconciliation = None
    if ledger_export is not None:
        try:
            reconciliation = reconcile_ledger(read_ledger_export(ledger_export), fills)
        except (OSError, EngineError) as exc:
            raise _abort(f"could not read the ledger export {ledger_export}: {exc}") from exc

    payload = {
        "nav": nav_value,
        "gate_from": gate_week,
        "n_cycles": len(stages),
        "tracking": tracking,
        "floor": floor,
        "cost": _cost_over(fills, reconciliation),
        "reconciliation": reconciliation,
        "schema_versions": sorted({record.schema_version for record in records}),
        "simulated": simulated_fills,
        "minimums_fetched_at": fetched_at,
        "notes": notes,
        # A failed reconciliation joins the exit-code count -- the only thing a script reading this
        # notices -- but stays OUT of `failures`, which is the per-cycle replay list.
        "n_failed": len(failures) + (1 if reconciliation is not None and reconciliation["status"] == "FAILED" else 0),
        "failures": failures,
    }
    _emit_report(_render_tracking(payload), payload, as_json=json_out)


@engine_app.command(name="exec-status")
def exec_status(
    state_dir: Optional[Path] = typer.Option(
        None,
        "--state-dir",
        help="Engine state directory to read the control files from. Defaults to the configured journal_dir's parent.",
    ),
) -> None:
    """Report whether the engine may submit orders right now, and every input that decided it.

    Remote telemetry can only say THAT the engine is disarmed, never WHICH key is missing -- `zcrypto_exec_armed` conflates its two arming keys into one gauge. This command reads the same gate on the host and prints every reason and every input."""
    config = _load_engine_config()
    root = state_dir if state_dir is not None else config.journal_dir.parent
    gate = ExecutionGate(
        armed_in_config=config.exec_armed,
        state_dir=root,
        venue_reader=read_system_status,  # explicit so tests can substitute it (no --no-venue-check flag)
    )
    verdict = gate.evaluate(_utc_now())
    _echo_gate_verdict(verdict)


def _echo_gate_verdict(verdict: GateVerdict) -> None:
    typer.echo(f"level={verdict.level}")
    typer.echo(f"reasons={','.join(verdict.reasons) or '-'}")
    for key, value in sorted(verdict.inputs.items()):
        typer.echo(f"  {key}={value}")


@engine_app.command()
def flatten(
    state_dir: Path = typer.Option(
        ...,
        "--state-dir",
        help="Engine state directory holding the control files and receiving this run's record. Required: this command must not depend on a config file when the environment is what broke.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually send. Without it the account is read, the plan is printed and nothing is sent.",
    ),
) -> None:
    """Close every open position and sell every non-EUR balance at market, account-wide.

    Without `--execute` it reads the account, prints the plan and stops. With `--execute` it needs the engine's kill file already in place, asks for a typed confirmation on the terminal, then cancels every resting order, closes every margin position reduce-only, and sells every non-EUR balance -- all at market, all journaled. Exit 0 the account reads flat, 1 refused with nothing sent, 2 something is still open, 3 the venue could not be read before anything was sent. The cancel is account-wide and complete; the flat verdict is not -- neither the plan nor the final read can see a resting order on BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR or ETH/BTC, so exit 0 is not proof those pairs are clear: confirm open orders on Kraken's own page, and re-run if one is there."""
    # Lazy: `cli.engine.flatten` pulls nautilus (~1 s) and `zcrypto --help` must never pay it.
    from cli.engine.flatten import run_flatten

    key = os.environ.get(_API_KEY_VAR)
    secret = os.environ.get(_API_SECRET_VAR)
    missing = [name for name, value in ((_API_KEY_VAR, key), (_API_SECRET_VAR, secret)) if not value]
    if missing:
        # The refusal names the VARIABLES and never their contents.
        raise _abort(f"the trade credentials are not in this environment: {', '.join(missing)}")

    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    client = KrakenSpotHttpClient(key, secret)
    # `raise typer.Exit(code=...)`, never `return`: a returned int is discarded and the process exits 0, which would turn every
    # refusal and every not-flat account into a clean-looking run. `asyncio.run` is the only place a loop is opened: the client's
    # methods raise `RuntimeError: no running event loop` outside one, so called synchronously this command would exit 3 on its very
    # first read, `--execute` included. `echo` is passed bare -- `run_flatten` owns the dead-stdout guard.
    raise typer.Exit(code=asyncio.run(run_flatten(client, state_dir=state_dir, execute=execute, echo=typer.echo)))


def _newest_venue_record(journal_dir: Path) -> dict | None:
    """The newest `ok`, schema-2 `venue-<HH>.json` document in full, or None when the journal holds
    none -- `_seed_exec_positions`' scan kept whole, because this caller needs the instrument
    constraints and the balances both. Same no-try/except contract: reading past a record that fails
    `validate_venue_record` would make every floor below fail open."""
    from cli.engine.venueledger import read_venue_record, validate_venue_record

    newest: tuple[datetime, dict] | None = None
    for _, path in _journal_artifacts(journal_dir, "*", "venue-*.json"):
        doc = read_venue_record(path)
        validate_venue_record(doc)
        if doc.get("status") != "ok" or doc.get("schema_version") != 2:
            continue
        cycle_ts = datetime.fromisoformat(doc["cycle_ts"])
        if newest is None or cycle_ts > newest[0]:
            newest = (cycle_ts, doc)
    return None if newest is None else newest[1]


def _intent_floor_check(index: int, intent, entry: dict) -> tuple[str, list[str]]:
    """One intent's checkable floors against one venue-snapshot instrument entry: the printable line, and every refusal it
    earned. A notional intent is compared against `costmin` ONLY when both are EUR -- a EUR notional against a `/BTC` leg's
    own floor passes everything silently, the fail-open direction `size_probe_order`'s guard refuses at sizing time. A qty
    intent carries no price here, so it meets `ordermin` and the lot step instead."""
    refusals: list[str] = []
    head = f"  [{index}] {intent.symbol} {intent.side} {intent.action} {intent.mode}"
    if intent.mode == "rest-hold":
        # The two fields that decide whether this order can FILL, on the only surface an operator
        # reads before placing it. `offset_pct` is a PERCENT: 0.05 is fifteen euro off a 30k euro bid.
        head += f" ({intent.offset_pct:g}% passive of the touch, holding {intent.hold_minutes} min)"
    if intent.notional_eur is not None:
        quote = entry["costmin_quote"]
        if quote != "EUR":
            return (
                f"{head}: notional {intent.notional_eur:.2f} EUR -- NOT COMPARED",
                [
                    f"intent {index}: {intent.symbol}'s costmin is denominated in {quote!r}, so it cannot be "
                    "compared against a EUR notional"
                ],
            )
        costmin = float(entry["costmin"])
        if intent.notional_eur < costmin:
            refusals.append(f"intent {index}: notional {intent.notional_eur:.2f} EUR is below costmin {costmin:.2f} EUR")
        return f"{head}: notional {intent.notional_eur:.2f} EUR, costmin {costmin:.2f} EUR", refusals

    ordermin = float(entry["ordermin"])
    lot_step = float(entry["lot_step"])
    if intent.qty < ordermin:
        refusals.append(f"intent {index}: qty {intent.qty:.10g} is below ordermin {ordermin:.10g}")
    if lot_step <= 0:
        refusals.append(f"intent {index}: the venue snapshot's lot step for {intent.symbol} is {lot_step!r}, not a positive step")
    elif _floor_to_step(intent.qty, lot_step) != intent.qty:
        refusals.append(f"intent {index}: qty {intent.qty:.10g} is not a multiple of the {lot_step:.10g} lot step")
    return f"{head}: qty {intent.qty:.10g}, ordermin {ordermin:.10g}, lot step {lot_step:.10g}", refusals


@engine_app.command(name="probe-plan")
def probe_plan(
    plan_path: Path = typer.Argument(..., help="Probe plan JSON file to validate."),
    check: bool = typer.Option(
        False,
        "--check",
        help="Validate the plan offline: shape, expiry, duplicate plan ids, the plan-level caps, and each intent "
        "against the newest venue snapshot's constraints. Advisory only -- the engine re-validates every plan live "
        "before any order.",
    ),
) -> None:
    """Validate an operator-authored probe plan against the newest journaled venue snapshot.

    Read-only and offline: it reads the plan file, the journal, and the control-file tree, and writes nothing anywhere. The gate verdict it prints is a REPORT, never a permission -- the engine evaluates the gate itself inside every submission, so a plan that validates cleanly while the gate is shut is still a valid plan."""
    if not check:
        raise _abort("only --check is implemented -- the engine consumes plans from its state directory, never from this command")

    config = _load_engine_config()
    try:
        text = plan_path.read_text()
    except OSError as exc:
        raise _abort(f"could not read the probe plan {plan_path}: {exc}") from exc
    try:
        plan = parse_plan(text)
    except ProbePlanError as exc:
        raise _abort(str(exc)) from exc

    try:
        record = _newest_venue_record(config.journal_dir)
    except (OSError, EngineJournalError, KeyError, TypeError, ValueError) as exc:
        raise _abort(f"the newest venue snapshot under {config.journal_dir} could not be read: {exc}") from exc
    if record is None:
        raise _abort(
            f"no usable venue snapshot under {config.journal_dir} -- the per-intent floors are read from one, "
            "and a plan checked without it would report floors it never measured"
        )
    instruments = record["state"]["instruments"]
    balances = record["state"]["balances"]

    gate = ExecutionGate(armed_in_config=config.exec_armed, state_dir=config.journal_dir.parent, venue_reader=read_system_status)
    now = _utc_now()
    _echo_gate_verdict(gate.evaluate(now))
    typer.echo(f"venue snapshot: {record['state']['snapshot_at']}")

    # The live balances spell the free-cash currency `EUR` (read from a live balance record), so this
    # resolves on its SECOND arm; the `ZEUR` arm stays because the adapter's other surface spells the
    # euro `ZEUR`. Both absent reads 0.0, which refuses any margin intent.
    free_zeur = balances.get("ZEUR", 0.0) or balances.get("EUR", 0.0)
    refusals = list(
        plan_refusals(
            plan,
            now=now,
            ledgered=ledgered_plan_ids(config.journal_dir, now),
            max_plan_notional_eur=config.exec_max_plan_notional_eur,
            free_zeur=float(free_zeur),
        )
    )
    for index, intent in enumerate(plan.intents):
        entry = instruments.get(intent.symbol)
        if entry is None:
            refusals.append(f"intent {index}: {intent.symbol} is absent from the venue snapshot")
            continue
        line, intent_refusals = _intent_floor_check(index, intent, entry)
        typer.echo(line)
        refusals.extend(intent_refusals)

    if refusals:
        raise _abort("plan refused: " + "; ".join(refusals))
    total = sum(i.notional_eur or 0.0 for i in plan.intents)
    typer.echo(f"plan ok: {len(plan.intents)} intent(s), total notional {total:.2f} EUR")
