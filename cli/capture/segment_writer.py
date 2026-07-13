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

# How far ahead a `ts` may be of BOTH our own clock AND the stream itself before it is garbage
# rather than data (see `_implausible`). Rotation follows the event's ts, so one far-future stamp
# would close the live hour early and then have the late-event guard drop every genuine row after it.
MAX_TS_AHEAD = timedelta(hours=1)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hour_start(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _read_failure(path: Path) -> Exception | None:
    """`None` if every row of `path` can be read, else the exception the read failed with.

    Decodes all data pages — aggregating rather than materializing, so memory stays bounded. A
    Parquet file's footer can be perfectly intact while its body is not (bit-rot, a half-written
    page), and `collect_schema()`, which reads only the footer, passes such a file happily.
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


def _part_index(path: Path) -> int | None:
    """`"<HH>.part0007.parquet"` -> `7`; `None` if the name is not one of ours.

    Numeric, so part9999 sorts before part10000. Never raises: it runs on the `append()` path, and a
    `<HH>.part0000-copy.parquet` (a human's backup, an rsync artefact) would otherwise take down
    capture for every pair and both kinds, on every restart.
    """
    try:
        return int(path.name.split(".part")[1].split(".")[0])
    except IndexError, ValueError:
        return None


def _hour_of(hour_dir: Path, hh: str) -> datetime | None:
    """`.../<YYYY>/<MM>/<DD>` + `"07"` -> that UTC hour; `None` if the path is not one of ours.

    Nothing this writer creates fails to parse, but construction and the rotation path both walk the
    tree, and a raise from either stops capture for every pair and both kinds — so a stray file is
    skipped, never fatal.
    """
    day, month, year = hour_dir.name, hour_dir.parent.name, hour_dir.parent.parent.name
    try:
        return datetime(int(year), int(month), int(day), int(hh), tzinfo=UTC)
    except ValueError:
        return None


class SegmentWriter:
    """Buffers `(pair, kind)` capture events and streams them to hourly zstd-Parquet segments.

    Events are appended to a small in-memory buffer and flushed to a numbered "part" file once the
    buffer reaches `flush_rows` — the writer never holds more than that many rows in RAM at once,
    regardless of how much traffic an hour sees. When an event's `ts` crosses into a new hour, the
    closing hour's parts are streamed (`scan_parquet` -> `sink_parquet`, never loaded whole) into
    `<HH>.parquet`, alongside a sidecar `<file>.sha256` manifest.

    One invariant makes crash recovery mechanical, with nothing left to guess (T0036):

        **`<HH>.parquet` on disk is ALWAYS a committed, complete final.**

    It holds because `close()` flushes but never finalizes (a stop mid-hour leaves parts, never a
    part-hour published as a whole one), and because the final is the LAST thing a merge writes —
    the merged bytes go to `<HH>.parquet.merging` first, atomically, and are renamed into place only
    once the manifest is written and the consumed parts are gone. So:

    * a `<HH>.parquet.merging` on disk is a complete merge that was interrupted before it was
      published: it is authoritative, and committing it is all recovery has to do;
    * a part beside a `<HH>.parquet` is a state nothing this writer does can reach. It is a
      pre-T0036 leftover, and it is genuinely AMBIGUOUS (see `_merge_hour`) — so it is left exactly
      as it is, for a human. Nothing is guessed, nothing is unlinked, nothing is re-blessed.

    From the same invariant the writer needs **no wall clock**: "hour HH is closed" is exactly
    "`<HH>.parquet` exists", read off disk at construction. A clock leading for one instant (a boot
    before chrony's first step) would otherwise seed that state wrong and silently drop the entire
    live stream for up to 59:59. Which hours are over is likewise read from the event stream — the
    exchange's clock — not ours: the startup sweep runs on the first event, and finalizes every hour
    that still holds parts and is strictly before it.

    Nothing unreadable is ever deleted: it is quarantined to `<name>.corrupt` (never clobbering an
    earlier one) and kept as evidence.

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
        dedup_key: str | None = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._pair = pair
        self._kind = kind
        self._schema = schema
        self._flush_rows = flush_rows
        self._dedup_key = dedup_key
        self._buffer: list[dict] = []
        self._current_hour: datetime | None = None  # the open hour; None until the first event
        self._max_ts: datetime | None = None
        self._seen: set = set()
        self._floor: datetime | None = None  # oldest hour still open, per the segments on disk
        self._recover()

    def append(self, event: dict) -> None:
        """Append one event dict (keys matching `schema`). Rotates the previous hour's segment first
        if `event["ts"]` has crossed into a new hour."""
        ts = event["ts"]
        if self._implausible(ts):
            logger.warning("dropping implausible event ts pair=%s kind=%s ts=%s", self._pair, self._kind, ts)
            return
        hour = _hour_start(ts)
        floor = self._current_hour or self._floor
        if floor is not None and hour < floor:
            # An hour that is already closed — a `<HH>.parquet` for it is on disk. A reconnect's
            # trade snapshot replays prints from before the boundary (T0026); writing them beside a
            # committed final would either duplicate rows it already holds or strand them.
            logger.warning("dropping late event pair=%s kind=%s ts=%s floor=%s", self._pair, self._kind, ts, floor)
            return
        if self._current_hour is None:
            self._sweep(hour)  # deferred to here: the first event's hour is exchange time
            self._open_hour(hour)
        elif hour > self._current_hour:
            self._finalize_hour(self._current_hour)
            self._open_hour(hour)
        if self._dedup_key is not None:
            key = event[self._dedup_key]
            if key in self._seen:
                logger.warning("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
            self._seen.add(key)
        if self._max_ts is None or ts > self._max_ts:
            self._max_ts = ts
        self._buffer.append(event)
        if len(self._buffer) >= self._flush_rows:
            self._flush_buffer()

    def close(self) -> None:
        """Flush the buffer to a part file (idempotent). Deliberately does **not** finalize the open
        hour: `<HH>.parquet` means "committed and complete", and publishing a stop's half-hour under
        that name is what made crash recovery ambiguous. The hour is finalized by whoever crosses its
        boundary — this process, or the next one's sweep."""
        self._flush_buffer()

    def _implausible(self, ts: datetime) -> bool:
        """True only if `ts` is far ahead of BOTH our own clock AND the stream itself.

        Two witnesses must agree before a row is thrown away, because either one alone has a failure
        mode that silently costs the whole stream for as long as it lasts:

        * the clock alone — a local clock lagging by more than MAX_TS_AHEAD rejects every live event
          (and chrony only *slews* an offset that appears after startup, so it can last hours);
        * the stream alone — a pair can genuinely go an hour without a print (the thin EUR alts do,
          overnight), and the next real trade would then be rejected against a reference that can
          never advance again, since a DROPPED event does not advance it.

        Before this process has accepted an event there is no second witness at all, so nothing is
        dropped: the clock is never the sole judge of live data. (Seeding the witness from the newest
        segment on disk looks tempting and is worse than useless — an outage longer than
        MAX_TS_AHEAD leaves it stale by exactly the length of the outage, so both witnesses then fire
        on the first genuine event of the recovery and the stream stays dark.)
        """
        if self._max_ts is None:
            return False
        return ts > self._max_ts + MAX_TS_AHEAD and ts > _utcnow() + MAX_TS_AHEAD

    def _hour_dir(self, hour: datetime) -> Path:
        return self._base_dir / self._pair / self._kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"

    def _parts_for(self, hour_dir: Path, hh: str) -> list[Path]:
        """Every part file on disk for `<HH>`, in ascending sequence order. A name whose sequence
        does not parse is not one of ours: it is skipped, never guessed at and never fatal."""
        indexed = [(seq, path) for path in hour_dir.glob(f"{hh}.part*.parquet") if (seq := _part_index(path)) is not None]
        return [path for _, path in sorted(indexed)]

    def _open_hour(self, hour: datetime) -> None:
        self._current_hour = hour
        self._seen = set()
        if self._dedup_key is None:
            return
        # Seed the de-dup set from the parts a previous process already wrote for this hour. On a
        # mid-hour restart `ws_client` resubscribes with snapshot=True and Kraken REPLAYS its recent
        # prints (T0026); they are already on disk, so an in-memory-only de-dup would not recognize
        # them and the hour's segment would hold each replayed print twice. Duplicated rows corrupt a
        # reconstructed book exactly as badly as lost ones.
        parts = self._parts_for(self._hour_dir(hour), f"{hour:%H}")
        if not parts:
            return
        try:
            self._seen = set(self._keys_of(parts))
        except Exception:
            # One unreadable part must not silently empty the whole set — that is how the replay
            # gets written a second time. Take the keys of every part that CAN be read; a part that
            # cannot is quarantined at the merge, so its rows never reach the segment and a replay of
            # them is a recovery, not a duplicate.
            for part in parts:
                try:
                    self._seen |= set(self._keys_of([part]))
                except Exception:
                    logger.exception("could not read de-dup keys pair=%s kind=%s path=%s", self._pair, self._kind, part)

    def _keys_of(self, parts: list[Path]) -> pl.Series:
        return pl.scan_parquet(parts).select(self._dedup_key).collect()[self._dedup_key]

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        hour_dir = self._hour_dir(self._current_hour)
        hh = f"{self._current_hour:%H}"
        try:
            hour_dir.mkdir(parents=True, exist_ok=True)
            # The next sequence number is read from disk, so a writer resuming a half-written hour
            # starts *past* the highest part already there and can never overwrite it.
            parts = self._parts_for(hour_dir, hh)
            seq = (_part_index(parts[-1]) or 0) + 1 if parts else 0
            part_path = hour_dir / f"{hh}.part{seq:04d}.parquet"
            tmp_path = part_path.with_name(part_path.name + ".tmp")
            df = pl.DataFrame(self._buffer, schema=self._schema)
            df.write_parquet(tmp_path, compression="zstd")
            _replace_durably(tmp_path, part_path)  # atomic + durable: a kill can never leave a torn part
        except Exception:
            # The hottest write in the daemon (every `flush_rows` rows), and it is one `OSError`
            # (EIO, ENOSPC despite DiskWatermark) away from taking down the single consumer task —
            # i.e. capture for all 10 pairs and both kinds. This buffer is lost either way; the other
            # 19 streams need not be. The dead-man's switch goes red on the watermark breach that
            # normally causes this, and the traceback names the pair.
            logger.exception("flush failed — buffer dropped pair=%s kind=%s hour=%s", self._pair, self._kind, hh)
        self._buffer = []

    def _finalize_hour(self, hour: datetime) -> None:
        self._flush_buffer()
        self._merge_hour(self._hour_dir(hour), f"{hour:%H}")

    def _merge_hour(self, hour_dir: Path, hh: str) -> None:
        """Merge the hour's parts into a committed `<HH>.parquet`. Never raises.

        This runs on `append()`'s rotation path, and nothing between here and `_run` catches: a raise
        would kill capture for every pair and both kinds. Every step below leaves the hour fully
        recoverable — a part is unlinked only once the merged bytes that contain it are durable — so
        on any failure the right move is to log and carry on, and let the next boundary (or the next
        process's sweep) retry the hour. No row is ever destroyed by giving up here.
        """
        final_path = hour_dir / f"{hh}.parquet"
        merging_path = hour_dir / f"{hh}.parquet.merging"
        parts = self._parts_for(hour_dir, hh)
        if not parts:
            return  # already committed, or the hour was never captured: nothing to merge
        try:
            if merging_path.exists():
                # A merge that `_recover` could not finish (its commit hit an IO error). Those bytes
                # may be the hour's ONLY copy — the parts they came from are already unlinked — so
                # they are never sunk over. Only `_recover` promotes them; leave it to the next start.
                logger.error("an uncommitted merge is in the way pair=%s kind=%s path=%s", self._pair, self._kind, merging_path)
                return
            if final_path.exists():
                failure = _read_failure(final_path)
                if failure is None:
                    # AMBIGUOUS, and unresolvable from here — the pre-T0036 writer produced BOTH
                    # readings of this state: `close()` published the open hour, so the parts hold
                    # rows the final does NOT have (merging is right); and its finalize unlinked the
                    # parts only AFTER sinking the final, so a kill there leaves parts the final
                    # ALREADY holds (merging would duplicate the whole hour). Guessing either way
                    # destroys the data — round 3 unlinked them, and it deleted real rows. Every byte
                    # is on disk and nothing here is on fire, so touch nothing and let a human look.
                    logger.error(
                        "parts beside a readable final — ambiguous, left untouched pair=%s kind=%s path=%s parts=%d",
                        self._pair,
                        self._kind,
                        final_path,
                        len(parts),
                    )
                    return
                # An unreadable final holds no rows anyone can recover, so it cannot be the truth and
                # cannot be an input: quarantine it (never delete) and rebuild the hour from the parts.
                self._quarantine(final_path, failure)
            if self._write_merging(parts, merging_path):
                self._commit(merging_path, final_path)
                logger.info("segment written pair=%s kind=%s path=%s", self._pair, self._kind, final_path)
        except Exception:
            logger.exception("merge failed pair=%s kind=%s dir=%s hour=%s", self._pair, self._kind, hour_dir, hh)

    def _write_merging(self, inputs: list[Path], merging_path: Path) -> bool:
        """Stream `inputs` into `<HH>.parquet.merging`, atomically. False if nothing could be read.

        Rows are concatenated in input order and are **never sorted**: L2 book deltas carry ABSOLUTE
        quantities, so re-ordering rows that share a `ts` silently corrupts the rebuilt book.

        The happy path decodes each input exactly ONCE — the read IS the validation. Only if it
        actually fails is every input decoded on its own, to quarantine the unreadable one and merge
        the rest: pre-validating every part on every rotation cost a 27s event-loop stall at each
        hour boundary across the 20 streams, starving the healthcheck and disk-watermark loops.
        """
        tmp_path = merging_path.with_name(merging_path.name + ".tmp")
        try:
            try:
                pl.scan_parquet(inputs).sink_parquet(tmp_path, compression="zstd")
            except Exception:
                inputs = [path for path in inputs if self._readable(path)]
                if not inputs:
                    return False
                pl.scan_parquet(inputs).sink_parquet(tmp_path, compression="zstd")
            _replace_durably(tmp_path, merging_path)
            return True
        finally:
            # A no-op once the replace has consumed it. On a failure it is a half-sunk full-hour file
            # on the very disk DiskWatermark guards, and it is re-derivable from the untouched parts.
            tmp_path.unlink(missing_ok=True)

    def _commit(self, merging_path: Path, final_path: Path) -> None:
        """Publish an interrupted-or-fresh `<HH>.parquet.merging` as the hour's committed final.

        The merging file was written atomically, so it is whole — it, never the parts and never a
        half-written final, is the authority. The order is what makes recovery mechanical:

        1. the manifest, from the merging file's bytes (which ARE the final's bytes, so the digest is
           right before the file it certifies exists) — a final can never be published unmanifested;
        2. the parts, which are now provably inside durable merged bytes — and only now;
        3. the rename, atomic and last.

        A kill anywhere in here leaves a `<HH>.parquet.merging` behind, and the next construction
        simply re-runs these three steps. Nothing has to be inferred from what is or is not on disk.
        """
        self._write_manifest(merging_path, final_path)
        for part in self._parts_for(final_path.parent, final_path.name.split(".")[0]):
            part.unlink(missing_ok=True)
        _replace_durably(merging_path, final_path)

    def _readable(self, path: Path) -> bool:
        """True if every row of `path` decodes; else quarantine it and return False.

        One unreadable input must never abort the merge: it runs on the rotation path and, on a
        restart, over every hour a previous process left behind — so a raise here stops capture for
        every pair and both kinds until a human intervenes. That is unbounded loss, far worse than
        the one file.
        """
        failure = _read_failure(path)
        if failure is None:
            return True
        self._quarantine(path, failure)
        return False

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
        """Finish what a previous process left mid-merge, and read off disk which hours are closed.

        Runs at construction and must not raise: the daemon builds one writer per (pair, kind) before
        it connects, so anything escaping here stops capture entirely, on every restart. It merges
        nothing — that needs to know which hour is still in progress, which only the event stream can
        say (`_sweep`).
        """
        root = self._base_dir / self._pair / self._kind
        for tmp in root.rglob("*.tmp"):
            # Re-derivable: a merge tmp from the parts (still on disk), a part tmp from rows that
            # never reached a part file (the same loss as an unflushed buffer).
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
        for merging_path in sorted(root.rglob("*.parquet.merging")):
            final_path = merging_path.with_name(merging_path.name.removesuffix(".merging"))
            try:
                if final_path.exists():
                    # Unreachable from any kill: the rename that publishes a final is atomic and is
                    # what consumes the merging file. So this is a hand-edit or a restored backup —
                    # and committing would overwrite a COMMITTED final and re-bless its sidecar. The
                    # one thing recovery must never do is overwrite what the invariant calls whole.
                    logger.error(
                        "an interrupted merge beside a committed final — left untouched pair=%s kind=%s path=%s",
                        self._pair,
                        self._kind,
                        merging_path,
                    )
                    continue
                self._commit(merging_path, final_path)
                logger.warning("committed an interrupted merge pair=%s kind=%s path=%s", self._pair, self._kind, final_path)
            except Exception:
                logger.exception(
                    "could not commit an interrupted merge pair=%s kind=%s path=%s", self._pair, self._kind, final_path
                )
        # Which hours are closed. A `<HH>.parquet` is one, by the invariant. So is a `.merging` file
        # that would not commit above: its bytes may be the hour's only copy (the parts are already
        # unlinked), and an hour left open here could be re-opened by the live stream and its merge
        # would then sink straight over them.
        hours = [
            hour
            for path in (*root.rglob("*.parquet"), *root.rglob("*.parquet.merging"))
            if ".part" not in path.name and (hour := _hour_of(path.parent, path.name.split(".")[0])) is not None
        ]
        self._floor = max(hours) + timedelta(hours=1) if hours else None

    def _sweep(self, before: datetime) -> None:
        """Finalize every hour that still holds parts and is strictly before `before` — the hour of
        the first event this writer accepts, i.e. Kraken's own clock. Whatever a previous process
        left unfinished (the hour it died in, or hours it slept through) is closed here."""
        root = self._base_dir / self._pair / self._kind
        for hour_dir in sorted({path.parent for path in root.rglob("*.part*.parquet")}):
            for hh in sorted({path.name.split(".part")[0] for path in hour_dir.glob("*.part*.parquet")}):
                hour = _hour_of(hour_dir, hh)
                if hour is not None and hour < before:
                    self._merge_hour(hour_dir, hh)

    def _write_manifest(self, source: Path, final_path: Path) -> None:
        """Write `<HH>.parquet.sha256` from `source`'s bytes — atomically and durably, so a kill can
        never leave a torn or empty sidecar that nothing would rewrite.

        Only ever called for a final this writer is itself publishing (`source` is the merging file
        whose bytes it is about to become). The sidecar of any other final is never touched: a digest
        that no longer matches its file is real corruption, and re-blessing it would destroy the only
        bit-rot detector this unbackfillable dataset has.
        """
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_path = final_path.with_name(final_path.name + ".sha256")
        tmp_path = manifest_path.with_name(manifest_path.name + ".tmp")
        tmp_path.write_text(f"{digest}  {final_path.name}\n")
        _replace_durably(tmp_path, manifest_path)

    def __enter__(self) -> SegmentWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def verify_manifest(path: Path) -> bool:
    """Recompute `path`'s sha256 and compare it against its `<path>.sha256` sidecar."""
    manifest_path = path.with_name(path.name + ".sha256")
    recorded = manifest_path.read_text().split() if manifest_path.exists() else []
    if not recorded:
        # An EMPTY or unparseable sidecar is a MISSING one, not a mismatch — a pre-T0036 process
        # killed inside its non-atomic `write_text` left a 0-byte file, and `split()[0]` then raised
        # IndexError out of the archive's verify_tree instead of reporting the hour.
        raise CaptureError(f"no manifest for {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest() == recorded[0]
