"""The `zcrypto panel` Typer sub-app (spec 00052 Task 3): materialize canonical book hours into the
1s L2 primitive panel via `cli.panel.materialize`.

Generation-guards `panel-meta.json` (spec 00052 D5): writes it on a fresh panel root, refuses to run
against an existing one whose generation (schema_version, grid, notionals, k_levels) differs from
this code's -- a generation change must be an explicit regeneration, never a silent mix.

Also guards the `--since`/watermark hole (a review finding): if `--since` is newer than an affected
pair's current panel watermark, the sweep would skip `[watermark+1h, since)` forever once later hours
are written -- refused by default, proceed only with `--allow-holes`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer

from cli.archive.reader import canonical_segments
from cli.logging import get_logger
from cli.panel.materialize import K_LEVELS, SCHEMA_VERSION, panel_watermark, write_meta
from cli.panel.materialize import materialize as materialize_hours
from cli.panel.primitives import NOTIONALS_BY_QUOTE

logger = get_logger("panel.command")

panel_app = typer.Typer(
    no_args_is_help=True,
    help="The 1s L2 primitive panel: materialize the canonical book archive into it.",
)


def _abort(message: str) -> typer.Exit:
    """A clean one-line error (logged, no traceback) + exit code 1. Usage: `raise _abort(...)`."""
    logger.error(message)
    return typer.Exit(code=1)


def _parse_since(raw: str) -> datetime:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"--since {raw!r} is not a YYYY-MM-DD date or an ISO-8601 hour") from exc
    parsed = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise typer.BadParameter(f"--since {raw!r} is not on an hour boundary")
    return parsed


def _expected_generation() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "grid": "1s",
        "notionals_by_quote": {q: list(v) for q, v in sorted(NOTIONALS_BY_QUOTE.items())},
        "k_levels": list(K_LEVELS),
    }


def _check_generation(panel_root: Path) -> None:
    meta_path = panel_root / "panel-meta.json"
    if not meta_path.exists():
        # An absent meta means "fresh tree" ONLY if the tree is actually fresh. Deleting the meta
        # alone -- the obvious reading of the abort below, and the cheapest-looking way past it --
        # would otherwise mint a new-generation manifest over old-generation hours, and every later
        # run would read that manifest and pass. Nothing downstream can detect the mix: this check
        # sees only the manifest, and the watermarked sweep never revisits an hour it has written.
        stranded = next(panel_root.glob("*/*/panel-1s/*/*/*/*.parquet"), None)
        if stranded is not None:
            raise _abort(
                f"panel materialize: {meta_path} is missing but the tree already holds hours "
                f"(e.g. {stranded}). Deleting the manifest alone does not regenerate anything -- it "
                f"would stamp this code's generation onto hours written by another one. Either "
                f"restore the manifest (the NAS mirror carries a copy), or delete the whole tree on "
                f"BOTH this host and the NAS -- the archive pull is `rsync -a` with no --delete, so "
                f"deleting only one side leaves the other's hours to be pulled back alongside."
            )
        write_meta(panel_root)
        return
    # A matching manifest is not enough: the sweep only covers quotes with an entry in
    # `NOTIONALS_BY_QUOTE`, so hours for a quote outside that ladder are never revisited and stay at
    # whatever generation wrote them. The manifest then asserts a generation the tree does not have,
    # and a whole-tree read raises SchemaError on files nobody remembers exist. No sweep can repair
    # it -- only deleting them can.
    stray = next(
        (h for h in panel_root.glob("*/*/panel-1s/*/*/*/*.parquet") if h.parts[-6] not in NOTIONALS_BY_QUOTE),
        None,
    )
    if stray is not None:
        raise _abort(
            f"panel materialize: the tree holds hours outside the ladder-scoped sweep this run "
            f"covers (e.g. {stray}), so they can never be regenerated and the manifest would "
            f"describe a generation they do not share. Delete them on BOTH this host and the NAS."
        )
    expected = _expected_generation()
    existing_full = json.loads(meta_path.read_text())
    existing = {key: existing_full.get(key) for key in expected}
    if existing != expected:
        raise _abort(
            f"panel materialize: {meta_path} generation differs from this code's -- "
            f"existing={existing} code={expected}. A generation change must be an explicit "
            # spec 00052 D5: whole-tree regeneration on a generation change.
            "regeneration of the whole panel tree, never a silent mix."
        )


def _affected_pairs(primary_root: Path, reconciled_root: Path | None, pair: Optional[str]) -> set[str]:
    if pair is not None:
        return {pair}
    # Ladder-quoted only, matching the sweep's own scope (NOTIONALS_BY_QUOTE) -- otherwise the
    # completion line would report pairs=N counting pairs the sweep never processes.
    return {
        seg_pair
        for seg_pair, _, _ in canonical_segments(primary_root, reconciled_root, kind="book")
        if seg_pair.split("/")[-1] in NOTIONALS_BY_QUOTE
    }


def _check_since_holes(
    affected_pairs: set[str],
    panel_root: Path,
    primary_root: Path,
    reconciled_root: Path | None,
    *,
    since: datetime,
    allow_holes: bool,
) -> None:
    # Fresh pairs (review I-1): a pair with NO panel yet has no watermark for `since` to be "newer
    # than", but a --since above its EARLIEST canonical hour strands the earlier hours just as
    # permanently (the sweep's since-filter drops them before they are even counted as skipped).
    # The earliest canonical hour stands in for the missing watermark. One extra archive
    # enumeration, paid only on --since runs (manual), never by the hourly timer.
    earliest: dict[str, datetime] = {}
    for seg_pair, seg_hour, _ in canonical_segments(primary_root, reconciled_root, kind="book"):
        if seg_pair in affected_pairs and (seg_pair not in earliest or seg_hour < earliest[seg_pair]):
            earliest[seg_pair] = seg_hour
    holes: list[tuple[str, datetime, datetime]] = []
    for seg_pair in sorted(affected_pairs):
        watermark = panel_watermark(panel_root, seg_pair)
        if watermark is None:
            first = earliest.get(seg_pair)
            if first is not None and since > first:
                holes.append((seg_pair, first, first))
            continue
        hole_start = watermark + timedelta(hours=1)
        if since > hole_start:
            holes.append((seg_pair, watermark, hole_start))
    if not holes:
        return
    for seg_pair, watermark, hole_start in holes:
        logger.warning(
            "panel materialize: --since %s is newer than %s's panel watermark / earliest canonical "
            "hour %s -- without --allow-holes this permanently skips [%s, %s)",
            since.isoformat(),
            seg_pair,
            watermark.isoformat(),
            hole_start.isoformat(),
            since.isoformat(),
        )
    if not allow_holes:
        raise _abort(
            f"panel materialize: --since {since.isoformat()} is newer than the panel watermark for "
            f"{len(holes)} pair(s) -- this would open a permanent hole. Pass --allow-holes to proceed anyway."
        )


@panel_app.command()
def materialize(
    primary_root: Path = typer.Argument(..., exists=True, file_okay=False, help="The primary (raw) canonical book archive."),
    reconciled_root: Optional[Path] = typer.Argument(
        None, help="The healed overlay; its hours materialize reconciled-first. Omit to use the primary alone."
    ),
    panel_root: Path = typer.Option(..., "--panel-root", help="The panel tree root to write into."),
    pair: Optional[str] = typer.Option(
        None,
        "--pair",
        help=f"Only this pair (e.g. BTC/EUR); its quote must have a notional ladder ({', '.join(NOTIONALS_BY_QUOTE)}). "
        "Defaults to every pair whose quote has one.",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only hours at/after this UTC boundary: a YYYY-MM-DD date or an ISO-8601 hour (e.g. 2026-07-16T09).",
    ),
    depth: int = typer.Option(100, "--depth", help="Book depth the archive was captured at (capture's default 100)."),
    allow_holes: bool = typer.Option(
        False,
        "--allow-holes",
        help="Proceed even if --since is newer than a pair's panel watermark, permanently skipping the hole in between.",
    ),
    settle_hours: float = typer.Option(
        7.0,
        "--settle-hours",
        help="Defer hours newer than this many hours: a heal-settle margin so an hour is only "
        "materialized once the reconciler has finished healing it (its max mint is 6h after the "
        "hour). Default 7h.",
    ),
) -> None:
    """Materialize canonical book hours (reconciled-first) into the 1s L2 panel.

    Writes `panel-meta.json` if absent; refuses if an existing one's generation differs from this
    code's. Exits non-zero iff any hour errored, mirroring `archive verify-replay`'s contract.
    """
    if pair is not None and pair.count("/") != 1:
        raise typer.BadParameter(f"--pair {pair}: expected BASE/QUOTE (e.g. BTC/EUR)")
    if pair is not None and pair.split("/")[-1] not in NOTIONALS_BY_QUOTE:
        # Refuse loudly: the sweep would skip it, so proceeding would exit 0 having done nothing. (T0092)
        raise typer.BadParameter(f"--pair {pair}: its quote has no notional ladder ({', '.join(NOTIONALS_BY_QUOTE)})")

    since_dt = _parse_since(since) if since is not None else None
    affected_pairs = _affected_pairs(primary_root, reconciled_root, pair)

    _check_generation(panel_root)
    if since_dt is not None:
        _check_since_holes(affected_pairs, panel_root, primary_root, reconciled_root, since=since_dt, allow_holes=allow_holes)

    result = materialize_hours(
        primary_root, reconciled_root, panel_root, pair=pair, since=since_dt, depth=depth, settle=timedelta(hours=settle_hours)
    )

    for seg_pair, hour, message in result.errors:
        logger.error("panel hour failed pair=%s hour=%s: %s", seg_pair, hour.isoformat(), message)

    logger.info(
        "panel materialize complete pairs=%d pairs_out_of_scope=%d hours_written=%d hours_skipped=%d hours_unsettled=%d hours_unanchored=%d rows=%d errors=%d",
        len(affected_pairs),
        result.pairs_out_of_scope,
        result.hours_written,
        result.hours_skipped,
        result.hours_unsettled,
        result.hours_unanchored,
        result.rows,
        len(result.errors),
    )
    if result.errors:
        raise typer.Exit(1)
