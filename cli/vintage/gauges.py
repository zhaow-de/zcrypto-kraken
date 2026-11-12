"""The recorder's `.prom`: five gauges per source, each a function of the record as the chain orders it and of the tick
just published."""

from __future__ import annotations

import gzip
import hashlib
import zlib
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from cli.logging import get_logger
from cli.vintage.chain import Chain, TickFile
from cli.vintage.derive import changed_values, parse_series
from cli.vintage.record import Published
from cli.vintage.sources import SOURCES, Source

# The evening slot plus the tick deadline: a fetch ending later reads as this, so a late start never carries the next
# day's page past that day's midnight.
LAST_OK_CAP = time(19, 57)

LAST_OK = "zcrypto_vintage_last_ok_timestamp_seconds"
OUTCOME = "zcrypto_vintage_outcome"
BODY_BYTES = "zcrypto_vintage_body_bytes"
DAYS_MISSING = "zcrypto_vintage_days_missing"
CHANGED_VALUES = "zcrypto_vintage_changed_values"
HELP = {
    LAST_OK: "Unix time a source's latest good fetch ended, read along the chain of recorded ticks and capped at 19:57 UTC of that fetch's day; 0 when it has none.",
    OUTCOME: "This tick's outcome for a source: 0 a good body, 1 not fetched, 2 a body stored that failed its check.",
    BODY_BYTES: "Raw size in bytes of the body this tick stored for a source, whatever its status; 0 when it kept none.",
    DAYS_MISSING: "UTC days from a source's first recorded tick through yesterday with no good fetch.",
    CHANGED_VALUES: "Values this tick's good body replaced, withdrew or filled in behind the newest day of the source's previous good body; new days are not counted.",
}
CHANGED_KINDS = frozenset({"fng", "cm-asset", "mempool-hashrate", "bg"})

log = get_logger("vintage.gauges")


def last_ok_value(ended_at: datetime) -> float:
    return min(ended_at, datetime.combine(ended_at.date(), LAST_OK_CAP, UTC)).timestamp()


def _fetches(manifest: dict | None) -> dict[str, dict]:
    fetches = manifest.get("fetches") if isinstance(manifest, dict) else None
    if not isinstance(fetches, list):
        return {}
    return {fetch["source"]: fetch for fetch in fetches if isinstance(fetch, dict) and isinstance(fetch.get("source"), str)}


def _outcome(fetch: dict | None) -> int | None:
    check = fetch.get("check") if isinstance(fetch, dict) else None
    outcome = check.get("outcome") if isinstance(check, dict) else None
    return outcome if isinstance(outcome, int) else None


def _ok_ended(fetch: dict | None) -> datetime | None:
    """When the fetch ended, for an ok fetch; None for any other, or one whose end does not read."""
    if _outcome(fetch) != 0:
        return None
    try:
        ended = datetime.fromisoformat(fetch["attempts"][-1]["ended_at"])
    except KeyError, IndexError, TypeError, ValueError:
        return None
    return ended.astimezone(UTC) if ended.tzinfo else None


def _last_ok_ended(order: tuple[TickFile, ...], source_id: str) -> datetime | None:
    for tick in reversed(order):
        ended = _ok_ended(_fetches(tick.manifest).get(source_id))
        if ended is not None:
            return ended
    return None


def _days_missing(order: tuple[TickFile, ...], source_id: str, today: date) -> int:
    first: date | None = None
    recorded: set[date] = set()
    for tick in order:
        fetch = _fetches(tick.manifest).get(source_id)
        if fetch is None:
            continue
        if first is None:
            first = datetime.strptime(tick.stamp[:8], "%Y%m%d").date()
        ended = _ok_ended(fetch)
        if ended is not None:
            recorded.add(ended.date())
    if first is None:
        return 0
    span = (today - first).days
    return sum(1 for offset in range(span) if first + timedelta(days=offset) not in recorded)


def _previous_ok(earlier: tuple[TickFile, ...], source_id: str) -> tuple[TickFile, str | None] | None:
    for tick in reversed(earlier):
        fetch = _fetches(tick.manifest).get(source_id)
        if _ok_ended(fetch) is not None:
            entry = fetch.get("body")
            return tick, entry.get("sha256") if isinstance(entry, dict) else None
    return None


def _changed(
    record_root: Path, earlier: tuple[TickFile, ...], source: Source, fetch: dict | None, served: bytes | None
) -> int | None:
    """The two-body reading against the source's previous ok body along the chain; None, and no line, where this
    tick's body is not ok, there is no earlier ok body, or either body does not read."""
    if _outcome(fetch) != 0 or served is None:
        return None
    previous = _previous_ok(earlier, source.id)
    if previous is None:
        return None
    tick, digest = previous
    path = tick.dir / source.file
    try:
        data = gzip.decompress(path.read_bytes())
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("the previous body does not re-hash to its entry")
        return changed_values(parse_series(source, data), parse_series(source, served))
    except (OSError, EOFError, zlib.error, ValueError) as exc:
        log.warning(
            "vintage changed values left out source=%s previous=%s: %s",
            source.id,
            path.relative_to(record_root) if path.is_relative_to(record_root) else path,
            type(exc).__name__,
        )
        return None


def _sample(family: str, source: Source, value: float) -> str:
    return f'{family}{{source="{source.id}"}} {value}'


def render_prom(record_root: Path, chain: Chain, published: Published, *, today: date) -> str:
    """The `.prom` text; `chain` is the record's chain read after `published` was."""
    fetches = _fetches(published.manifest)
    served = {exchange.source.id: exchange.body for exchange in published.exchanges}
    earlier = tuple(tick for tick in chain.order if tick.stamp != published.stamp)
    lines: dict[str, list[str]] = {family: [] for family in HELP}
    for source in SOURCES:
        fetch = fetches.get(source.id)
        ended = _last_ok_ended(chain.order, source.id)
        lines[LAST_OK].append(_sample(LAST_OK, source, 0 if ended is None else last_ok_value(ended)))
        outcome = _outcome(fetch)
        if outcome is None:
            log.warning("vintage outcome not in the published tick, written as not fetched source=%s", source.id)
            outcome = 1
        lines[OUTCOME].append(_sample(OUTCOME, source, outcome))
        stored = fetch.get("body") if isinstance(fetch, dict) else None
        lines[BODY_BYTES].append(_sample(BODY_BYTES, source, stored["bytes"] if isinstance(stored, dict) else 0))
        lines[DAYS_MISSING].append(_sample(DAYS_MISSING, source, _days_missing(chain.order, source.id, today)))
        if source.kind in CHANGED_KINDS:
            changed = _changed(record_root, earlier, source, fetch, served.get(source.id))
            if changed is not None:
                lines[CHANGED_VALUES].append(_sample(CHANGED_VALUES, source, changed))
    out = []
    for family, samples in lines.items():
        out += [f"# HELP {family} {HELP[family]}", f"# TYPE {family} gauge", *samples]
    return "\n".join(out) + "\n"
