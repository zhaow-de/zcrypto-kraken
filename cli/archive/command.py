"""The `zcrypto archive` Typer sub-app (spec 00048 Role A): pull a source tree via rsync-over-ssh
and hash-verify it against its manifest sidecars, so a transport failure and a hash mismatch are
distinguished exit codes -- neither is ever silently archived as good.

`reconcile` (spec 00050 Role C) extends the tier with the cross-host overlay: two raw mirrors in,
one healed hour out, minted only where the secondary demonstrably witnessed what the primary lost.
Wiring, exporter and exit codes only -- the rules live in `reconcile.py` / `settle.py` / `mint.py`."""

from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Optional

import polars as pl
import typer

from cli.archive.mint import already_minted, ledger_append, mint_hour
from cli.archive.pull import VerifyResult, pull_lag_seconds, verify_tree
from cli.archive.reconcile import Block, find_book_gaps, splice_book, union_trades
from cli.archive.settle import (
    fleet_dark_windows,
    hour_path,
    is_late,
    is_total_loss,
    newest_hour,
    scan_hours,
    settled_hours,
)
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA
from cli.logging import get_logger

logger = get_logger("archive.command")

archive_app = typer.Typer(
    no_args_is_help=True,
    help="The NAS pull/archive tier (Role A): rsync a source tree, then hash-verify it.",
)

KINDS = ("book", "trades")

# Every ledger state. `would_mint` is detect-only's ONLY output; `trade_deficit` records a deficit on
# the SECONDARY (a QA signal about the witness's own health, never a reason to mint); the two
# correlated-loss states are permanent loss and are never minted from.
_MINT_FAMILY = ("minted", "would_mint", "trade_deficit")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _run_rsync(source: str, dest: Path) -> int:
    ssh_key = os.environ.get("ARCHIVE_SSH_KEY")
    if not ssh_key:
        # No transport identity -> the pull can't even be attempted. Signal a transport-class
        # failure (pull() maps any non-zero to exit 2), never the bare KeyError that Click would
        # surface as exit 1 -- the contract reserves exit 1 for a hash mismatch.
        logger.error("archive pull: ARCHIVE_SSH_KEY is not set; cannot establish the ssh transport")
        return 2
    ssh_port = os.environ.get("ARCHIVE_SSH_PORT") or "10022"  # empty-string-safe (compose may pass "")
    # StrictHostKeyChecking=yes fails closed: the VPS key must already be in the pinned known_hosts
    # (accept-new would silently trust a new key). IdentitiesOnly=yes offers only the -i key, so a
    # stray agent/other key can't burn auth attempts and trip the rrsync forced command.
    # CheckHostIP=no: the hostname key is pinned; the extra IP-keyed check would try to append the
    # IP's key on every pull, which fails against the read-only /keys mount.
    ssh_opts = f"-i {ssh_key} -p {ssh_port} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o CheckHostIP=no"
    known_hosts = os.environ.get("ARCHIVE_SSH_KNOWN_HOSTS")
    if known_hosts:  # a pre-seeded, mounted known_hosts pins the VPS host key across restarts
        ssh_opts += f" -o UserKnownHostsFile={known_hosts}"
    ssh_command = f"ssh {ssh_opts}"
    # --chmod forces the archived tree to the mandated 0775 dirs / 0664 files (spec 00048): the NAS
    # share is plain POSIX (no ACL inheritance), so without this rsync -a would preserve the VPS's
    # 0644 source perms and the tree would not be group-writable. Applied every pull -> idempotent.
    argv = ["rsync", "-a", "--chmod=D0775,F0664", "-e", ssh_command, source, str(dest)]
    return subprocess.run(argv).returncode


@archive_app.command()
def pull(
    source: str = typer.Argument(..., help="rsync source spec, e.g. deploy@host:/var/lib/zcrypto-capture/segments/"),
    dest: Path = typer.Argument(..., help="Local destination directory to rsync into and verify."),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Hash-verify pulled segments against their .sha256 sidecars (default). Use --no-verify "
        "for archive-only sources like the engine journal, which has no sidecars.",
    ),
) -> None:
    """Pull `source` into `dest` via rsync-over-ssh, then hash-verify every segment against its
    manifest sidecar. Exits 2 on a transport failure (partial pull, never verified as authoritative),
    1 on a hash mismatch, 0 when every checked segment verifies."""
    returncode = _run_rsync(source, dest)
    if returncode != 0:
        logger.error("archive pull: rsync failed source=%s dest=%s returncode=%s", source, dest, returncode)
        raise typer.Exit(2)

    if not verify:
        logger.info("archive pull complete (no verify) source=%s dest=%s", source, dest)
        return

    result = verify_tree(dest, now=_utc_now())
    lag_s = pull_lag_seconds(result, now=_utc_now())
    logger.info(
        "pull complete source=%s checked=%d ok=%d failed=%d lag_s=%s",
        source,
        result.checked,
        result.ok,
        len(result.failed),
        lag_s,
    )
    if result.failed:
        for path in result.failed:
            logger.error("archive pull: verify failed path=%s", path)
        raise typer.Exit(1)


# --- reconcile (spec 00050 Role C) ----------------------------------------------------------------


def _load_ledger(root: Path) -> list[dict]:
    """The overlay's append-only audit ledger, and the ONLY state a one-shot reconciler carries.

    A skipped line under-counts a cumulative counter; Prometheus reads the drop as a counter reset and
    `increase()` then invents a permanent-loss page out of nothing. So a malformed line is loud.
    """
    path = root / "reconcile-ledger.jsonl"
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CaptureError(f"{path}:{number} is not valid JSON: {exc}") from exc
    return records


def _totals(records: list[dict]) -> dict[str, float]:
    """The exporter's cumulative counters, derived from the WHOLE ledger.

    `_total` is a Prometheus counter and the reconciler is a one-shot process with no memory: a run
    that exported only its own cycle's numbers would reset every counter to zero on the next quiet
    hour, and the "residual gap increased" rule — the permanent-loss page — would fire on the reset.
    The ledger is append-only and each (pair, kind, hour, state) is written at most once, so summing
    it is monotonic by construction.

    Trade deficits are counted from the FIRST decision per (pair, kind, hour) only: an hour ledgered
    `would_mint` during T0039's soak and then `minted` after the flip is one measurement, not two.
    """
    totals = dict.fromkeys(
        (
            "spliced_hours",
            "union_hours",
            "healed_seconds",
            "residual_seconds",
            "deficit_primary",
            "deficit_secondary",
            "dedup_rows",
        ),
        0.0,
    )
    measured: set[tuple] = set()
    for record in records:
        state = record.get("state")
        totals["residual_seconds"] += float(record.get("residual_seconds") or 0.0)
        if state == "minted":
            totals["healed_seconds"] += float(record.get("healed_seconds") or 0.0)
            totals["spliced_hours" if record.get("kind") == "book" else "union_hours"] += 1
        if state in _MINT_FAMILY:
            key = (record.get("pair"), record.get("kind"), record.get("hour"))
            if key in measured:
                continue
            measured.add(key)
            totals["deficit_primary"] += float(record.get("trades_added") or 0)
            totals["deficit_secondary"] += float(record.get("trades_secondary_deficit") or 0)
            totals["dedup_rows"] += float(record.get("trades_deduped") or 0)
    return totals


def _lag(scans: dict[str, dict[str, set[datetime]]], *, now: datetime) -> float:
    """Age of the mirror's newest final -- a dead source detected via DATAFLOW, independently of its
    dead-man.

    `pull_lag_seconds` is the one definition of that arithmetic, so it is reused; the `VerifyResult`
    it consumes is built from the filename scan we already have rather than from `verify_tree`, whose
    full sha256 sweep of an indefinitely-retained mirror would be a third and fourth hash of the whole
    archive per cycle -- the pull step already does the two the loop budget accounts for.
    """
    result = VerifyResult(checked=0, ok=0, failed=(), newest_ts=newest_hour(*scans.values()))
    lag = pull_lag_seconds(result, now=now)
    # No final at all: the mirror is not merely stale, it is empty. +Inf trips the source-lag rule;
    # omitting the series would leave it with no data to evaluate and nothing would fire.
    return math.inf if lag is None else lag


def _write_textfile(path: Path, *, now: datetime, totals: dict[str, float], lags: dict[str, float]) -> None:
    """Publish `reconcile.prom` atomically: a textfile is scraped in place, so a half-written one is
    scraped as garbage. Temp in the SAME directory (so the rename is a same-filesystem `os.replace`),
    then rename over the destination -- a scrape sees the old file or the new one, never half of one.
    """
    lines: list[str] = []

    def _emit(name: str, kind: str, help_: str, samples: list[tuple[str, float]]) -> None:
        lines.append(f"# HELP zcrypto_reconcile_{name} {help_}")
        lines.append(f"# TYPE zcrypto_reconcile_{name} {kind}")
        lines.extend(f"zcrypto_reconcile_{name}{labels} {value}" for labels, value in samples)

    _emit(
        "last_success_timestamp_seconds",
        "gauge",
        "Unix time of the last cycle that completed without an integrity failure.",
        [("", now.timestamp())],
    )
    _emit(
        "source_lag_seconds",
        "gauge",
        "Age of each mirror's newest committed final.",
        [(f'{{source="{source}"}}', value) for source, value in lags.items()],
    )
    _emit("spliced_hours_total", "counter", "Book hours minted from a primary+secondary splice.", [("", totals["spliced_hours"])])
    _emit("union_hours_total", "counter", "Trade hours minted from a cross-host trade-id union.", [("", totals["union_hours"])])
    _emit(
        "healed_gap_seconds_total",
        "counter",
        "Primary book silence covered by a secondary block.",
        [("", totals["healed_seconds"])],
    )
    _emit(
        "residual_gap_seconds_total",
        "counter",
        "Silence NO mirror covered: permanent loss (both_streams_silent / total_loss).",
        [("", totals["residual_seconds"])],
    )
    _emit(
        "trade_deficit_rows_total",
        "counter",
        "Trade rows a host was missing that the other one had.",
        [
            ('{host="primary"}', totals["deficit_primary"]),
            ('{host="secondary"}', totals["deficit_secondary"]),
        ],
    )
    _emit("trade_dedup_rows_total", "counter", "Duplicate trade_id rows dropped while unioning.", [("", totals["dedup_rows"])])

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)


@archive_app.command()
def reconcile(
    primary_root: Path = typer.Argument(..., help="The primary mirror (raw, canonical-by-default)."),
    secondary_root: Path = typer.Argument(..., help="The secondary mirror (raw)."),
    reconciled_root: Path = typer.Argument(..., help="The overlay: only healed hours are minted here."),
    window_hours: int = typer.Option(48, "--window-hours", help="Trailing settled hours to re-scan each cycle."),
    min_gap_seconds: float = typer.Option(
        30.0,
        "--min-gap-seconds",
        help="Primary book silence longer than this, with the secondary alive inside it, is a gap. "
        "The default 30 s is 2x the measured 14.78 s maximum natural quiescence and is NOT yet "
        "validated cross-host (T0039) -- which is why --detect-only is the default.",
    ),
    textfile: Optional[Path] = typer.Option(None, "--textfile", help="Prometheus textfile to publish."),
    mint: bool = typer.Option(
        False,
        "--mint/--detect-only",
        help="DEFAULT is --detect-only: ledger what WOULD be spliced and mint nothing. Do not flip to "
        "--mint until T0039's soak has pinned --min-gap-seconds from real cross-host data.",
    ),
) -> None:
    """Reconcile the two raw mirrors into the healed overlay.

    Detect-only by default: it ledgers every `would_mint` and writes no parquet. `--min-gap-seconds`
    is unvalidated cross-host (T0039) -- the measured single-host MAXIMUM natural quiescence is
    14.78 s and one secondary update row is enough to witness a gap, so a per-connection coalescing
    artifact could plausibly trip a phantom splice: an unaudited data swap into an archive that cannot
    be backfilled. Minting is unlocked only once the soak has pinned the threshold from real data.

    The two correlated-loss detectors run regardless of the flag and are never minted from: when BOTH
    streams are dark there is no witness to heal with, and no flag can conjure one.

    Exit 2 when a mirror is unreadable (transport), 1 on an integrity failure (an unreadable segment,
    a non-monotonic stream, a corrupt ledger), 0 otherwise. Residual gaps are a finding, not a failure:
    they exit 0 and page through `residual_gap_seconds_total`.
    """
    now = _utc_now()
    for label, root in (("primary", primary_root), ("secondary", secondary_root)):
        if not root.is_dir():
            # Treating an absent mirror as "no witness available" would let the reconciler report
            # all-clean forever while the redundancy simply is not there.
            logger.error("archive reconcile: the %s mirror is missing path=%s", label, root)
            raise typer.Exit(2)

    try:
        records = _load_ledger(reconciled_root)
    except CaptureError as exc:
        logger.error("archive reconcile: %s", exc)
        raise typer.Exit(1) from exc

    scans = {
        "primary": {kind: scan_hours(primary_root, kind) for kind in KINDS},
        "secondary": {kind: scan_hours(secondary_root, kind) for kind in KINDS},
    }
    available = {
        (pair, kind): scans["primary"][kind].get(pair, set()) | scans["secondary"][kind].get(pair, set())
        for kind in KINDS
        for pair in set(scans["primary"][kind]) | set(scans["secondary"][kind])
    }
    spans = {key: (min(hours), max(hours)) if hours else None for key, hours in available.items()}
    book_pairs = sorted(pair for pair, kind in available if kind == "book")
    trade_pairs = sorted(pair for pair, kind in available if kind == "trades")

    seen = {(r.get("pair"), r.get("kind"), r.get("hour"), r.get("state")) for r in records}
    failures = 0

    def _ledger(**record) -> None:
        key = (record["pair"], record["kind"], record["hour"], record["state"])
        if key in seen:  # already decided in an earlier cycle -- re-appending would double every total
            return
        seen.add(key)
        record.setdefault("at", now.isoformat())
        records.append(record)
        ledger_append(reconciled_root, record)

    def _read(root: Path, pair: str, kind: str, hour: datetime, columns: list[str] | None = None) -> pl.DataFrame:
        return pl.read_parquet(hour_path(root, pair, kind, hour), columns=columns)

    def _decided(pair: str, kind: str, hour: datetime, state: str) -> bool:
        return (pair, kind, hour.isoformat(), state) in seen

    def _fail(pair: str, kind: str, hour: datetime, reason: str) -> None:
        nonlocal failures
        failures += 1
        logger.error("archive reconcile: %s pair=%s kind=%s hour=%s", reason, pair, kind, hour.isoformat())
        _ledger(state="failed", pair=pair, kind=kind, hour=hour.isoformat(), reason=reason, residual_seconds=0.0)

    for hour in settled_hours(now=now, window_hours=window_hours):
        hour_end = hour + timedelta(hours=1)
        late = is_late(hour, now=now)

        # --- total_loss: unconditional, no witness needed --------------------------------------
        for (pair, kind), hours in sorted(available.items()):
            if is_total_loss(hour, available=hours, span=spans[(pair, kind)]):
                logger.error("archive reconcile: total_loss pair=%s kind=%s hour=%s", pair, kind, hour.isoformat())
                _ledger(
                    state="total_loss",
                    pair=pair,
                    kind=kind,
                    hour=hour.isoformat(),
                    residual_seconds=3600.0,  # the whole hour, on both mirrors, gone
                )

        # --- load this hour's book streams once: gap detection AND the dual-silence timeline ----
        books: dict[str, dict[str, pl.DataFrame | None]] = {}
        stamps: list[datetime] = []
        broken = False
        for pair in book_pairs:
            frames: dict[str, pl.DataFrame | None] = {}
            for source, root in (("primary", primary_root), ("secondary", secondary_root)):
                if hour not in scans[source]["book"].get(pair, set()):
                    frames[source] = None
                    continue
                try:
                    # `ts` + `type` is all detection needs; the full frame is read only to splice.
                    frames[source] = _read(root, pair, "book", hour, ["ts", "type"])
                except Exception as exc:  # noqa: BLE001 -- any unreadable segment is an integrity fact
                    _fail(pair, "book", hour, f"unreadable {source} book segment: {exc}")
                    frames[source] = None
                    broken = True
                    continue
                stamps.extend(frames[source]["ts"].to_list())
            books[pair] = frames

        # --- both_streams_silent: unconditional, no witness needed ------------------------------
        # Skipped when a segment failed to read (an honest timeline cannot be built from it) and when
        # no book file exists at all (the hour is total_loss territory -- booking it here as well
        # would double-count the same seconds into a counter that can never be walked back).
        present = [pair for pair, frames in books.items() if any(f is not None for f in frames.values())]
        if present and not broken:
            windows = fleet_dark_windows(stamps, hour_start=hour, hour_end=hour_end, min_seconds=min_gap_seconds)
            if windows:
                residual = sum(w.seconds for w in windows) * len(present)  # seconds x dark book streams
                logger.error(
                    "archive reconcile: both_streams_silent hour=%s windows=%d residual_s=%.1f",
                    hour.isoformat(),
                    len(windows),
                    residual,
                )
                _ledger(
                    state="both_streams_silent",
                    pair="*",  # fleet-wide by construction: it is the intersection across every pair
                    kind="book",
                    hour=hour.isoformat(),
                    pairs=present,
                    windows=[{"start": w.start, "end": w.end, "seconds": w.seconds} for w in windows],
                    residual_seconds=residual,
                )

        # --- the witness-based heal: books ------------------------------------------------------
        for pair in book_pairs:
            frames = books[pair]
            secondary = frames["secondary"]
            if secondary is None or _decided(pair, "book", hour, "minted"):
                continue  # no witness, or already healed
            if already_minted(reconciled_root, pair, "book", hour):
                continue
            if not mint and _decided(pair, "book", hour, "would_mint"):
                continue  # detect-only: decided in an earlier cycle, do not re-ledger
            if frames["primary"] is None:
                if hour in scans["primary"]["book"].get(pair, set()) or not late:
                    continue  # unreadable (already failed), or the primary's file may still arrive
                primary = secondary.clear()  # the crash-shaped hour: heal the whole of it
            else:
                primary = frames["primary"]

            try:
                gaps = find_book_gaps(
                    primary,
                    secondary,
                    min_gap_seconds=min_gap_seconds,
                    hour_start=hour,
                    hour_end=hour_end,
                )
            except CaptureError as exc:
                _fail(pair, "book", hour, str(exc))
                continue
            if not gaps:
                continue

            healed = sum(gap.seconds for gap in gaps)
            entry = {
                "pair": pair,
                "kind": "book",
                "hour": hour.isoformat(),
                "healed_seconds": healed,
                "gaps_healed": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in gaps],
                "residual_seconds": 0.0,
            }
            if not mint:
                logger.info("archive reconcile: would_mint pair=%s kind=book hour=%s healed_s=%.1f", pair, hour.isoformat(), healed)
                _ledger(state="would_mint", **entry)
                continue

            try:
                full_secondary = _read(secondary_root, pair, "book", hour)
                full_primary = (
                    _read(primary_root, pair, "book", hour) if frames["primary"] is not None else pl.DataFrame(schema=BOOK_SCHEMA)
                )
                blocks = splice_book(full_primary, full_secondary, gaps)
                mint_hour(
                    reconciled_root,
                    pair,
                    "book",
                    hour,
                    blocks,
                    gaps_healed=gaps,
                    residual_gaps=[],
                    schema=BOOK_SCHEMA,
                    tool_version=version("zcrypto"),
                )
            except (CaptureError, OSError) as exc:
                _fail(pair, "book", hour, f"mint failed: {exc}")
                continue
            logger.info("archive reconcile: minted pair=%s kind=book hour=%s healed_s=%.1f", pair, hour.isoformat(), healed)
            _ledger(state="minted", **entry)

        # --- the witness-based heal: trades -----------------------------------------------------
        for pair in trade_pairs:
            if _decided(pair, "trades", hour, "minted") or already_minted(reconciled_root, pair, "trades", hour):
                continue
            if hour not in scans["secondary"]["trades"].get(pair, set()):
                continue  # nothing to union from
            primary_present = hour in scans["primary"]["trades"].get(pair, set())
            if not primary_present and not late:
                continue  # the primary's file may still arrive; a full-secondary mint would shadow it
            if not mint and (_decided(pair, "trades", hour, "would_mint") or _decided(pair, "trades", hour, "trade_deficit")):
                continue

            try:
                secondary_trades = _read(secondary_root, pair, "trades", hour)
                primary_trades = _read(primary_root, pair, "trades", hour) if primary_present else pl.DataFrame(schema=TRADE_SCHEMA)
                union = union_trades(primary_trades, secondary_trades)
            except Exception as exc:  # noqa: BLE001 -- any unreadable segment is an integrity fact
                _fail(pair, "trades", hour, f"unreadable trades segment: {exc}")
                continue

            if union.added_from_secondary == 0:
                if union.secondary_deficit or union.deduped_rows:
                    # The secondary lacks rows the primary has: evidence about the WITNESS's own
                    # health. A QA signal, never a mint -- this reconciler only heals the primary.
                    _ledger(
                        state="trade_deficit",
                        pair=pair,
                        kind="trades",
                        hour=hour.isoformat(),
                        trades_added=0,
                        trades_secondary_deficit=union.secondary_deficit,
                        trades_deduped=union.deduped_rows,
                        residual_seconds=0.0,
                    )
                continue

            entry = {
                "pair": pair,
                "kind": "trades",
                "hour": hour.isoformat(),
                "healed_seconds": 0.0,  # a trade union heals rows, not silence
                "trades_added": union.added_from_secondary,
                "trades_secondary_deficit": union.secondary_deficit,
                "trades_deduped": union.deduped_rows,
                "residual_seconds": 0.0,
            }
            if not mint:
                _ledger(state="would_mint", **entry)
                continue

            try:
                # One block, not a splice: `trade_id` is globally unique and identical across hosts,
                # so trades are the one stream the reconciler may union ROW-level. "union" is the
                # honest provenance source -- the rows come from both mirrors, interleaved by id.
                frame = union.frame
                block = [Block("union", frame, frame["ts"].min(), frame["ts"].max())]
                mint_hour(
                    reconciled_root,
                    pair,
                    "trades",
                    hour,
                    block,
                    gaps_healed=[],
                    residual_gaps=[],
                    schema=TRADE_SCHEMA,
                    tool_version=version("zcrypto"),
                )
            except (CaptureError, OSError) as exc:
                _fail(pair, "trades", hour, f"mint failed: {exc}")
                continue
            logger.info(
                "archive reconcile: minted pair=%s kind=trades hour=%s added=%d deduped=%d",
                pair,
                hour.isoformat(),
                union.added_from_secondary,
                union.deduped_rows,
            )
            _ledger(state="minted", **entry)

    totals = _totals(records)
    logger.info(
        "reconcile complete mode=%s window_h=%d spliced=%d union=%d healed_s=%.1f residual_s=%.1f failures=%d",
        "mint" if mint else "detect-only",
        window_hours,
        int(totals["spliced_hours"]),
        int(totals["union_hours"]),
        totals["healed_seconds"],
        totals["residual_seconds"],
        failures,
    )
    if failures:
        # No textfile on a failed cycle: `last_success_timestamp` freezes and the exporter-stale rule
        # pages. Publishing fresh-looking numbers from a cycle that could not read its inputs would
        # be the one thing worse than not publishing.
        raise typer.Exit(1)

    if textfile is not None:
        lags = {source: _lag(scan, now=now) for source, scan in scans.items()}
        try:
            _write_textfile(textfile, now=now, totals=totals, lags=lags)
        except OSError as exc:
            logger.error("archive reconcile: could not publish the textfile path=%s: %s", textfile, exc)
            raise typer.Exit(1) from exc
