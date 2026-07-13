from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.capture.errors import CaptureError
from cli.logging import get_logger

logger = get_logger("capture.segment_writer")

# One row per book-update price-level change (snapshot rows use type="snapshot").
BOOK_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "type": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "qty": pl.Float64,
    "checksum": pl.Int64,
}

# One row per trade print.
TRADE_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "qty": pl.Float64,
    "ord_type": pl.Utf8,
    "trade_id": pl.Int64,
}

DEFAULT_FLUSH_ROWS = 5_000

# How far ahead of our own clock an event's `ts` may plausibly be. Rotation follows the event's ts,
# so one garbage far-future stamp would close the live hour early and then have the late-event guard
# drop every genuine row after it, for the life of the process. An hour of slack absorbs any credible
# skew between us and Kraken (the sweep already trusts this clock to say which hour is over).
MAX_TS_AHEAD = timedelta(hours=1)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hour_start(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _read_failure(path: Path) -> Exception | None:
    """`None` if every row of `path` can be read, else the exception the read failed with.

    Decodes all data pages — aggregating rather than materializing, so memory stays bounded. A
    Parquet file's footer can be perfectly intact while its body is not (bit-rot, a half-written
    page), and `collect_schema()`, which reads only the footer, passes such a file happily. Nothing
    may certify a segment — or trust a final over the parts beside it — on the footer alone.
    """
    try:
        pl.scan_parquet(path).select(pl.all().null_count()).collect(engine="streaming")
    except Exception as exc:
        return exc
    return None


def _replace_durably(tmp_path: Path, dest: Path) -> None:
    """`os.replace` into `dest`, fsyncing the data and then the directory entry.

    `replace` is atomic but not durable: on a machine power loss (as opposed to a process kill) the
    rename can reach the disk while the blocks it points at have not, leaving a torn file where an
    atomic one was promised. This dataset is unbackfillable, so take the durability.
    """
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    tmp_path.replace(dest)
    dir_fd = os.open(dest.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _part_index(path: Path) -> int:
    """`"<HH>.part0007.parquet"` -> `7`. Numeric, so part9999 sorts before part10000."""
    return int(path.name.split(".part")[1].split(".")[0])


def _hour_of(hour_dir: Path, hh: str) -> datetime:
    """`.../<YYYY>/<MM>/<DD>` + `"07"` -> that UTC hour."""
    day, month, year = hour_dir.name, hour_dir.parent.name, hour_dir.parent.parent.name
    return datetime(int(year), int(month), int(day), int(hh), tzinfo=UTC)


class SegmentWriter:
    """Buffers `(pair, kind)` capture events and streams them to hourly zstd-Parquet segments.

    Events are appended to a small in-memory buffer and flushed to a numbered "part" file once the
    buffer reaches `flush_rows` — the writer never holds more than that many rows in RAM at once,
    regardless of how much traffic an hour sees. Parts are written to a temp path and `replace()`d
    into place, so a hard kill can never leave a torn one. When an event's `ts` crosses into a new
    hour, the closing hour's parts are streamed (`scan_parquet` -> `sink_parquet`, not loaded whole)
    into `<HH>.parquet` and removed, and a sidecar `<file>.sha256` manifest is written.

    Restart-safe (T0036): the part sequence and the merge inputs are read from the hour directory on
    every use, never from process memory (which a restart resets), and construction repairs whatever
    a previous process left behind — stale parts from hours that are already over, a torn part, a
    final segment whose manifest was never written. Two invariants make crash recovery unambiguous:

    * `close()` **flushes but never finalizes**. A stop mid-hour therefore leaves parts, never a
      partial `<HH>.parquet` published as if it were a whole hour.
    * an hour is finalized exactly once, so a `<HH>.parquet` that **reads** is the commit marker: any
      part still sitting beside it has already been merged into it, and re-merging it would silently
      DUPLICATE every row (corrupting a reconstructed book exactly as badly as losing rows). Whether
      it reads is *checked against the file*, never assumed from its existence: a pre-T0036 process
      killed inside its non-atomic final write leaves a torn `<HH>.parquet` beside parts that still
      hold the whole hour, and there the parts — not the final — are the truth.

    The hour the process dies in is therefore finished by whoever comes next — this process's own
    rotation, or the next process's construction sweep. Nothing that cannot be read is ever deleted:
    it is quarantined to `<name>.corrupt` (never clobbering an earlier one) and kept as evidence.

    Segment layout: `<base_dir>/<pair>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet`.
    """

    def __init__(
        self,
        base_dir: Path,
        pair: str,
        kind: str,
        schema: dict[str, pl.DataType],
        *,
        flush_rows: int = DEFAULT_FLUSH_ROWS,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._pair = pair
        self._kind = kind
        self._schema = schema
        self._flush_rows = flush_rows
        self._buffer: list[dict] = []
        # The oldest hour this writer may still write to. Seeded from the clock — never left unset —
        # so the late-event guard below is live from the very FIRST event: `ws_client` resubscribes
        # with `snapshot=True` on every (re)connect, so after a restart the first event can be a
        # replayed print stamped before the hour boundary (T0026). Left ungated it would reopen an
        # hour that is already over — writing rows into a part beside its final (deleted at the next
        # merge), or, if the daemon was down across that hour, publishing a handful of replayed
        # prints as a complete, manifested segment for an hour that was never captured.
        self._current_hour = _hour_start(_utcnow())
        self._adopt_pending = True
        self._recover()

    def append(self, event: dict) -> None:
        """Append one event dict (keys matching `schema`). Rotates the previous hour's segment first
        if `event["ts"]` has crossed into a new hour."""
        if event["ts"] > _utcnow() + MAX_TS_AHEAD:
            logger.warning("dropping implausible event ts pair=%s kind=%s ts=%s", self._pair, self._kind, event["ts"])
            return
        hour = _hour_start(event["ts"])
        if hour < self._current_hour:
            # A row whose hour is already closed (a reconnect's trade snapshot replays prints from
            # before the boundary — T0026). Reopening that hour would either clobber its segment or
            # duplicate the rows it already holds, so the row is dropped rather than mis-filed.
            logger.warning(
                "dropping late event pair=%s kind=%s ts=%s hour=%s", self._pair, self._kind, event["ts"], self._current_hour
            )
            return
        if self._adopt_pending:
            self._adopt_pending = False
            self._adopt_partial_final(hour)
        if hour > self._current_hour:
            self._finalize_hour(self._current_hour)
        self._current_hour = hour
        self._buffer.append(event)
        if len(self._buffer) >= self._flush_rows:
            self._flush_buffer()

    def close(self) -> None:
        """Flush the buffer to a part file (idempotent). Deliberately does **not** finalize the open
        hour: publishing a partial `<HH>.parquet` would both present an incomplete hour as a whole
        segment and destroy the "a final means its parts are already merged" invariant that makes
        crash recovery unambiguous. The hour is finalized by whoever crosses its boundary."""
        self._flush_buffer()

    def _hour_dir(self, hour: datetime) -> Path:
        return self._base_dir / self._pair / self._kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"

    def _parts_for(self, hour_dir: Path, hh: str) -> list[Path]:
        """Every part file on disk for `<HH>`, in ascending sequence order."""
        return sorted(hour_dir.glob(f"{hh}.part*.parquet"), key=_part_index)

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        hour_dir = self._hour_dir(self._current_hour)
        hour_dir.mkdir(parents=True, exist_ok=True)
        hh = f"{self._current_hour:%H}"
        # The next sequence number is read from disk, so a writer resuming a half-written hour
        # starts *past* the highest part already there and can never overwrite it.
        parts = self._parts_for(hour_dir, hh)
        seq = _part_index(parts[-1]) + 1 if parts else 0
        part_path = hour_dir / f"{hh}.part{seq:04d}.parquet"
        tmp_path = part_path.with_name(part_path.name + ".tmp")
        df = pl.DataFrame(self._buffer, schema=self._schema)
        df.write_parquet(tmp_path, compression="zstd")
        _replace_durably(tmp_path, part_path)  # atomic + durable: a kill can never leave a torn part
        self._buffer = []

    def _finalize_hour(self, hour: datetime) -> None:
        self._flush_buffer()
        self._merge_hour(self._hour_dir(hour), f"{hour:%H}")

    def _merge_hour(self, hour_dir: Path, hh: str) -> None:
        """Merge every `<HH>.part*.parquet` on disk into `<HH>.parquet`, in part-sequence order.

        Idempotent, because every crash point of the sequence below recovers by re-running it:

        * killed before the `replace` -> only parts (plus a dead tmp) exist: merge again;
        * killed after it -> the final exists **and reads**, so the parts beside it are its own
          already-merged inputs: drop them (re-merging would duplicate every row) and write the
          manifest if it is missing, which heals a kill between the `replace` and the manifest write.

        The final's authority is *read from the file*, never inferred from its existence. A
        pre-T0036 process killed inside its non-atomic `sink_parquet` — the slow, IO-heavy step of an
        ordinary rotation — leaves a torn `<HH>.parquet` beside all the parts, which still hold the
        complete hour: there the final is worthless and the parts are the truth, so the final is
        quarantined and the hour rebuilt from them.

        Rows are concatenated in part order and are **never sorted**: L2 book deltas carry absolute
        quantities, so reordering rows that share a `ts` would silently corrupt the rebuilt book.
        """
        final_path = hour_dir / f"{hh}.parquet"
        manifest_path = final_path.with_name(final_path.name + ".sha256")
        parts = self._parts_for(hour_dir, hh)
        if final_path.exists():
            failure = _read_failure(final_path)
            if failure is None:
                if parts:
                    logger.warning(
                        "dropping %d already-merged part(s) pair=%s kind=%s path=%s",
                        len(parts),
                        self._pair,
                        self._kind,
                        final_path,
                    )
                    for part in parts:
                        part.unlink()
                if not manifest_path.exists():
                    # An EXISTING sidecar is never rewritten: a digest that no longer matches its
                    # file is real corruption (bit-rot, tampering), and re-blessing it would destroy
                    # the only detector this unbackfillable dataset has.
                    self._write_manifest(final_path)
                return
            if not parts:
                logger.error("unreadable segment left in place pair=%s kind=%s path=%s", self._pair, self._kind, final_path)
                return  # nothing better to put there — quarantining it would leave the hour empty
            self._quarantine(final_path, failure)
            manifest_path.unlink(missing_ok=True)  # a digest of bytes the quarantine still holds
        frames = [frame for part in parts if (frame := self._scan_part(part)) is not None]
        if not frames:
            return
        # Not `*.parquet`, so a tmp stranded by a crash is invisible to the archive's globs.
        tmp_path = hour_dir / f"{hh}.parquet.tmp"
        try:
            # An explicit per-file scan list: a multi-path `scan_parquet` may parallelize and does
            # not contractually preserve inter-file row order. `sink_parquet` still streams.
            pl.concat(frames, how="vertical").sink_parquet(tmp_path, compression="zstd")
        except Exception:
            # The merge runs on the rotation path too, and nothing between here and `_run` catches:
            # a raise would kill capture for every pair and both kinds. Leave the parts untouched —
            # the next restart's sweep retries the hour, and no row has been destroyed.
            tmp_path.unlink(missing_ok=True)
            logger.exception("merge failed pair=%s kind=%s path=%s", self._pair, self._kind, final_path)
            return
        _replace_durably(tmp_path, final_path)
        self._write_manifest(final_path)  # before the unlinks: while parts remain, recovery re-runs
        for part in parts:
            part.unlink(missing_ok=True)  # missing: an unreadable part was quarantined, not scanned
        logger.info("segment written pair=%s kind=%s path=%s", self._pair, self._kind, final_path)

    def _scan_part(self, part: Path) -> pl.LazyFrame | None:
        """Scan one part, or quarantine it and return `None` if it cannot be read.

        An unreadable part must never abort the merge: this runs from `__init__`, so a raise would
        propagate out of every `SegmentWriter(...)` the daemon builds at startup and crash-loop the
        whole capture — no pair, no kind, until a human intervenes. That is unbounded loss, far
        worse than the one part.
        """
        failure = _read_failure(part)
        if failure is not None:
            self._quarantine(part, failure)
            return None
        return pl.scan_parquet(part)

    def _quarantine(self, path: Path, failure: Exception) -> None:
        """Rename an unreadable file aside, **never delete it**: it is evidence, and rows may still
        be salvageable from it by hand. The target is never clobbered — a rename would silently
        overwrite an earlier quarantine's bytes, and the same name does recur (the part sequence
        globs `<HH>.part*.parquet`, which `.corrupt` files do not match, so once every part of an
        hour has been quarantined the numbering restarts at 0000)."""
        dest = path.with_name(path.name + ".corrupt")
        seq = 0
        while dest.exists():
            seq += 1
            dest = path.with_name(f"{path.name}.corrupt.{seq}")
        path.rename(dest)
        logger.error(
            "quarantined unreadable file pair=%s kind=%s path=%s dest=%s error=%s",
            self._pair,
            self._kind,
            path,
            dest,
            failure,
        )

    def _recover(self) -> None:
        """Repair what a previous process left behind. Runs at construction and must not raise: the
        daemon builds one writer per (pair, kind) before it connects, so anything escaping here
        stops capture entirely, on every restart."""
        root = self._base_dir / self._pair / self._kind
        for tmp in root.rglob("*.tmp"):
            # A merge tmp is re-derivable from the parts, which are still on disk; a part tmp holds
            # only rows that never reached a part file (same loss as an unflushed buffer).
            tmp.unlink(missing_ok=True)

        now_hour = self._current_hour  # one clock read, shared with the late-event guard's seed
        for hour_dir in sorted({p.parent for p in root.rglob("*.part*.parquet")}):
            for hh in sorted({p.name.split(".part")[0] for p in hour_dir.glob("*.part*.parquet")}):
                try:
                    if _hour_of(hour_dir, hh) >= now_hour:
                        continue  # the hour in progress — this writer resumes its parts
                    self._merge_hour(hour_dir, hh)
                except Exception:
                    logger.exception(
                        "stale-hour recovery failed pair=%s kind=%s dir=%s hour=%s", self._pair, self._kind, hour_dir, hh
                    )
        self._bless_unmanifested_finals(root)

    def _adopt_partial_final(self, hour: datetime) -> None:
        """Demote a `<HH>.parquet` for the hour this writer is opening back to `part0000`.

        Only a pre-T0036 process writes one: its `close()` published the open hour on a graceful
        stop, so the rows are in the final but in no part file. Left alone, the rest of the hour's
        parts would be dropped by `_merge_hour` as "already merged" and the hour would end at the
        restart. Demoting is content-preserving in every reading of the file — it simply becomes the
        merge's first input, so its rows land in the final exactly once, in order.

        Keyed on the hour of the **first event this writer accepts**, not on the wall clock: rotation
        follows Kraken's exchange time, so a lagging (or backward-stepped) local clock would put a
        restart in a window where a cleanly committed final looks like the hour still in progress —
        demoting it and leaving the hour unpublished for the daemon's whole uptime. The late-event
        guard has already rejected every hour that is over, so the first accepted event's hour is by
        construction the one still open.
        """
        hour_dir = self._hour_dir(hour)
        hh = f"{hour:%H}"
        final_path = hour_dir / f"{hh}.parquet"
        if not final_path.exists() or self._parts_for(hour_dir, hh):
            return  # with parts beside it, the final is a committed one: `_merge_hour`'s rule holds
        final_path.rename(hour_dir / f"{hh}.part0000.parquet")
        final_path.with_name(final_path.name + ".sha256").unlink(missing_ok=True)
        logger.warning("adopted partial segment pair=%s kind=%s path=%s", self._pair, self._kind, final_path)

    def _bless_unmanifested_finals(self, root: Path) -> None:
        """Write the sidecar for any final segment that has none.

        A pre-T0036 process could die between publishing `<HH>.parquet` and writing its manifest,
        and nothing retriggers that write (no parts remain to merge), so good data stays flagged
        corrupt by `verify_manifest` forever. An **existing** sidecar is never touched: a digest that
        no longer matches is a real integrity signal (bit-rot, tampering), and silently re-blessing
        it would destroy the only detector we have.
        """
        for final_path in sorted(root.rglob("*.parquet")):
            manifest_path = final_path.with_name(final_path.name + ".sha256")
            if ".part" in final_path.name or manifest_path.exists():
                continue
            failure = _read_failure(final_path)  # never bless a segment we cannot read as verified
            if failure is not None:
                logger.error(
                    "unreadable segment left unmanifested pair=%s kind=%s path=%s error=%s",
                    self._pair,
                    self._kind,
                    final_path,
                    failure,
                )
                continue
            self._write_manifest(final_path)
            logger.warning("wrote missing manifest pair=%s kind=%s path=%s", self._pair, self._kind, final_path)

    def _write_manifest(self, path: Path) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path = path.with_name(path.name + ".sha256")
        manifest_path.write_text(f"{digest}  {path.name}\n")

    def __enter__(self) -> SegmentWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def verify_manifest(path: Path) -> bool:
    """Recompute `path`'s sha256 and compare it against its `<path>.sha256` sidecar."""
    manifest_path = path.with_name(path.name + ".sha256")
    if not manifest_path.exists():
        raise CaptureError(f"no manifest for {path}")
    recorded = manifest_path.read_text().split()[0]
    return hashlib.sha256(path.read_bytes()).hexdigest() == recorded
