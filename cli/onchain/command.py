"""The `zcrypto onchain` Typer sub-app."""

from __future__ import annotations

import traceback
from datetime import UTC, date, datetime
from pathlib import Path

import typer

from cli.capture.errors import CaptureError
from cli.logging import get_logger
from cli.onchain.brk import BrkClient
from cli.onchain.chain import ChainError, chain_name, line_days, verify, walk
from cli.onchain.freeze import freeze
from cli.onchain.write import run_write

log = get_logger("onchain.command")

onchain_app = typer.Typer(help="BTC's on-chain valuation series from a pinned BRK beside our own node, one vintage per UTC day.")


def _failure(exc: Exception) -> str:
    """The exception's class and its innermost frame's file, line and function: names in code, never the exception's
    text, which can carry a request's header."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return type(exc).__name__
    return f"{type(exc).__name__} at {frames[-1].filename}:{frames[-1].lineno} in {frames[-1].name}"


def _head(root: Path) -> str:
    try:
        days = line_days(root)
    except Exception:
        return "unread"
    return days[-1].isoformat() if days else "none"


def _stopped(name: str, head: str, reason: str) -> int:
    log.error("onchain write stopped chain=%s head=%s reason=%s", name, head, reason)
    return 1


def run_onchain_write(
    chain_root: Path, client: BrkClient, *, brk_commit: str, bitview_image: str, bitcoind_image: str, now: datetime
) -> int:
    """One writer run, ending with one summary line; the exit code: 0 complete, 1 stopped. No exception leaves it."""
    name = chain_name(brk_commit)
    root = chain_root / name
    try:
        outcome = run_write(
            chain_root, client, brk_commit=brk_commit, bitview_image=bitview_image, bitcoind_image=bitcoind_image, now=now
        )
    except CaptureError:
        log.error("another onchain writer holds %s; refusing. Read the zcrypto-onchain-write.service journal", root)
        return _stopped(name, _head(root), "lock held")
    except Exception as exc:
        return _stopped(name, _head(root), _failure(exc))
    if outcome.stopped is not None:
        return _stopped(name, _head(root), outcome.stopped)
    log.info("onchain write complete chain=%s head=%s wrote=%d base=%d", name, _head(root), len(outcome.wrote), outcome.base)
    return 0


@onchain_app.command("write")
def write_cmd(
    chain_root: Path = typer.Option(
        ..., "--chain-root", help="An existing directory; a run makes the chain's own directory in it when absent."
    ),
    bitview: str = typer.Option(
        ..., "--bitview", metavar="URL", help="The pinned BRK's address on the on-chain project's network."
    ),
    brk_commit: str = typer.Option(
        ...,
        "--brk-commit",
        metavar="SHA",
        help="The pinned BRK commit; the chain's directory is named for its first 12 characters.",
    ),
    bitview_image: str = typer.Option(
        ..., "--bitview-image", metavar="ID", help="The local image id of the running BRK container, recorded in each line written."
    ),
    bitcoind_image: str = typer.Option(
        ...,
        "--bitcoind-image",
        metavar="ID",
        help="The local image id of the running Bitcoin Core node, recorded in each line written.",
    ),
) -> None:
    """Write the base when the chain is empty and the index has reached the node's tip, else each UTC day closed by a
    later day's block and 12 blocks deep since the chain's head; exit 0 complete, 1 stopped."""
    client = BrkClient(bitview)
    code = run_onchain_write(
        chain_root, client, brk_commit=brk_commit, bitview_image=bitview_image, bitcoind_image=bitcoind_image, now=datetime.now(UTC)
    )
    raise typer.Exit(code=code)


def _as_of(chain: Path, text: str | None) -> date:
    """`--as-of`'s day; without one, the head's."""
    if text is not None:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ChainError(f"--as-of {text!r} is not a YYYY-MM-DD date") from exc
    days = line_days(chain)
    if not days:
        raise ChainError(f"{chain} holds no line")
    return days[-1]


_CHAIN_HELP = "The chain's own directory under the chain root, named for its BRK commit and generation."


@onchain_app.command("freeze")
def freeze_cmd(
    chain: Path = typer.Option(..., "--chain", resolve_path=True, help=_CHAIN_HELP),
    as_of: str = typer.Option(
        ..., "--as-of", metavar="YYYY-MM-DD", help="The day of the line to freeze the chain at; a day after its head is refused."
    ),
    out: Path = typer.Option(..., "--out", help="The snapshot's directory, which the run makes; one that exists is refused."),
) -> None:
    """Verify the chain through the as-of line, then write every day it holds through that line as one parquet and,
    last, a manifest naming the line, its BRK commit and its image ids; exit 0 written, 1 refused."""
    try:
        day = _as_of(chain, as_of)
        path = freeze(chain, day, out, written_at=datetime.now(UTC).isoformat(timespec="seconds"))
    except (ChainError, OSError) as exc:
        log.error("onchain freeze refused chain=%s reason=%s", chain.name, exc)
        raise typer.Exit(code=1) from exc
    log.info("onchain freeze complete chain=%s as_of=%s manifest=%s", chain.name, day, path)


@onchain_app.command("verify")
def verify_cmd(
    chain: Path = typer.Option(..., "--chain", resolve_path=True, help=_CHAIN_HELP),
    as_of: str | None = typer.Option(
        None, "--as-of", metavar="YYYY-MM-DD", help="The day of the line to verify the chain through; its head's when omitted."
    ),
) -> None:
    """Walk the chain from its base to the as-of line, re-hash every file each line lists, and name that line, its
    sha256 and the number of days whose lines were read; exit 0 verified, 1 refused."""
    try:
        line = verify(chain, _as_of(chain, as_of))
        days = len(walk(chain, line.day))
    except (ChainError, OSError) as exc:
        log.error("onchain verify refused chain=%s reason=%s", chain.name, exc)
        raise typer.Exit(code=1) from exc
    log.info("onchain verify complete chain=%s head=%s head_sha256=%s days=%d", chain.name, line.day, line.sha256, days)
