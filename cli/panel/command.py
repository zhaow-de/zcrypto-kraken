"""The `zcrypto panel` Typer sub-app (spec 00052 Task 3): materialize canonical book hours into the
1s L2 primitive panel via `cli.panel.materialize`.

Generation-guards `panel-meta.json` (spec 00052 D5): writes it on a fresh panel root, refuses to run
against an existing one whose generation (schema_version, grid, notionals, k_levels) differs from
this code's -- a generation change must be an explicit regeneration, never a silent mix.

Also guards the `--since`/watermark hole (Task 2 review I2): if `--since` is newer than an affected
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
from cli.panel.primitives import NOTIONALS_EUR

logger = get_logger("panel.command")

panel_app = typer.Typer(
    no_args_is_help=True,
    help="The 1s L2 primitive panel (spec 00052): materialize the canonical book archive into it.",
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
        "notionals_eur": list(NOTIONALS_EUR),
        "k_levels": list(K_LEVELS),
    }


def _check_generation(panel_root: Path) -> None:
    meta_path = panel_root / "panel-meta.json"
    if not meta_path.exists():
        write_meta(panel_root)
        return
    expected = _expected_generation()
    existing_full = json.loads(meta_path.read_text())
    existing = {key: existing_full.get(key) for key in expected}
    if existing != expected:
        raise _abort(
            f"panel materialize: {meta_path} generation differs from this code's -- "
            f"existing={existing} code={expected}. A generation change must be an explicit "
            "regeneration of the whole panel tree (spec 00052 D5), never a silent mix."
        )


def _affected_pairs(primary_root: Path, reconciled_root: Path | None, pair: Optional[str]) -> set[str]:
    if pair is not None:
        return {pair}
    return {seg_pair for seg_pair, _, _ in canonical_segments(primary_root, reconciled_root, kind="book")}


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
    pair: Optional[str] = typer.Option(None, "--pair", help="Only this pair (e.g. BTC/EUR). Defaults to every pair."),
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
) -> None:
    """Materialize canonical book hours (reconciled-first) into the 1s L2 panel (spec 00052).

    Writes `panel-meta.json` if absent; refuses if an existing one's generation differs from this
    code's. Exits non-zero iff any hour errored, mirroring `archive verify-replay`'s contract.
    """
    since_dt = _parse_since(since) if since is not None else None
    affected_pairs = _affected_pairs(primary_root, reconciled_root, pair)

    _check_generation(panel_root)
    if since_dt is not None:
        _check_since_holes(affected_pairs, panel_root, primary_root, reconciled_root, since=since_dt, allow_holes=allow_holes)

    result = materialize_hours(primary_root, reconciled_root, panel_root, pair=pair, since=since_dt, depth=depth)

    for seg_pair, hour, message in result.errors:
        logger.error("panel hour failed pair=%s hour=%s: %s", seg_pair, hour.isoformat(), message)

    logger.info(
        "panel materialize complete pairs=%d hours_written=%d hours_skipped=%d rows=%d errors=%d",
        len(affected_pairs),
        result.hours_written,
        result.hours_skipped,
        result.rows,
        len(result.errors),
    )
    if result.errors:
        raise typer.Exit(1)
