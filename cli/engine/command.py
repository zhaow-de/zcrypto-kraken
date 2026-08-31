"""The `zcrypto engine` Typer sub-app (spec 00041 SS the CLI): seed the live price store, run the
shadow node, run one cycle manually, replay journaled cycles through the builder, evaluate the
ratified gate, and export the gate as machine-readable metrics + a dead-man's-switch ping. Config
errors and EngineErrors surface as clean one-line exits, never tracebacks.

`cli.engine.node` (and with it nautilus-trader, ~1 s of import time) is imported lazily inside the
command bodies that need it -- `zcrypto --help` must never pay the nautilus import.
"""

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
# The two variables carrying the trade credentials, rendered onto the engine host by the deploy.
# Named here so a refusal can say WHICH is missing without ever touching a value.
# `cli/engine/node.py` defines the same two names for the same reason. The copy is deliberate and
# not shared: importing them would pull nautilus into this module's scope and defeat the lazy
# import that keeps `zcrypto --help` off the ~1 s adapter load. `engine.env.j2` renders both.
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
    """A clean one-line error (logged, no traceback) + exit code 1. Usage: `raise _abort(...)`.

    LOGS rather than `typer.echo`s. The line has to carry a level, or Alloy cannot label it at
    ingest (infra/nas/config.alloy) and the level-based alerting never sees it -- `engine
    gate-export` reports every failure through one of this helper's call sites. The older text-grep
    alert matched the literal `ERROR:` prefix this used to print; the label-based rule that replaced
    it did not, which is exactly the blindness T0041 records.
    """
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
    """_evaluate_journal's per-run scoring-cache tally (spec 00060 D8): how many success records
    this run actually replayed vs served from cache, and whether the cache was discarded wholesale
    (a schema/replay-fingerprint mismatch or an unreadable file) -- all zero/False when `cache_path`
    is None, so a degrading cache is visible in the metrics rather than looking like a working one.
    A forced rotation re-verification (spec 00062 D4/D1) counts in `replayed`, never `from_cache` --
    a forced-replay failure is a real gate failure, not a cache event.

    `oldest_verification_age` (spec 00062 D5) is `now - min(verified_at)` across the cache's final
    (post-run) entries, in seconds; None when the cache is inactive or empty. Makes a rotation that
    silently stops visible rather than indistinguishable from a healthy cache."""

    replayed: int
    from_cache: int
    invalidated: bool
    oldest_verification_age: float | None


_EVALUATE_JOURNAL_REPLAY_PATH = "fast"  # threaded into replay_fingerprint() below (spec 00060 D3)


def _replay_one(record: CycleRecord, reader) -> CycleOutcome:
    """Replay one journaled success record and classify the outcome -- factored out so a cache hit
    and a fresh replay build the exact same CycleOutcome shape; _evaluate_journal derives its
    counters from that outcome afterward, in one place, so neither path can silently undercount."""
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
    """Replay every journaled cycle-*.json (fast path) and classify every failed-cycle-*.json
    sidecar into CycleOutcome entries -- report's and gate-export's shared evidence-gathering pass.
    Absent boundaries are NOT fabricated -- evaluate_gate scores them missing. The third element is
    the newest cycle_ts seen across every outcome (None when the journal is empty).

    `cache_path` (spec 00060, opt-in -- None is today's full replay, byte-for-byte) reuses a prior
    run's CycleOutcome for a success record whose evidence_fingerprint is unchanged, skipping
    replay_cycle entirely for that cycle; sidecars and unparseable records are never cached (D7).
    JournalCounts is always derived from the resulting outcome (cached or freshly replayed) in one
    place below, never from which branch produced it -- a cache hit must count exactly like a
    replay would have. The fourth element, CacheStats, is spec 00060 D8's observability tally.

    `cache_path is None` takes exactly the pre-`--cache` code path: neither `replay_fingerprint` nor
    `evidence_fingerprint` is ever called, so a bug in either (e.g. replay_fingerprint's unguarded
    `read_bytes()` over the ~60-module import closure) can never reach a no-cache caller like `report` -- D1's
    byte-for-byte promise, structurally. When `cache_path` is set but `replay_fingerprint()` itself
    raises OSError, that's caught here and degrades THIS RUN to the same no-cache path (logged, never
    aborted) -- a cache is an optimization, gate evidence is not. Same principle per record for
    `evidence_fingerprint`: a failure there means "replay this one cycle", never "abort the run".

    `now` (spec 00062, threaded from the caller rather than read via `_utc_now()` here so tests can
    drive the clock) also decides, per otherwise cache-eligible cycle, whether this run FORCES a
    replay regardless of a cache hit: `due_for_reverification(record.cycle_ts, now)` is true for
    exactly 1/24 of cycles per run (D2/D3), so the whole journal is re-verified about daily even
    with the cache warm -- the parquet bytes are re-hashed by `replay_cycle`'s own check, which a
    cache hit would otherwise skip forever. A forced replay that fails is a real gate failure (D4):
    it produces the same CycleOutcome any replay would and is counted in `replayed`, never
    `from_cache`."""
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

    # Counters derived from the resulting outcome, in one place -- see the docstring's THE TRAP note.
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
    """The gate-export dead-man's-switch ping (spec 00042, mirroring cli/engine/cycle.py's
    _ping_healthcheck): GET `url` on a clean gate, GET `url + "/fail"` otherwise -- one attempt,
    10 s timeout, ANY exception swallowed via logger.warning; the ping can never fail the export."""
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
    """Atomically write the gate-export Prometheus textfile-collector metrics: write to a `.tmp`
    sibling then `os.replace` onto `path`, so a node-exporter scrape never observes a partial file
    and a write failure (e.g. an unwritable parent) leaves no partial artifact behind. The cache
    metrics (spec 00060 D8) are always emitted, zeroed/False when `--cache` was omitted, so a
    silently-degrading cache is visible rather than looking indistinguishable from a working one.
    `zcrypto_gate_cache_replayed`/`_hits` (spec 00062 D7) carry no `_total` suffix -- they are
    per-run gauges, not monotonic counters; enabling `--cache` drops `replayed` from N to ~1, which
    `rate()`/`increase()` would otherwise read as a counter reset. `_oldest_verification_age_seconds`
    (D5) is omitted, like `_journal_pull_lag_seconds`, when there is nothing to report (cache
    inactive or empty)."""
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
    """The engine's cumulative gauge/counter state (spec 00069 D5, engine's pinned instrument
    set): `run()` builds one of these on the SAME registry the exporter serves, then installs
    `.update` as `cycle.py`'s metrics sink -- called after every cycle, success or failure.
    `cycle_success` is registered LAZILY (`seed_cycle_success`), not here -- see that method
    (cold-review I4); `active_sleeves` and `cycle_duration` are lazy for the same reason, see
    their own comments below."""

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
        # A Gauge, not a Counter: the pinned name (spec 00069 D5, "names verbatim") carries no
        # `_total` suffix, and `Counter` would silently ADD one to the exposed series name --
        # `Gauge` exposes exactly the name given while `.inc()` still makes it cumulative. Caveat:
        # unlike its sibling `orders_total` (a real Counter), this Gauge only carries counter
        # SEMANTICS via `.inc()` -- `rate()`/`increase()` are undefined over it, and a process
        # restart drops it back to 0 with no built-in reset marker: `disable_created_metrics()`
        # (cli/obs/metrics.py) suppresses even a real Counter's own `_created` sample fleet-wide,
        # so that escape hatch isn't available here either.
        self.order_notional_eur = Gauge(
            "zcrypto_engine_order_notional_eur", "Intended order notional (EUR), summed across every cycle.", registry=registry
        )
        self.cycle_success: Gauge | None = None  # lazy -- see seed_cycle_success (cold-review I4)
        self.cycle_completed_at = Gauge(
            "zcrypto_engine_cycle_completed_at_seconds", "Unix timestamp the most recent cycle completed at.", registry=registry
        )
        # Lazy for exactly `seed_cycle_success`'s reason: a freshly-registered Gauge defaults to
        # 0.0, and "the last cycle took 0 seconds" before any cycle has run (or completed since a
        # restart) is a claim the engine has not measured -- false. Deliberately not seeded from
        # the journal either, unlike `cycle_completed_at`/`cycle_success`: the artifact does carry
        # the endpoints (started_at/attempted_at + completed_at), but a previous process's
        # duration is not this process's, so `update()` is the only place it is honestly known.
        # An absent series is honest; a published 0 is a claim.
        self.cycle_duration: Gauge | None = None
        self.sleeve_gross = Gauge(
            "zcrypto_engine_sleeve_gross",
            "Latest per-sleeve gross exposure (sum of absolute target weights).",
            ["sleeve"],
            registry=registry,
        )
        # Lazy for exactly `seed_cycle_success`'s reason, and it is the crux here: `sleeve_gross`
        # above is LABELLED, so it is honest for free -- a labelled Gauge publishes nothing until
        # `.labels()` is first called. This one is UNLABELLED, so registering it eagerly would
        # publish 0.0 from process start, and "no sleeve is carrying exposure" before any cycle has
        # run is a claim the engine has not measured -- false, and it would also become the
        # baseline the composition-changed alert reads the first real cycle against. An absent
        # series is honest; a published 0 is a claim.
        self.active_sleeves: Gauge | None = None

    def seed_cycle_success(self, success: bool) -> None:
        """Register (if not already) and set `zcrypto_engine_cycle_success` (spec 00069 D5,
        cold-review I4): called both at startup -- when the newest journal artifact tells us the
        last known outcome -- and from `update()` after every real cycle. Left UNREGISTERED, no
        series at all, until a value is actually known: a freshly built `Gauge` defaults to 0.0,
        and publishing that before any cycle has run (or completed since a restart) would read as
        "the last cycle failed" for up to the 4h until the next one -- false. An absent series is
        honest; a published 0 is a claim."""
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
            # Retire assets that left the target set: a weight left behind keeps publishing its last
            # value for the life of the process. remove(), not set(0) -- a zero weight and a
            # not-in-the-book asset are different states and the executor must tell them apart.
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
    """The execution envelope's published state. Built on the SAME registry the exporter serves,
    exactly as `_CycleGauges` is, and updated from the gate's verdict after every cycle.

    `zcrypto_exec_gate_level` is registered EAGERLY and seeded at 0: before anything is evaluated,
    "nothing may be submitted" is the true state, not an unmeasured claim -- the engine really is
    refusing. The other presence gauges are eager for the same reason, and `run()` evaluates once
    at startup so none of them sits at its seeded default: a `kill_tripped` reading 0 while the
    kill file exists is not a stale gauge, it is a false statement about the safety envelope.
    `last_evaluation` is LAZY for `_CycleGauges.cycle_duration`'s reason: a published 0 before any
    evaluation would claim the gate was last read at the Unix epoch, and an absent series is
    honest where a zero is a lie -- which matters doubly here, since the staleness alert reads
    this series and a seeded 0 would page instantly on every fresh process.
    """

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
        # The envelope's heartbeat, and the ONLY series that can answer "is the gate still being
        # evaluated at all". A snapshot-AGE gauge was rejected: evaluations are hours apart and the
        # snapshot bound is 30 s, so every evaluation re-reads and the age would publish ~0 forever
        # -- a constant wearing a measurement's clothes. Lazy for `_CycleGauges.cycle_duration`'s
        # reason: before the first evaluation there is no timestamp to state.
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
# call sites by tests/test_engine_metrics.py. `ambiguous` is load-bearing and must never be folded
# into `refused`: "refused" asserts that no order exists, and after a submission whose venue outcome
# was never established that claim is unavailable -- the same lie a prior ruling removed from the
# forensic ledger.
_EXEC_ORDER_OUTCOMES = ("submitted", "accepted", "rejected", "venue_canceled", "canceled", "filled", "refused", "ambiguous")
# Every name the venue's own `LiquiditySide` can produce, lower-cased -- pinned against the real
# enum by tests/test_engine_metrics.py rather than derived here, because importing nautilus-trader
# at this module's top level would put ~1 s on `zcrypto --help`. `no_liquidity_side` is deliberate
# and pre-registered like the other two: a fill the venue did not attribute is still a fill, and
# neither silently counting it as taker nor letting a third label appear at runtime is acceptable
# when the maker-vs-taker split is the number this ladder exists to measure.
_EXEC_LIQUIDITY_SIDES = ("maker", "taker", "no_liquidity_side")
# Every disposition `cli/engine/executor.py`'s `_inc_external` can emit, pinned against that
# module's own call sites by tests/test_engine_metrics.py. `unmatched` is the load-bearing one: an
# order event arriving on the external strategy topic that belongs to no order this engine's ledger
# vouches for is counted and ignored, and this counter is the only trace it leaves.
_EXEC_EXTERNAL_DISPOSITIONS = ("matched", "unmatched")


class _ExecutionMetrics:
    """What the executor did, as opposed to `_ExecGauges`' what it was ALLOWED to do. Built on the
    SAME registry as `_CycleGauges`/`_ExecGauges` and installed on the executor's telemetry hooks,
    which are wrapped at every call site there -- nothing here can alter or stop a submission.

    Every counter's label children are registered up front, unlike the gauges above whose absent
    series are the honest state: a Counter's zero is a MEASURED fact ("nothing has been refused
    yet"), where a Gauge's would be an unmeasured claim, and a `rejected` series that springs into
    existence at the first rejection gives `rate()` no baseline and reads exactly like a scrape gap
    until then. `position` is the exception -- symbol-labelled, so it publishes only the symbols
    `run()`'s seed or a fill has actually named.

    `realized_pnl` is a Gauge because realized PnL falls; it is registered eagerly at 0, which is
    true of a fresh process before its first trade. It is NOT seeded from disk, so a process
    restarted mid-probe reads 0 until its next fill -- accepted here because the probe windows are
    attended and the engine is converged only in the inter-cycle gap.
    """

    def __init__(self, registry) -> None:
        self._registry = registry
        self.orders = Counter("zcrypto_exec_orders_total", "Executor orders by outcome.", ["outcome"], registry=registry)
        self.fills = Counter("zcrypto_exec_fills_total", "Order fills by liquidity side.", ["liquidity"], registry=registry)
        self.fees = Counter("zcrypto_exec_fees_eur_total", "Trading fees paid, in EUR.", registry=registry)
        self.position = Gauge(
            "zcrypto_exec_position", "Net position quantity by symbol, in base units.", ["symbol"], registry=registry
        )
        self.realized_pnl = Gauge("zcrypto_exec_realized_pnl_eur", "Realized profit and loss, in EUR.", registry=registry)
        self.external_events = Counter(
            "zcrypto_exec_external_events_total",
            "Order events arriving on the external strategy topic, by disposition: matched means the "
            "event belonged to a restart-adopted order this engine's ledger vouches for; unmatched "
            "means it belonged to no such order and was acted on nowhere -- the account owner's own "
            "hand settle, or equally activity nobody sanctioned.",
            ["disposition"],
            registry=registry,
        )
        # The weekly tracking-error verdict, registered on FIRST USE for
        # `_ExecGauges.last_evaluation`'s reason and one of its own: every value it can take means
        # something, and a series that existed before the first boundary was scored could only
        # publish a code outside that alphabet -- a 0 that renders as a legitimate reading rather
        # than as the "nothing has been scored yet" it would actually be.
        self.tracking_state: Gauge | None = None
        for outcome in _EXEC_ORDER_OUTCOMES:
            self.orders.labels(outcome=outcome)
        for liquidity in _EXEC_LIQUIDITY_SIDES:
            self.fills.labels(liquidity=liquidity)
        for disposition in _EXEC_EXTERNAL_DISPOSITIONS:
            self.external_events.labels(disposition=disposition)

    def inc_order(self, outcome: str) -> None:
        self.orders.labels(outcome=outcome).inc()

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
        """What the last 4-hourly boundary decided about the most recently closed week. The help
        text carries the whole alphabet because this gauge is read on a board, where a bare number
        means nothing -- and every code it lists is one the executor can really publish."""
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
    """The venue-truth family (spec 00089 D6). Built on the SAME registry as `_CycleGauges` and
    `_ExecGauges`, updated from the metrics sink when `CycleResult.venue` is present -- and seeded
    at startup from the newest on-disk `venue-<HH>.json` (`_seed_venue_state`, mirroring
    `_seed_cycle_state`'s reasoning for `zcrypto_engine_cycle_completed_at_seconds`). Without that
    seed, a routine engine restart -- which always lands inside the inter-cycle gap
    (`fleet-deploys.md`) -- would leave every gauge at its eager default until the NEXT boundary
    cycle, and `zcrypto-venue-snapshot-stale` would false-page "the writer has stopped" against an
    engine that merely restarted (cold-review MAJOR 1).

    All four are registered EAGERLY, unlike `_ExecGauges.last_evaluation`:
    `zcrypto_venue_snapshot_timestamp_seconds` is a TIMESTAMP, never an age -- an age gauge freezes
    at a healthy-looking value when its writer dies, which is the exact failure this must surface,
    and an UNSEEDED 0.0 (a brand-new deployment with no journal yet, or the startup seed read itself
    failing) reads as honestly ancient (1970), never a false "just happened". `instruments_expected`
    is seeded from `len(INSTRUMENT_IDS)` -- DERIVED, never a literal 12, so a future basket
    re-ratification moves one committed place.
    """

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
    """The startup seed for BOTH `zcrypto_engine_cycle_completed_at_seconds` and
    `zcrypto_engine_cycle_success` (spec 00069 D5; the latter cold-review I4): the newest journal
    artifact's own `completed_at` wall-clock time and outcome -- a success record scores
    `(completed_at, True)`, a failed-cycle sidecar scores `(completed_at, False)`, whichever
    artifact is actually newer wins -- so a routine restart never leaves either series
    false-firing (missing and stale, or a false "last cycle failed"). The completed_at half falls
    back to process start (`_utc_now()`) when the journal holds nothing yet (a brand-new
    deployment); the success half then has no honest answer at all, so it comes back `None` -- the
    caller must leave `zcrypto_engine_cycle_success` UNREGISTERED rather than publish a false 0.
    Reuses this module's own `_journal_artifacts` glob (the same day-dir layout `node.py`'s
    `startup_action` walks, though that one does not glob)."""
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
    """The startup seed for `_VenueGauges` (spec 00089 D6, cold-review MAJOR 1): the newest
    `venue-<HH>.json` whose `status` is `"ok"`, reduced to the same `{"loaded", "expected",
    "failures", "snapshot_at"}` shape `cli.engine.cycle._record_venue_state` puts on
    `CycleResult.venue` -- so `run()` can feed it straight into `_VenueGauges.update`. An `"error"`
    record (no `VenueState` that cycle) is skipped rather than treated as newer: the last REAL
    snapshot must keep aging honestly, the same "absence never overwrites a real value" invariant
    `_VenueGauges.update` itself enforces for `venue=None`. Returns `None` when the journal holds no
    readable `ok` record yet (a brand-new deployment) -- the caller then leaves every gauge at its
    eager default, exactly `_seed_cycle_state`'s `success=None` case.

    Deliberately NO try/except of its own, mirroring `_seed_cycle_state`: an unreadable file
    (PermissionError) or a malformed record propagates to the caller's own guard, which must never
    let telemetry setup kill the engine daemon. Every record is `validate_venue_record`-checked
    before its `status` is even consulted (T0140 D9) -- a record that fails to validate is a
    malformed record, and the caller's guard is exactly where that must surface, never a silent skip.

    Local import: `cli.engine.venueledger` pulls in `cli.engine.venuestate`, which imports
    nautilus_trader (~1s) at module level -- deferred to here for the same reason `cycle.py`'s
    `_record_venue_state` defers it, so `cli.engine.command`'s own module-level import stays
    nautilus-free (`zcrypto --help`)."""
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
    """The startup seed for the (symbol-labelled) positions gauge: the newest `venue-<HH>.json`
    whose `status` is `"ok"` AND `schema_version == 2`, reduced to `dict(doc["state"]["positions"])`
    -- a base-keyed schema_version 1 record is skipped even when `"ok"`, never coerced, because the
    gauge it seeds is symbol-labelled and a v1 record cannot honestly produce that label. Mirrors
    `_seed_venue_state` above: same glob/newest logic, same no-try/except contract (the caller's own
    telemetry guard owns isolation), same `validate_venue_record`-before-`status` ordering (T0140
    D9) -- a malformed record propagates rather than being silently skipped."""
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
    """`run()`'s per-cycle metrics sink, at module level rather than inline so the ORDER inside it
    can be driven by a test: the ledger write comes first, and a test that cannot reach this closure
    cannot prove that a failing writer starves the heartbeat rather than being papered over by a
    gauge that keeps ticking."""

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
    # so a glob over one quote directory passes on a store missing exactly the legs a basket widening
    # added (spec 00094's two /BTC legs) and the first cycle dies on the absent file instead.
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
        # Startup seeding reads arbitrary on-disk journal artifacts (_seed_cycle_state ->
        # from_json/_sidecar_fields): an unreadable cycle-*.json (bad mode/ownership on the bind
        # mount) or a record with a tz-naive completed_at can raise OUTSIDE EngineJournalError
        # (PermissionError, TypeError from an aware/naive comparison) -- telemetry may never kill
        # the engine daemon (spec 00069 D5's isolation invariant; mirrors capture's
        # CaptureCollector registration guard below). Serve process metrics regardless.
        try:
            cycle_gauges = _CycleGauges(registry)
            completed_at, success = _seed_cycle_state(config.journal_dir)
            cycle_gauges.cycle_completed_at.set(completed_at.timestamp())
            if success is not None:  # None => empty/unreadable journal -- leave cycle_success absent
                cycle_gauges.seed_cycle_success(success)
        except Exception:
            logger.exception("engine metrics setup failed -- continuing with process metrics only")
        # Its own guard, isolated from the cycle seed above (00089 D6, cold-review MAJOR 1): without
        # this, a routine restart (always inside the inter-cycle gap, fleet-deploys.md) would leave
        # `zcrypto_venue_snapshot_timestamp_seconds` at its eager 0.0 default until the NEXT boundary
        # cycle, and `zcrypto-venue-snapshot-stale` would false-page "the writer has stopped" for up
        # to ~4h against an engine that merely restarted. An unreadable/absent venue-<HH>.json must
        # never prevent the engine from starting, same isolation invariant as the cycle seed.
        try:
            venue_gauges = _VenueGauges(registry)
            seed = _seed_venue_state(config.journal_dir)
            if seed is not None:  # None => no readable "ok" record yet -- leave every gauge eager
                venue_gauges.update(seed)
        except Exception:
            logger.exception("venue metrics setup failed -- continuing with process metrics only")
        start_metrics_server(port, registry)

    # Built regardless of telemetry: the ledger is a forensic artifact, not a metric. venue_reader
    # is passed explicitly (rather than relying on the class's default) so a test can substitute it
    # via `monkeypatch.setattr(command, "read_system_status", ...)` -- see exec_status below.
    gate = ExecutionGate(armed_in_config=config.exec_armed, state_dir=config.journal_dir.parent, venue_reader=read_system_status)
    exec_gauges = _ExecGauges(registry) if registry is not None else None

    exec_metrics = None
    if registry is not None:
        # Its own isolation guard, the `_VenueGauges` pattern: `_seed_exec_positions` reads arbitrary
        # on-disk journal artifacts and raises by contract on a malformed one, and telemetry may
        # never kill the engine daemon. The families are registered BEFORE the seed, so a failed
        # seed costs the starting values, never the series.
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

    # One evaluation at startup so no latch gauge sits at its seeded default. Inside the same
    # isolation the sink enjoys: telemetry must never be able to stop the engine from starting.
    if exec_gauges is not None:
        try:
            now = _utc_now()
            exec_gauges.update(gate.evaluate(now), evaluated_at=now)
        except Exception:  # noqa: BLE001 -- telemetry must never prevent the engine from starting
            logger.exception("startup execution-gate evaluation failed")

    # Lazy: cli.engine.node imports nautilus-trader (~1 s); `zcrypto --help` must never pay it.
    from cli.engine.node import build_shadow_node

    node = build_shadow_node(config)
    # This is the ONLY thing that arms faulthandler in the engine: nothing in the image or the
    # compose entrypoint sets PYTHONFAULTHANDLER, so without it a native abort -- a Rust panic in
    # the adapter, or the pyo3 assertion that fires when an unsendable object is touched off its own
    # thread -- kills the engine with exit 134 and NOTHING on stderr. Armed, it arrives with a stack.
    # tests/test_engine_node.py measures both, and it is why this runs before node.run().
    # `disable()` first: `enable()` installs the fatal-signal handlers only while faulthandler
    # considers itself disabled, so this pair is what makes THIS call install its own regardless of
    # what state the process was already in.
    # `file=2` rather than the default `sys.stderr` for two reasons. A fatal-signal dump is written
    # from a signal handler and must reach the process's real stderr -- fd 2, which here is docker's
    # log stream -- not whatever object happens to occupy `sys.stderr`. And the default form RAISES
    # when that object has no `fileno()`: since `disable()` has already run by then, the engine would
    # start with faulthandler switched OFF, strictly worse than never having armed it at all. An fd
    # needs no `fileno()`, so this form cannot fail that way and needs no exception handling.
    # Only the fatal five (SIGSEGV/SIGFPE/SIGABRT/SIGBUS/SIGILL) are handled; SIGTERM and SIGINT are
    # untouched, so `docker stop` and Ctrl-C still shut down cleanly.
    faulthandler.disable()
    faulthandler.enable(file=2)
    logger.info("shadow node starting (exec_enabled=%s, journal_dir=%s)", config.exec_enabled, config.journal_dir)
    # `node.run()` returns on a clean shutdown and RAISES on a start it cannot complete -- a client
    # that never connects, a startup reconciliation that never finishes. That raise is the loud
    # failure: the node has already disconnected its clients and stopped by the time it escapes,
    # `cli/__main__.py` logs it at ERROR before the process dies, and compose's `restart:
    # unless-stopped` is the recovery. Nothing here may catch it -- a swallowed start failure is a
    # live-looking node that will never trade, burning ratified gate days in silence.
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
        # A ran-and-failed instrument/identity/reconcile check means the tool itself can't be
        # trusted -- distinct from a short-window/canonical-absent "no verdict" refusal, which
        # exits 0 like any other successful emit.
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
    and ping an independent dead-man's-switch healthcheck. Exits 0 on a successful emit even when
    the gate has a mismatch or the journal is stale (those are findings, surfaced via the metrics
    and a /fail ping); non-zero only on an operational failure (unreadable journal, unwritable
    textfile)."""
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
    # Every not-clean outcome that breaks a gate day: replay mismatches, corrupt records, AND
    # failed-cycle sidecars (the normal stale_pair/refresh_deadline failure path -- these break
    # the streak but are tallied in sidecar_count, so omitting them would let the metric read 0
    # and the dead-man ping "clean" through a real gate failure).
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
        # The dead-man reflects the gate's CURRENT health across ALL break reasons (missing / late /
        # mismatch / validation / sidecar -- evaluate_gate resets streak on any of them in the most recent
        # COMPLETE day), not just the counted mismatch_total. streak>0 => the last complete day is clean
        # (progressing, at any streak length); streak==0 with no last_failure => no complete day is
        # evaluable yet (early phase -> liveness only, not a break); streak==0 WITH a last_failure => the
        # most recent complete day broke -> not clean. A recovered gate (broke earlier, clean since) has
        # streak>0 => clean, matching Grafana's windowed increase() and fixing the /fail-forever divergence.
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
    """Every journaled success record whose boundary falls in the inclusive [--since, --until] UTC
    day window.

    An unreadable record ABORTS rather than being skipped. Both measurements aggregate across the
    whole window, so a quietly dropped cycle biases every number below it with nothing on the page
    to say so -- and unlike a record that parses but fails to replay (which the reports name and
    count), one that will not parse cannot even be named per cycle downstream. --since/--until are
    the escape hatch for a journal carrying a known-bad day."""
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
    """`--minimums`, else the newest venue reference-data snapshot under the configured data dir.

    Newest BY FILENAME: the stamp is fixed-width UTC, so lexicographic order is chronological."""
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
    """The report payload as STRICTLY valid JSON: every non-finite float becomes `null`, and every
    mapping key becomes a string.

    Both are deliberate. A NaN is a legitimate value in these payloads -- a flat cycle's 0/0
    cancellation ratio, which must not masquerade as 1.0 -- and `json.dumps` writes it as the bare
    token `NaN`, which the JSON grammar has no room for and most non-Python parsers reject outright;
    emitting invalid JSON from a `--json` flag is worse than losing the NaN/None distinction, and
    the only other None either payload carries is an absent whole block (`reconciliation`, when no
    ledger export was given), so `null` on a number reads unambiguously as "not a number".
    The drift payload is also keyed by NAV, a float: the key spelling is written here and pinned by
    a test rather than left to `json.dumps`' internal coercion, and the numeric NAVs stay
    recoverable from the payload's own `navs` list and each row's `nav` field."""

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
    """Print the report, then exit non-zero if anything in it failed -- `n_failed` is the count.

    A failed replay means one of the two identity guards fired -- the recomputed stages no longer
    match the builder, or the rebuild no longer matches what the engine actually traded -- so the
    aggregates above it describe a smaller window than was asked for. A caller may count other
    failures of the same weight (the tracking report adds a ledger reconciliation that did not
    reconcile). Every one is named in the rendered text and in the payload; the exit code is what a
    script notices."""
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
    # float(None), and a non-dict `universe` entry reaches .get() on a str -- both are malformed
    # evidence, and this module answers those with a clean one-line exit, never a traceback.
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

    An unreadable or schema-invalid record ABORTS rather than being skipped, for a sharper reason
    than the cycle records': the fills it carries move `held` for every LATER cycle, so dropping one
    quietly overstates the drift of the whole remaining window."""
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
    """Validate `--gate-from` as a fixed-width ISO week label, or abort naming the form.

    Fixed width is load-bearing, not cosmetic: `rung_by_week` is built by comparing week labels as
    STRINGS, and `YYYY-Www` orders lexicographically exactly as it orders chronologically. A
    one-digit week would silently sort `2026-W9` after `2026-W10` and hand the wrong weeks a rung.
    """
    if raw is None:
        return None
    year, sep, week = raw.partition("-W")
    if not (len(year) == 4 and year.isdigit() and sep and len(week) == 2 and week.isdigit() and 1 <= int(week) <= 53):
        raise _abort(f"--gate-from {raw!r} is not an ISO week of the form YYYY-Www, e.g. 2026-W29")
    return raw


def _rung_by_week(stages: list[CycleStages], gate_from: str | None) -> dict[str, int]:
    """Every window week labelled rung 3 from `gate_from` onward, rung 2 before it.

    Absent the flag this is EMPTY, and `weekly_tracking` decides nothing -- the safe direction. The
    operator names the boundary; nothing here guesses it from the data, because the first week that
    counts is a decision about the deployment, not a property of the journal.
    """
    if gate_from is None:
        return {}
    labels = {f"{s.cycle_ts.isocalendar().year}-W{s.cycle_ts.isocalendar().week:02d}" for s in stages}
    return {label: (3 if label >= gate_from else 2) for label in labels}


def _simulated_fills(stages: list[CycleStages], floor_cycles: list[dict], minimums: dict[str, tuple[float, float]]) -> list[Fill]:
    """The drift floor's own placements, dressed as fills at the journaled close.

    The true-positive for the whole realized half. With zero journaled fills, every refusal in the
    tracking module is indistinguishable from a guard that always refuses, and a report that runs
    end to end proves only that it ran.

    Fees are MODELLED at the builder's own maker rate, so the fee-per-side this produces is the
    current one by construction -- real-shaped, never a recalibration input, which is why the report
    labels the run and says so beside the number.
    """
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
    """The realized blend, with the PROPOSAL withdrawn when the ledger did not reconcile.

    The measurement stays -- the maker/taker split and the realized rate are what the operator
    investigates with, and withholding them helps nobody. `proposed_fee_per_side` is different: it is
    the one number this whole comparison exists to feed into a config, and a `--json` consumer reads
    it straight out without ever looking at `n_failed`. A rate computed over a book the
    reconciliation has just declared incomplete must not be there to read.

    `basis` carries the reason, in the PAYLOAD rather than only in the rendered text -- the same
    reason `cost_blend` spells its three no-rate branches out at source instead of at whatever
    renders them."""
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
    """Why a week carries no verdict, spelled out.

    `weekly_tracking` marks a week that straddles the first fill only by ELIMINATION -- complete,
    on the deciding rung, and still not gate-eligible -- and an operator should not have to infer
    that from three flags. The branches are exhaustive because `gate_eligible` is exactly
    `complete and rung == 3 and not straddles`; each one below eliminates a conjunct, so what
    reaches the straddle branch can only be straddling."""
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
    # Both halves are inside one catch. `accumulation_report` DROPS a record whose replay raises and
    # counts it -- but a fill journaled under that dropped boundary then orphans, and
    # `realized_drift` refuses rather than silently overstating every later cycle. That refusal must
    # surface as this module's clean one-line exit, not as a traceback.
    try:
        floor = accumulation_payload(stages, floors, [nav_value])["by_nav"][nav_value]
        if simulated_fills:
            fills = _simulated_fills(stages, floor["cycles"], floors)
        else:
            fills, notes = extract_fills(_window_exec_records(journal_root, since, until))
        tracking = weekly_tracking(stages, fills, floors, nav_value, rung_by_week=_rung_by_week(stages, gate_week))
    except EngineError as exc:
        raise _abort(str(exc)) from exc

    # Absent an export there is nothing to reconcile against, and most runs will not have one. An
    # export whose HEADER cannot be mapped aborts, unlike an unmatched row: nothing was read, so
    # there is no reconciliation to report either way.
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
        # A failed reconciliation joins the exit-code count: the report is printed in full either
        # way, and the exit code is the only thing a script reading this notices. It stays OUT of
        # `failures`, which is the per-cycle replay list.
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

    Remote telemetry can only say THAT the engine is disarmed, never WHICH key is missing -- `zcrypto_exec_gate_level` carries a number, and `zcrypto_exec_armed` conflates its two arming keys into one gauge. This command reads the same gate and prints every reason and every input, for the deployment checklist to read on the host."""
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

    Without `--execute` it reads the account, prints the plan and stops. With `--execute` it needs the engine's kill file already in place, asks for a typed confirmation on the terminal, then cancels every resting order, closes every margin position reduce-only, and sells every non-EUR balance -- all at market, all journaled. Exit 0 the account reads flat, 1 refused before the venue was touched, 2 something is still open, 3 the venue could not be read before anything was sent."""
    # Imported HERE, not at module scope: `cli.engine.flatten` pulls nautilus (~1 s) and
    # `zcrypto --help` must never pay it -- the same reason `cli.engine.node` is lazy above.
    from cli.engine.flatten import run_flatten

    key = os.environ.get(_API_KEY_VAR)
    secret = os.environ.get(_API_SECRET_VAR)
    missing = [name for name, value in ((_API_KEY_VAR, key), (_API_SECRET_VAR, secret)) if not value]
    if missing:
        # The refusal names the VARIABLES and never their contents.
        raise _abort(f"the trade credentials are not in this environment: {', '.join(missing)}")

    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    client = KrakenSpotHttpClient(key, secret)
    # `raise typer.Exit(code=...)`, never `return`: a returned int is discarded and the process
    # exits 0, which turns every refusal and every not-flat account into a clean-looking run.
    # `echo` is handed the plain callable -- `run_flatten` wraps it in its own dead-stdout guard.
    # `asyncio.run` is where the loop the client needs comes from, and this is the only place it is
    # opened: every one of its seven methods raises `RuntimeError: no running event loop` outside
    # one, so called synchronously this command exits 3 on its very first read -- `--execute`
    # included. Same boundary placement as `cli/liquidations/command.py` and `cli/capture`.
    raise typer.Exit(code=asyncio.run(run_flatten(client, state_dir=state_dir, execute=execute, echo=typer.echo)))


def _newest_venue_record(journal_dir: Path) -> dict | None:
    """The newest `ok`, schema-2 `venue-<HH>.json` document in full, or None when the journal holds
    none. `_seed_exec_positions`' scan, kept whole rather than reduced: this caller needs both the
    instrument constraints and the balances. Same no-try/except contract -- a record that fails
    `validate_venue_record` raises rather than being skipped, because reading past a broken record
    would make every floor below fail open."""
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
    """One intent's checkable floors against one venue-snapshot instrument entry: the printable
    line, and every refusal it earned.

    A notional intent meets `costmin`, and ONLY when both are EUR: comparing a EUR notional against
    a `/BTC` leg's BTC-denominated floor passes everything silently (2e-05 is under any EUR figure),
    which is exactly the fail-open direction `size_probe_order`'s guard refuses at sizing time. A
    qty intent meets `ordermin` and the lot step instead -- it carries no price here, so no notional
    exists to check.
    """
    refusals: list[str] = []
    head = f"  [{index}] {intent.symbol} {intent.side} {intent.action} {intent.mode}"
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

    # The live balances spell the free-cash currency `EUR` (measured: `{'EUR': 99.84}`), so this
    # resolves on its SECOND arm against a real record. The `ZEUR` arm stays because the adapter's
    # other surface spells the euro `ZEUR` (the instrument quote currency); both absent reads 0.0,
    # which refuses any margin intent -- the executor's own reading.
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
