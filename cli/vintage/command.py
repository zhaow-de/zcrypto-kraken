"""The `zcrypto vintage` Typer sub-app."""

from __future__ import annotations

import contextlib
import logging
import sys
import traceback
import urllib.request
from datetime import UTC
from pathlib import Path
from typing import BinaryIO, Optional

import typer

from cli.capture.command import single_instance_lock
from cli.capture.errors import CaptureError
from cli.logging import get_logger
from cli.vintage import chain as chain_mod
from cli.vintage import verify as verify_mod
from cli.vintage.credential import read_key
from cli.vintage.fetch import Clock, SystemClock
from cli.vintage.gauges import render_prom
from cli.vintage.record import RECORD_SUBDIR, Published, RecordRefused, record_tick
from cli.vintage.sources import SOURCE_BY_ID
from cli.vintage.storage import publish_prom

# The ops re-verify after each tick: the newest ticks along the chain, and the slice the count of published ticks names.
OPS_VERIFY_NEWEST = 4
OPS_VERIFY_SLICES = 14

log = get_logger("vintage.verify")
record_log = get_logger("vintage.record")

vintage_app = typer.Typer(help="The vintage record: every byte the free on-chain and sentiment sources serve, twice a day.")


@vintage_app.command("verify")
def verify_cmd(
    root: Path = typer.Option(..., "--root", help="A copy of the record: the directory holding <year>/<month>/<day>/<stamp>/."),
    custody: bool = typer.Option(
        False,
        "--custody",
        help="Read the copy as the only custody of an acknowledged fork's tick off the chain, as every read of the NAS copy does.",
    ),
    newest: Optional[int] = typer.Option(
        None,
        "--newest",
        min=0,
        metavar="N",
        help="Re-hash the bodies of the newest N ticks along the chain and of the slice alone; takes --slice and --slices.",
    ),
    slice_: Optional[int] = typer.Option(
        None, "--slice", min=0, metavar="K", help="The slice: every tick whose position in stamp order is K modulo M."
    ),
    slices: Optional[int] = typer.Option(None, "--slices", min=1, metavar="M", help="M, the count of slices."),
) -> None:
    """Verify a copy of the record: its chain, its bodies and the files its ticks hold; exit 0 clean, 1 otherwise."""
    if (newest, slice_, slices).count(None) not in (0, 3):
        raise typer.BadParameter("--newest, --slice and --slices go together")
    if slices is not None and slice_ >= slices:
        raise typer.BadParameter("--slice must be below --slices")
    result = verify_mod.verify(root, newest=newest, slice_=slice_, slices=slices, custody=custody)
    for finding in result.breaks:
        log.error("vintage verify %s path=%s: %s", finding.kind, finding.path, finding.detail)
    for finding in result.notes:
        log.info("vintage verify %s path=%s: %s", finding.kind, finding.path, finding.detail)
    log.log(
        logging.ERROR if result.breaks else logging.INFO,
        "vintage verify complete ticks=%d head=%s head_tick_json_sha256=%s bodies_hashed=%d breaks=%d",
        result.ticks,
        result.head or "none",
        result.head_tick_json_sha256 or "none",
        result.bodies_hashed,
        len(result.breaks),
    )
    if result.breaks:
        raise typer.Exit(code=1)


def _failure(exc: Exception) -> str:
    """The exception's class and its innermost frame's file, line and function: names in code, never the exception's
    text, which can carry a request's header."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return type(exc).__name__
    return f"{type(exc).__name__} at {frames[-1].filename}:{frames[-1].lineno} in {frames[-1].name}"


def _write_gauges(record_root: Path, chain: chain_mod.Chain, published: Published, textfile: Path, clock: Clock) -> bool:
    try:
        publish_prom(textfile, render_prom(record_root, chain, published, today=clock.now().astimezone(UTC).date()))
    except Exception as exc:
        record_log.error("vintage gauges not written path=%s: %s", textfile, _failure(exc))
        return False
    return True


def _after_publish(data_dir: Path, textfile: Path, published: Published, clock: Clock) -> int:
    record_root = data_dir / RECORD_SUBDIR
    chain = chain_mod.chain(chain_mod.scan(record_root).ticks)
    written = _write_gauges(record_root, chain, published, textfile, clock)
    result = verify_mod.verify(
        record_root,
        newest=OPS_VERIFY_NEWEST,
        slice_=len(chain.order) % OPS_VERIFY_SLICES,
        slices=OPS_VERIFY_SLICES,
    )
    for finding in result.breaks:
        record_log.error("vintage verify %s path=%s: %s", finding.kind, finding.path, finding.detail)
    clean = not result.breaks
    counts = {0: 0, 1: 0, 2: 0}
    stored = 0
    for fetch in published.manifest["fetches"]:
        check = fetch["check"]
        counts[check["outcome"]] += 1
        stored += fetch["body"]["bytes"] if fetch["body"] else 0
        if check["outcome"] != 0:
            record_log.warning("vintage source not ok source=%s outcome=%d: %s", fetch["source"], check["outcome"], check["reason"])
    record_log.info(
        "vintage record complete tick=%s tick_json_sha256=%s ok=%d not_fetched=%d failed_checks=%d bytes=%d",
        published.stamp,
        published.tick_json_sha256,
        counts[0],
        counts[1],
        counts[2],
        stored,
    )
    every_ok = counts[0] == len(published.manifest["fetches"])
    return 0 if every_ok and written and published.after_rename is None and clean else 1


def run_record(
    data_dir: Path,
    textfile: Path,
    clock_prom: Path,
    *,
    key_stream: BinaryIO | None,
    https_handler: urllib.request.BaseHandler | None = None,
    clock: Clock | None = None,
    version: str | None = None,
    revision: str | None = None,
    sources: tuple[str, ...] = (),
) -> int:
    """One tick, its gauges and its re-verify; the exit code: 0 every source ok, the gauges written and the re-verify
    clean, 1 published with any of those not, 2 nothing published. No exception leaves it."""
    unknown = [source for source in sources if source not in SOURCE_BY_ID]
    for source in unknown:
        record_log.error("unknown source %s; the fetch table's ids are %s", source, " ".join(SOURCE_BY_ID))
    if unknown:
        return 2
    clock = SystemClock() if clock is None else clock
    published: Published | None = None
    try:
        key, key_reason = read_key(key_stream)
        with contextlib.ExitStack() as held:
            try:
                held.enter_context(single_instance_lock(data_dir))
            except CaptureError:
                record_log.error(
                    "another vintage recorder holds %s; refusing. Read the zcrypto-vintage-record.service journal and docker ps -a --filter name=zcrypto-vintage-record",
                    data_dir,
                )
                return 2
            published = record_tick(
                data_dir,
                key=key,
                key_reason=key_reason,
                clock_prom=clock_prom,
                https_handler=https_handler,
                clock=clock,
                version=version,
                revision=revision,
                only=frozenset(sources) or None,
            )
            return _after_publish(data_dir, textfile, published, clock)
    except RecordRefused as exc:
        record_log.error("%s; nothing published", exc)
        return 2
    except Exception as exc:
        if published is None:
            record_log.error("vintage record failed, nothing published: %s", _failure(exc))
            return 2
        record_log.error("vintage record failed after publishing tick=%s: %s", published.stamp, _failure(exc))
        return 1


@vintage_app.command("record")
def record_cmd(
    data_dir: Path = typer.Option(..., "--data-dir", help="The recorder's root: record/, staging/ and the lock."),
    textfile: Path = typer.Option(..., "--textfile", help="The .prom file the gauges are written to."),
    clock_prom: Path = typer.Option(..., "--clock-prom", help="The host clock-offset .prom, read into tick.json as evidence."),
    bgeometrics_key_stdin: bool = typer.Option(
        False,
        "--bgeometrics-key-stdin",
        help="Read the BGeometrics key from stdin; without it the keyed sources read no credential.",
    ),
    source: Optional[list[str]] = typer.Option(
        None, "--source", metavar="ID", help="Fetch only the sources named, every other recorded as not selected; once per source."
    ),
) -> None:
    """Record one tick: fetch every source, publish the tick, write the gauges and re-verify; exit 0 all ok, 1 published
    with something not ok, 2 nothing published."""
    code = run_record(
        data_dir,
        textfile,
        clock_prom,
        key_stream=sys.stdin.buffer if bgeometrics_key_stdin else None,
        sources=tuple(source or ()),
    )
    raise typer.Exit(code=code)
