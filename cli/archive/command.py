"""The `zcrypto archive` Typer sub-app (spec 00048 Role A): pull a source tree via rsync-over-ssh
and hash-verify it against its manifest sidecars, so a transport failure and a hash mismatch are
distinguished exit codes -- neither is ever silently archived as good.

`reconcile` (spec 00050 Role C) extends the tier with the cross-host overlay: two raw mirrors in,
one healed hour out, minted only where the secondary demonstrably witnessed what the primary lost.
Wiring, exporter and exit codes only -- the rules live in `reconcile.py` / `settle.py` / `mint.py`.

`verify-replay` (spec 00051 OPS-3) replays the canonical book stream (reconciled-first) through
`OrderBook` and proves it coherent per hour -- rules and scope guard in `replay.py`.

`backfill-trades` (spec 00053 Task 5) heals the canonical TRADE stream: detects trade_id gaps against
the archive, fetches the missing ids from Kraken's public REST, and mints healed hours into the
reconciled overlay -- rules live in `cli/trades/backfill.py`."""

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

from cli.archive import replay as replay_mod
from cli.archive.mint import already_minted, ledger_append, mint_hour
from cli.archive.pull import VerifyResult, prune_stale_parts, pull_lag_seconds, verify_tree
from cli.archive.reconcile import (
    Block,
    Gap,
    find_book_gaps,
    find_unwitnessed_gaps,
    measure_residual,
    overlap_seconds,
    splice_book,
    union_trades,
)
from cli.archive.settle import (
    containing_dark_window,
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
from cli.trades.backfill import backfill

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
    # T0038: drain the parts of every VERIFIED hour on the NAS. Safe by construction (only where the
    # final verified against its manifest), independent of any failed hours, and it clears the backlog
    # on the first cycle. Not gated on `result.failed`: each verified final independently justifies
    # pruning its own parts, and a single bad hour should not keep a majority-stale mirror stale.
    pruned_hours, pruned_parts = prune_stale_parts(result.verified)
    logger.info(
        "pull complete source=%s checked=%d ok=%d failed=%d lag_s=%s pruned_parts=%d pruned_hours=%d",
        source,
        result.checked,
        result.ok,
        len(result.failed),
        lag_s,
        pruned_parts,
        pruned_hours,
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


def _as_dt(value: datetime | str) -> datetime:
    """A ledger record appended THIS cycle still holds datetimes; one read back from the JSONL holds
    the ISO strings `json.dumps(default=str)` wrote. Both reach `_totals` and the lookups below."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _spans(items: list[dict]) -> list[tuple[datetime, datetime]]:
    return [(_as_dt(item["start"]), _as_dt(item["end"])) for item in items]


def _booked_dark(records: list[dict], pair: str, hour: datetime) -> list[tuple[datetime, datetime]]:
    """The fleet-dark windows the ledger has ALREADY booked as loss for `pair`'s stream in `hour`.

    Read from the ledger, never recomputed. `both_streams_silent` is decided ONCE, for the pairs
    present on that cycle, and a later cycle's inputs differ: a mirror file arriving late adds a pair
    the fleet record booked no share for, so subtracting a fresh recomputation would delete that
    pair's loss from a total nobody ever added it to. Both directions of that error were measured.
    """
    stamp = hour.isoformat()
    windows: list[tuple[datetime, datetime]] = []
    for record in records:
        if record.get("state") != "both_streams_silent" or record.get("hour") != stamp:
            continue
        if pair not in (record.get("pairs") or []):
            continue
        # `stream_windows` is what was actually booked for this stream; `windows` is the
        # intersection. Records written before the two were split carry only the latter, and there
        # it WAS what got booked -- so reading either keeps history correctly subtracted.
        per_stream = (record.get("stream_windows") or {}).get(pair)
        windows += _spans(per_stream if per_stream is not None else (record.get("windows") or []))
    return windows


def _booked_residual(records: list[dict], pair: str, hour: datetime) -> list[tuple[datetime, datetime]]:
    """The residual windows `pair`'s own book record already booked as loss for `hour`.

    The mirror image of `_booked_dark`, and the reason the attribution is order-independent: an
    unreadable segment suppresses the fleet detector for a cycle, so a pair that mints in the
    meantime books its residual first and the fleet record must then book only the rest. Records
    written before residual was measured carry no `residual_gaps` and booked nothing, so they
    correctly subtract nothing.
    """
    stamp = hour.isoformat()
    for record in records:
        if record.get("kind") != "book" or record.get("pair") != pair or record.get("hour") != stamp:
            continue
        if record.get("state") in ("minted", "would_mint"):
            return _spans(record.get("residual_gaps") or [])
    return []


def _book_entry(
    pair: str, hour: datetime, gaps: list[Gap], residual_gaps: list[Gap], dark: list[tuple[datetime, datetime]]
) -> dict:
    """One healed book hour's ledger record, with every second attributed EXACTLY once.

    The three quantities are deliberately separate because they answer three different questions, and
    collapsing them is what made this record lie about the 2026-07-27 blackout:

      * `claimed_seconds` — the primary silence the gap was ADMITTED on. This is what
        `healed_seconds` used to be, and the gap-RATE signal still wants it: that rate exists to
        reveal a degrading primary, and a correlated outage (not the primary degrading) must not make
        it quieter than an ordinary one.
      * `healed_seconds` — what the splice actually INSERTED. `secondary_covers` admits a window on
        one update row anywhere inside it; one row admits a window, it does not fill one. Measured
        against the minted frame, the real event read 82.955463 s against a claimed 2,311.536587 s.
      * `residual_seconds` — what the splice did NOT fill, minus whatever the fleet-wide
        `both_streams_silent` record already booked for the same seconds. Without that subtraction,
        correcting the heal over-count would manufacture a loss over-count in the same cycle.

    `residual_gaps` stays the FULL measured set: it is this file's provenance, not a counter, and the
    sidecar must describe the hour rather than the bookkeeping.
    """
    claimed = sum(gap.seconds for gap in gaps)
    unfilled = sum(gap.seconds for gap in residual_gaps)
    # Both subtractions are bounded by construction -- residual windows are disjoint sub-windows of
    # the gaps, and each merged dark window is intersected against them -- so neither can go negative.
    already_booked = overlap_seconds([(g.start, g.end) for g in residual_gaps], dark)
    return {
        "pair": pair,
        "kind": "book",
        "hour": hour.isoformat(),
        "claimed_seconds": claimed,
        "healed_seconds": claimed - unfilled,
        "gaps_healed": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in gaps],
        "residual_gaps": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in residual_gaps],
        "residual_seconds": unfilled - already_booked,
    }


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
            "healable_seconds",
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
        if state not in _MINT_FAMILY:
            # both_streams_silent / total_loss / failed / unwitnessed are decided once per
            # (pair, hour) and never re-ledgered, so they add unconditionally. `unwitnessed`
            # carries no `residual_seconds` key at all, so it contributes nothing here by
            # construction rather than by being zero -- see T0108 for what that leaves unseen.
            totals["residual_seconds"] += float(record.get("residual_seconds") or 0.0)
        if state == "minted":
            totals["healed_seconds"] += float(record.get("healed_seconds") or 0.0)
            totals["spliced_hours" if record.get("kind") == "book" else "union_hours"] += 1
        if state in _MINT_FAMILY:
            key = (record.get("pair"), record.get("kind"), record.get("hour"))
            if key in measured:
                continue
            measured.add(key)
            # Inside the dedup, for the same reason `healable` is: an hour ledgered `would_mint` in
            # detect-only and `minted` after the flip carries the SAME measured residual on both
            # records. Adding both books permanent loss twice, and the second step reads to the
            # CRITICAL page as a fresh permanent-loss event -- an increase, so the reset guard on that
            # rule does not suppress it. (Harmless before residual was measured: it was a literal 0.0.)
            totals["residual_seconds"] += float(record.get("residual_seconds") or 0.0)
            # `healable` is the gap rate, and it must exist in DETECT-ONLY -- minting stays off for the
            # whole T0039 soak, so `healed` (minted only) is pinned at 0 exactly when the signal is most
            # needed. A degrading primary whose every gap the secondary quietly heals trips neither the
            # residual-gap rule nor either dead-man; the rate is the only thing that reveals it. Counted
            # here, inside the per-(pair,kind,hour) dedup, because the flip to --mint re-ledgers the same
            # hour as `minted`: one gap, not two.
            # `claimed_seconds` or `healed_seconds`: records written before the two were split
            # carry only the latter, and there it WAS the claimed window width.
            totals["healable_seconds"] += float(record.get("claimed_seconds") or record.get("healed_seconds") or 0.0)
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

    def _fmt(value: float) -> str:
        # Prometheus's text format spells the non-finite values `+Inf` / `-Inf` / `NaN`; Python's f-string
        # renders them `inf` / `-inf` / `nan`, which node-exporter's textfile collector rejects -- and it
        # rejects the WHOLE file on one bad line, dropping every zcrypto_reconcile_* series for that
        # scrape. A +Inf source_lag (an empty mirror) is a real, expected value the source-lag rule is
        # meant to fire on, so it must be emitted parseably rather than poisoning the file.
        if math.isinf(value):
            return "+Inf" if value > 0 else "-Inf"
        if math.isnan(value):
            return "NaN"
        return str(value)

    def _emit(name: str, kind: str, help_: str, samples: list[tuple[str, float]]) -> None:
        lines.append(f"# HELP zcrypto_reconcile_{name} {help_}")
        lines.append(f"# TYPE zcrypto_reconcile_{name} {kind}")
        lines.extend(f"zcrypto_reconcile_{name}{labels} {_fmt(value)}" for labels, value in samples)

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
        "Primary book silence a secondary block actually FILLED, measured against the minted hour rather "
        "than the window the gap was admitted on -- one secondary update admits a window, it does not fill "
        "one.",
        [("", totals["healed_seconds"])],
    )
    _emit(
        "healable_gap_seconds_total",
        "counter",
        "Primary book silence the secondary WITNESSED and could cover, whether or not it was minted. "
        "Unlike healed_gap_seconds_total this is non-zero in detect-only, so the gap RATE -- the only "
        # T0039: the soak this counter was added for.
        "signal that reveals a degrading primary whose gaps are always healed -- is visible during the "
        "soak.",
        [("", totals["healable_seconds"])],
    )
    _emit(
        "residual_gap_seconds_total",
        "counter",
        "Silence NO mirror covered: permanent loss (both_streams_silent / total_loss, plus whatever a "
        "healed hour's splice left unfilled and no fleet-wide record already booked). A FLOOR, not the "
        "whole: the `unwitnessed` state -- one pair silent on both mirrors, indistinguishable from a thin "
        "market -- is deliberately not counted and reaches no counter at all, living in the ledger and the "
        "WARNING log only.",
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
        "The default 30 s is validated from a 66h/217-window two-host soak: 2.48x the worst "
        "coalescing artifact, 2.8x below the smallest real outage on record.",
    ),
    textfile: Optional[Path] = typer.Option(None, "--textfile", help="Prometheus textfile to publish."),
    mint: bool = typer.Option(
        False,
        "--mint/--detect-only",
        help="DEFAULT is --detect-only: ledger what WOULD be spliced and mint nothing. The deployed "
        "reconciler runs --mint; ad-hoc runs stay detect-only.",
    ),
) -> None:
    """Reconcile the two raw mirrors into the healed overlay.

    Detect-only by default: it ledgers every `would_mint` and writes no parquet. `--min-gap-seconds`
    30 s is validated cross-host: 2.48x the worst per-connection coalescing artifact in a 66 h /
    217-window two-host soak (12.08 s), 2.03x the single-host maximum natural quiescence
    (14.78 s), and 2.8x below the smallest real outage on record -- and
    a live 25-minute drill outage healed exactly, CRC-clean, while a healthy hour minted nothing.
    The deployed reconciler runs `--mint`; ad-hoc runs stay detect-only.

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

    # A permanent-loss finding is announced ONCE, on the cycle that decides it -- both branches below
    # are guarded by `_decided`, matching `_ledger`'s own dedupe ("already decided in an earlier cycle").
    # These hours are, by definition, unfixable: they stay in the trailing window for 48 h, so re-logging
    # them each cycle would re-fire the ERROR-log alert every hour for two days about a gap the operator
    # already knows about and can do nothing about. A page that repeats until it is ignored is worse than
    # no page. The ledger remains the durable record; the log is the announcement.
    for hour in settled_hours(now=now, window_hours=window_hours):
        hour_end = hour + timedelta(hours=1)
        late = is_late(hour, now=now)

        # --- total_loss ------------------------------------------------------------------------
        # `trades` is judged against its pair's BOOK hours. Book updates are continuous, trades are
        # prints: an hour with no trades is ordinary for a quiet pair, and the book final for that same
        # hour is the proof the stream was connected throughout. Without this witness the reconciler
        # calls "nobody traded LINK for an hour" a permanent, unrecoverable loss -- ledgered, logged at
        # ERROR (so it pages), and booked into a monotonic counter that can never be walked back. The
        # book has no sibling to witness it and is judged on bracketing alone, as before.
        for (pair, kind), hours in sorted(available.items()):
            witness = available.get((pair, "book")) if kind == "trades" else None
            if is_total_loss(hour, available=hours, span=spans[(pair, kind)], alive_witness=witness) and not _decided(
                pair, kind, hour, "total_loss"
            ):
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
        pair_stamps: dict[str, list[datetime]] = {}  # per stream, BOTH mirrors -- see `containing_dark_window`
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
                pair_stamps.setdefault(pair, []).extend(frames[source]["ts"].to_list())
            books[pair] = frames

        # --- both_streams_silent: unconditional, no witness needed ------------------------------
        # Skipped when a segment failed to read (an honest timeline cannot be built from it) and when
        # no book file exists at all (the hour is total_loss territory -- booking it here as well
        # would double-count the same seconds into a counter that can never be walked back).
        present = [pair for pair, frames in books.items() if any(f is not None for f in frames.values())]
        if present and not broken:
            windows = fleet_dark_windows(stamps, hour_start=hour, hour_end=hour_end, min_seconds=min_gap_seconds)
            if windows and not _decided("*", "book", hour, "both_streams_silent"):
                # Book each stream its OWN silence window around each intersection, not the
                # intersection itself: that window is bounded by whichever stream returned first, so
                # `intersection x count` charges every stream with the binding one's loss. Measured
                # 34.243169 s (1.27%) invisible on 2026-07-13 -- in the reassuring direction.
                #
                # Deduplicated per stream: two intersections exist only because some OTHER stream
                # ticked between them, and a stream that did not tick has ONE window containing both.
                #
                # ONLY for a stream with BOTH mirrors readable this hour, and at least one stamp in
                # it. `pair_stamps` holds what was readable THIS cycle, and this record is decided
                # once and never revised -- while the heal path deliberately waits for a late mirror.
                # Unsynchronised, a stream whose second mirror lands a cycle later would have its
                # entire SINGLE-mirror silence booked as permanent loss, unbounded and unwalkbackable,
                # and the repo's own pair-add order (primary first) creates single-mirror hours by
                # construction. Without both, fall back to the intersection: it under-books, but it is
                # bounded by the window every stream demonstrably shared.
                stream_windows: dict[str, list] = {}
                for p in present:
                    frames = books[p]
                    both_mirrors = frames["primary"] is not None and frames["secondary"] is not None
                    own: list = []
                    for w in windows:
                        c = (
                            containing_dark_window(pair_stamps[p], w, hour_start=hour, hour_end=hour_end)
                            if both_mirrors and pair_stamps.get(p)
                            else w
                        )
                        if c is not None and c not in own:
                            own.append(c)
                    stream_windows[p] = own
                # Minus whatever that stream's own book record already booked for the same seconds:
                # normally none exists yet, but after a cycle in which an unreadable segment
                # suppressed this detector, a pair that minted meanwhile booked its residual first.
                residual = sum(
                    sum(c.seconds for c in own)
                    - overlap_seconds(_booked_residual(records, p, hour), [(c.start, c.end) for c in own])
                    for p, own in stream_windows.items()
                )
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
                    # What was ACTUALLY booked, per stream. `_booked_dark` reads this so the healed
                    # path subtracts the same seconds; `windows` stays as the intersection provenance.
                    stream_windows={
                        p: [{"start": c.start, "end": c.end, "seconds": c.seconds} for c in own]
                        for p, own in stream_windows.items()
                    },
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

            # Primary silence NO secondary update witnessed. Ledgered for visibility and counted
            # nowhere: whenever the fleet was dark those same seconds are already booked by
            # `both_streams_silent`, so a counter here would double-book them -- and when the fleet
            # was NOT dark, one pair silent on both mirrors cannot be told from a quiet market,
            # which is the ambiguity the fleet-wide intersection exists to resolve. Before this, the
            # pair with the LARGEST hole of an outage was the one that produced no record at all.
            if not _decided(pair, "book", hour, "unwitnessed"):
                blind = find_unwitnessed_gaps(
                    primary,
                    secondary,
                    min_gap_seconds=min_gap_seconds,
                    hour_start=hour,
                    hour_end=hour_end,
                )
                if blind:
                    logger.warning(
                        "archive reconcile: unwitnessed pair=%s hour=%s windows=%d seconds=%.1f "
                        "-- primary silence no secondary update covers; not healable, not counted",
                        pair,
                        hour.isoformat(),
                        len(blind),
                        sum(g.seconds for g in blind),
                    )
                    _ledger(
                        state="unwitnessed",
                        pair=pair,
                        kind="book",
                        hour=hour.isoformat(),
                        # No `residual_seconds` key AT ALL, deliberately: `_totals` adds that field
                        # unconditionally for every non-mint-family state, so a 0.0 would be inert
                        # only by value. Absent, it is inert by construction -- and a literal 0.0 on
                        # a record whose windows sum to 208 s also reads as "measured zero loss".
                        gaps_unwitnessed=[{"start": g.start, "end": g.end, "seconds": g.seconds} for g in blind],
                    )

            if not gaps:
                continue

            # Detect-only has no minted frame to measure, so it measures the witness that WOULD be
            # spliced -- the same rows, hence the same arithmetic. The mint path re-measures the
            # actual output below, because that is what the counters claim to describe.
            residual_gaps = measure_residual(gaps, secondary, min_gap_seconds=min_gap_seconds)
            entry = _book_entry(pair, hour, gaps, residual_gaps, _booked_dark(records, pair, hour))
            if not mint:
                logger.info(
                    "archive reconcile: would_mint pair=%s kind=book hour=%s healed_s=%.1f residual_s=%.1f",
                    pair,
                    hour.isoformat(),
                    entry["healed_seconds"],
                    entry["residual_seconds"],
                )
                _ledger(state="would_mint", **entry)
                continue

            try:
                full_secondary = _read(secondary_root, pair, "book", hour)
                full_primary = (
                    _read(primary_root, pair, "book", hour) if frames["primary"] is not None else pl.DataFrame(schema=BOOK_SCHEMA)
                )
                blocks = splice_book(full_primary, full_secondary, gaps)
                minted = pl.concat([b.frame for b in blocks]) if blocks else pl.DataFrame(schema=BOOK_SCHEMA)
                residual_gaps = measure_residual(gaps, minted, min_gap_seconds=min_gap_seconds)
                entry = _book_entry(pair, hour, gaps, residual_gaps, _booked_dark(records, pair, hour))
                mint_hour(
                    reconciled_root,
                    pair,
                    "book",
                    hour,
                    blocks,
                    gaps_healed=gaps,
                    residual_gaps=residual_gaps,
                    schema=BOOK_SCHEMA,
                    tool_version=version("zcrypto"),
                )
            except (CaptureError, OSError) as exc:
                _fail(pair, "book", hour, f"mint failed: {exc}")
                continue
            logger.info(
                "archive reconcile: minted pair=%s kind=book hour=%s healed_s=%.1f residual_s=%.1f",
                pair,
                hour.isoformat(),
                entry["healed_seconds"],
                entry["residual_seconds"],
            )
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


# --- verify-replay (spec 00051 OPS-3) --------------------------------------------------------------


@archive_app.command(name="verify-replay")
def verify_replay(
    primary_root: Path = typer.Argument(..., help="The primary mirror (raw, canonical-by-default)."),
    reconciled_root: Optional[Path] = typer.Argument(
        None, help="The healed overlay; its hours replay reconciled-first. Omit to replay the primary alone."
    ),
    pair: Optional[str] = typer.Option(None, "--pair", help="Only this pair (e.g. BTC/EUR). Defaults to every pair."),
    since: Optional[str] = typer.Option(None, "--since", help="Only hours at/after this UTC date (YYYY-MM-DD)."),
    depth: int = typer.Option(
        100, "--depth", help="Book depth the archive was captured at (capture's default 100); the replayed book prunes to it."
    ),
) -> None:
    """Continuity-replay every canonical book hour (reconciled-first, primary otherwise) through
    `OrderBook` and report, per hour: anchored (chain-anchored -- opens with a snapshot, or its exact
    predecessor hour was present and itself anchored and error-free), ts-ordered, checksum-present,
    replay-ok. Exits non-zero if any hour errs or fails any of the four checks (mirroring `engine
    replay`'s non-zero-on-drift contract). The stored `checksum` is trusted as capture-time ground
    truth; no CRC is re-derived (the Float64 archive cannot reproduce it byte-exactly)."""
    since_dt = None
    if since is not None:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise typer.BadParameter(f"--since {since!r} is not a YYYY-MM-DD date") from exc

    results = replay_mod.verify_replay(primary_root, reconciled_root, pair=pair, since=since_dt, depth=depth)
    if not results:
        typer.echo("no canonical book hours found")
        return

    failed = 0
    for result in results:
        hour_s = f"{result.hour:%Y-%m-%d %H}:00" if result.hour is not None else "?"
        line = (
            f"{result.pair}  {hour_s}  {'ok' if result.passed else 'FAILED'}  "
            f"anchored={result.anchored} ordered={result.ts_ordered} "
            f"checksum={result.checksum_present} replay={result.replay_ok} rows={result.rows} msgs={result.messages}"
        )
        if result.error is not None:
            line += f"  error={result.error}"
        typer.echo(line)
        if not result.passed:
            failed += 1
            logger.error(
                "archive verify-replay: hour failed pair=%s hour=%s anchored=%s ordered=%s checksum=%s replay=%s error=%s",
                result.pair,
                hour_s,
                result.anchored,
                result.ts_ordered,
                result.checksum_present,
                result.replay_ok,
                result.error,
            )

    typer.echo(f"replayed {len(results)} hour(s): {len(results) - failed} ok, {failed} failed")
    logger.info("verify-replay complete hours=%d ok=%d failed=%d", len(results), len(results) - failed, failed)
    if failed:
        raise typer.Exit(1)


# --- backfill-trades (spec 00053 Task 5) ------------------------------------------------------------


@archive_app.command(name="backfill-trades")
def backfill_trades(
    primary_root: Path = typer.Argument(..., help="The primary (raw) canonical trade archive."),
    reconciled_root: Path = typer.Argument(..., help="The overlay healed hours are minted into."),
    pair: Optional[str] = typer.Option(None, "--pair", help="Only this pair (e.g. BTC/EUR). Defaults to every pair."),
    detect_only: bool = typer.Option(False, "--detect-only", help="Report the loss; mint nothing."),
) -> None:
    """Heal the canonical trade stream to a contiguous, duplicate-free trade_id sequence: detect gaps
    against the archive, fetch the missing ids from Kraken's public REST, and mint healed hours into
    the reconciled overlay. Never fabricates a trade -- an id REST will not serve is `trades_unrecoverable`,
    a row fetched for an unsettled hour is `trades_deferred`, never minted and never silently dropped.

    THE loss report: `--detect-only` prints the magnitude of the damage, not just the
    gap count -- `trades_missing` and `duplicate_rows_found` are what the detector FOUND, populated in
    both modes; `recovered`/`duplicates_collapsed` are what actually landed and are 0 in `--detect-only`.

    Exits 2 when `primary_root` does not exist, 1 if the sweep recorded any error (a fetch failure, a
    mint failure, or a post-mint invariant violation), else 0."""
    if not primary_root.exists():
        logger.error("archive backfill-trades: primary root does not exist path=%s", primary_root)
        raise typer.Exit(2)

    res = backfill(primary_root, reconciled_root, pair=pair, now=_utc_now(), detect_only=detect_only)
    typer.echo(
        f"trade backfill complete pairs={res.pairs} gaps={res.gaps_found} "
        f"trades_missing={res.trades_missing} duplicate_rows_found={res.duplicate_rows_found} "
        f"recovered={res.trades_recovered} "
        f"unrecoverable={res.trades_unrecoverable} deferred={res.trades_deferred} "
        f"fetch_failed={res.trades_fetch_failed} mint_failed={res.trades_mint_failed} "
        f"duplicates_collapsed={res.duplicates_collapsed} duplicates_cross_hour={res.duplicates_cross_hour} "
        f"hours_minted={res.hours_minted} hours_repaired_after_loss={res.hours_repaired_after_loss} "
        f"errors={len(res.errors)}"
    )
    raise typer.Exit(1 if res.errors else 0)
