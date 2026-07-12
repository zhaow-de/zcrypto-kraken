"""The `zcrypto engine` Typer sub-app (spec 00041 SS the CLI): seed the live price store, run the
shadow node, run one cycle manually, replay journaled cycles through the builder, evaluate the
ratified gate, and export the gate as machine-readable metrics + a dead-man's-switch ping. Config
errors and EngineErrors surface as clean one-line exits, never tracebacks.

`cli.engine.node` (and with it nautilus-trader, ~1 s of import time) is imported lazily inside the
command bodies that need it -- `zcrypto --help` must never pay the nautilus import.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer

from cli.config import ConfigError, EngineConfig, load_config
from cli.engine.concordance import CycleOutcome, GateStatus, HashMismatchError, compare_targets, evaluate_gate, replay_cycle
from cli.engine.cycle import CycleResult, run_cycle
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.journal import SnapshotEntry, from_json
from cli.engine.store import seed_store
from cli.logging import get_logger
from cli.ohlc.dataset import read_parquet

logger = get_logger("engine.command")

CANONICAL_DIR = Path("data/ohlc-full")
_WATCHDOG_SLACK_SECS = 30.0
_urlopen = urllib.request.urlopen  # module-level so tests can stub the gate-export healthcheck ping

engine_app = typer.Typer(
    no_args_is_help=True,
    help="The Phase-6 shadow engine: store seeding, the node, manual cycles, journal replay, the gate report, and gate export.",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _abort(message: str) -> typer.Exit:
    """A clean one-line error (printed, no traceback) + exit code 1. Usage: `raise _abort(...)`."""
    typer.echo(f"ERROR: {message}", err=True)
    return typer.Exit(code=1)


def _load_engine_config() -> EngineConfig:
    try:
        return load_config().engine
    except ConfigError as exc:
        raise _abort(str(exc)) from exc


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


def _evaluate_journal(journal_root: Path) -> tuple[list[CycleOutcome], JournalCounts, datetime | None]:
    """Replay every journaled cycle-*.json (fast path) and classify every failed-cycle-*.json
    sidecar into CycleOutcome entries -- report's and gate-export's shared evidence-gathering pass.
    Absent boundaries are NOT fabricated -- evaluate_gate scores them missing. The third element is
    the newest cycle_ts seen across every outcome (None when the journal is empty)."""
    reader = _snapshot_reader(journal_root)

    entries: list[CycleOutcome] = []
    replayed_ok = mismatches = validation_failures = 0
    for boundary, record_path in _journal_artifacts(journal_root, "*", "cycle-*.json"):
        try:
            record = from_json(record_path.read_text())
        except EngineJournalError:
            validation_failures += 1
            entries.append(CycleOutcome(cycle_ts=boundary, completed_at=boundary, validation_failed=True))
            continue
        try:
            replayed = replay_cycle(record, reader, path="fast")
        except HashMismatchError:
            mismatches += 1
            entries.append(CycleOutcome(cycle_ts=record.cycle_ts, completed_at=record.completed_at, mismatch=True))
            continue
        except EngineJournalError:
            validation_failures += 1
            entries.append(CycleOutcome(cycle_ts=record.cycle_ts, completed_at=record.completed_at, validation_failed=True))
            continue
        verdict = compare_targets(record.final_targets, replayed)
        replayed_ok += verdict.passed
        mismatches += not verdict.passed
        entries.append(CycleOutcome(cycle_ts=record.cycle_ts, completed_at=record.completed_at, compare_passed=verdict.passed))
    sidecar_count = 0
    for boundary, sidecar_path in _journal_artifacts(journal_root, "*", "failed-cycle-*.json"):
        cycle_ts, completed_at, _ = _sidecar_fields(boundary, sidecar_path)
        entries.append(CycleOutcome(cycle_ts=cycle_ts, completed_at=completed_at, validation_failed=True))
        sidecar_count += 1

    newest_ts = max((entry.cycle_ts for entry in entries), default=None)
    return entries, JournalCounts(replayed_ok, mismatches, validation_failures, sidecar_count), newest_ts


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


def _write_prom_textfile(path: Path, *, status: GateStatus, lag_seconds: float | None, mismatch_total: int, now: datetime) -> None:
    """Atomically write the gate-export Prometheus textfile-collector metrics: write to a `.tmp`
    sibling then `os.replace` onto `path`, so a node-exporter scrape never observes a partial file
    and a write failure (e.g. an unwritable parent) leaves no partial artifact behind."""
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


def _start_watchdog(node) -> threading.Timer:
    """The supervision watchdog (spec 00042): a one-shot daemon timer firing timeout_connection +
    timeout_reconciliation + 30 s slack after the node starts (the real nautilus TradingNodeConfig
    attribute names; defaults 60 s + 30 s). A trader still not RUNNING then means the exec client
    never connected/reconciled (bad key, IP/family mismatch, venue outage): log CRITICAL and
    os._exit(1) -- the supervisor's restart (compose `restart: unless-stopped`) is the recovery, a
    visible crash loop instead of a silent zombie burning gate days. A RUNNING trader means a
    healthy start and the fired check does nothing; run() cancels the timer once node.run() returns."""
    node_config = node._config  # TradingNode keeps its config private; there is no public accessor
    delay = node_config.timeout_connection + node_config.timeout_reconciliation + _WATCHDOG_SLACK_SECS

    def check() -> None:
        try:
            if node.trader.is_running:
                return
            reason = "trader not running -- exec connect/reconcile presumed failed"
        except Exception as exc:  # cannot confirm health => assume wedged; never a silently disarmed watchdog
            reason = f"health check itself raised ({exc!r})"
        logger.critical(
            "engine run: %s %.0f s after node start; force-exiting for the supervisor restart",
            reason,
            delay,
        )
        os._exit(1)

    watchdog = threading.Timer(delay, check)
    watchdog.daemon = True
    watchdog.start()
    return watchdog


@engine_app.command()
def run() -> None:
    """Run the shadow TradingNode in the foreground (the soak's systemd user service runs this).
    Fails fast on a missing zcrypto.toml (when ZCRYPTO_REQUIRE_CONFIG is set) or a missing/empty
    store -- a node without them is always misconfigured, never a healthy default."""
    if os.environ.get("ZCRYPTO_REQUIRE_CONFIG") and not Path("zcrypto.toml").exists():
        raise _abort(
            "ZCRYPTO_REQUIRE_CONFIG is set but no zcrypto.toml exists in the working directory -- a default-config "
            "node (exec off, journal under the CWD) would run indistinguishably from a healthy one; fix the bind-mount"
        )
    config = _load_engine_config()
    if not any(config.store_dir.glob("*/EUR/*.parquet")):
        raise _abort(
            f"store_dir {config.store_dir} is missing or holds no */EUR/*.parquet series -- a node without a store is "
            "always misconfigured; fix the bind-mount or run `zcrypto engine seed`"
        )
    logger.info(
        "engine run: exec_enabled=%s, store_dir=%s, journal_dir=%s", config.exec_enabled, config.store_dir, config.journal_dir
    )
    # Lazy: cli.engine.node imports nautilus-trader (~1 s); `zcrypto --help` must never pay it.
    from cli.engine.node import build_shadow_node

    node = build_shadow_node(config)
    watchdog = _start_watchdog(node)
    logger.info("shadow node starting (exec_enabled=%s, journal_dir=%s)", config.exec_enabled, config.journal_dir)
    try:
        node.run()
    finally:
        watchdog.cancel()
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
    entries, counts, _ = _evaluate_journal(journal_root)

    try:
        status = evaluate_gate(entries, now=_utc_now())
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
        18000.0,
        "--lag-fail-seconds",
        help="Journal-pull staleness threshold in seconds beyond which the ping counts as unclean (default 18000, 5h).",
    ),
) -> None:
    """Emit the >= 14-clean-day gate as machine-readable Prometheus metrics (atomic textfile write)
    and ping an independent dead-man's-switch healthcheck. Exits 0 on a successful emit even when
    the gate has a mismatch or the journal is stale (those are findings, surfaced via the metrics
    and a /fail ping); non-zero only on an operational failure (unreadable journal, unwritable
    textfile)."""
    config = _load_engine_config()
    journal_root = journal_dir if journal_dir is not None else config.journal_dir
    entries, counts, newest_ts = _evaluate_journal(journal_root)

    now = _utc_now()
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

    try:
        _write_prom_textfile(textfile, status=status, lag_seconds=lag, mismatch_total=mismatch_total, now=now)
    except OSError as exc:
        raise _abort(f"could not write gate textfile {textfile}: {exc}") from exc

    if healthcheck_url:
        clean = mismatch_total == 0 and lag is not None and lag <= lag_fail_seconds
        _gate_ping(healthcheck_url, clean)
