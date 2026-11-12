"""The derivation: a record's ticks, read along the chain, as the versions each (series, day) took, the coverage each
fetch gave, and the facts a later tick teaches about an earlier one. Pure: the same ticks, generation and link entries
give the same rows."""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import polars as pl

from cli.vintage.chain import TickFile, chain, scan
from cli.vintage.fetch import header
from cli.vintage.sources import SOURCE_BY_ID, LinkAcknowledgment, Source, _date_day, _epoch_day, _iso_day, _object, _rows

DERIVE_GENERATION = 1
KINDS = ("inherited", "first_publication", "backfill", "restatement", "retraction", "restoration")
CLOCK_OFFSET_BAR_SECONDS = 10
CLOCK_FILE_STALE_SECONDS = 600
DATE_SKEW_SECONDS = 300

SERIES_KINDS = frozenset({"fng", "cm-asset", "mempool-hashrate", "bg"})
_ROW_KEYS = ("asset", "time")
_FNG_KEYS = ("value", "value_classification")
_IDENTITY_ENCODINGS = frozenset({"", "identity"})
# A body its check could not read, or read under a non-identity encoding, yields no value.
_CHECK_REFUSALS = frozenset({("*", "shape"), ("*", "encoding")})

_TIME = pl.Datetime("us", "UTC")
VERSIONS_SCHEMA: dict[str, pl.DataType] = {
    "ts": _TIME,
    "provider": pl.String(),
    "source": pl.String(),
    "series": pl.String(),
    "kind": pl.String(),
    "token": pl.String(),
    "tick": pl.String(),
    "position": pl.Int64(),
    "ended_at": _TIME,
    "knowable_at": _TIME,
    "appeared_after": _TIME,
    "outcome": pl.Int64(),
    "flags": pl.String(),
}
COVERAGE_SCHEMA: dict[str, pl.DataType] = {
    "ts": _TIME,
    "provider": pl.String(),
    "tick": pl.String(),
    "position": pl.Int64(),
    "tick_json_sha256": pl.String(),
    "source": pl.String(),
    "series": pl.String(),
    "outcome": pl.Int64(),
    "reason": pl.String(),
    "ended_at": _TIME,
    "knowable_at": _TIME,
    "first_day": pl.Date(),
    "last_day": pl.Date(),
    "days": pl.Int64(),
    "evidence": pl.Boolean(),
    "flags": pl.String(),
}
LATER_FACTS_SCHEMA: dict[str, pl.DataType] = {
    "tick": pl.String(),
    "fact": pl.String(),
    "taught_by": pl.String(),
    "taught_position": pl.Int64(),
}


class DeriveError(Exception):
    """The record cannot be derived as it stands: a damaged tick, a body that does not re-hash, an unknown source."""


def _loads(text: str) -> object:
    return json.loads(text, parse_int=str, parse_float=str)


def _series(source: Source, key: str) -> str:
    match source.kind:
        case "cm-asset":
            return f"cm/{source.asset}/{key}"
        case "fng":
            return f"fng/{key}"
        case "mempool-hashrate":
            return f"mempool/{key}"
        case "bg":
            return f"bg/{source.id.removeprefix('bg-')}"
    raise ValueError(f"{source.id} carries no series")


def _cells(source: Source, text: str) -> Iterator[tuple[str, date, object]]:
    """Each (series, day, value) the body holds, the day read from the row's own time key, never from token text. The
    rows and days are read by the check's own readers, so this refuses every row the check refuses."""
    match source.kind:
        case "cm-asset":
            for line in [line for line in text.split("\n") if line.strip()]:
                row = _loads(line)
                if not isinstance(row, dict) or "asset" not in row or "time" not in row:
                    raise ValueError("a line is not an object with asset and time")
                day = _iso_day(row["time"])
                for key, value in row.items():
                    if key in _ROW_KEYS:
                        continue
                    yield _series(source, key), day, value
        case "fng":
            for row in _rows(_object(_loads(text)).get("data"), "data", ("value", "timestamp")):
                day = _epoch_day(row["timestamp"])
                for key in _FNG_KEYS:
                    yield _series(source, key), day, row.get(key)
        case "mempool-hashrate":
            for row in _rows(_object(_loads(text)).get("hashrates"), "hashrates", ("timestamp",)):
                yield _series(source, "avgHashrate"), _epoch_day(row["timestamp"]), row.get("avgHashrate")
        case "bg":
            for row in _rows(_loads(text), "body", ("d", "unixTs", source.value_key)):
                yield _series(source, source.value_key), _date_day(row["d"]), row[source.value_key]
        case _:
            raise ValueError(f"{source.id} carries no series")


def parse_series(source: Source, body: bytes) -> dict[str, dict[date, str]]:
    """Every series the body carries, day by day, each token the value's text as served; a null value is no value,
    and a key whose value in any row is an object or an array is no series. ValueError for a body it cannot read."""
    found: dict[str, dict[date, str]] = {}
    nested: set[str] = set()
    try:
        for series, day, value in _cells(source, body.decode("utf-8")):
            if isinstance(value, (dict, list)):
                nested.add(series)
            elif value is not None:
                found.setdefault(series, {})[day] = value if isinstance(value, str) else json.dumps(value)
    except (KeyError, TypeError, AttributeError, OverflowError, OSError, RecursionError) as exc:
        raise ValueError(f"{source.id} body unreadable: {type(exc).__name__}") from exc
    return {series: days for series, days in found.items() if series not in nested}


def _server_date(headers: list) -> datetime | None:
    value = header(headers, "Date")
    if value is None:
        return None
    try:
        moment = parsedate_to_datetime(value)
    except TypeError, ValueError, IndexError, OverflowError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def knowable_at(ended_at: datetime, headers: list[tuple[str, str]]) -> datetime:
    server_date = _server_date(headers)
    if server_date is None:
        return ended_at
    return max(ended_at, server_date + timedelta(seconds=1))


def _ended_at(fetch: dict) -> datetime | None:
    attempts = fetch.get("attempts") or []
    return datetime.fromisoformat(attempts[-1]["ended_at"]) if attempts else None


def flags(manifest: dict, fetch: dict) -> tuple[str, ...]:
    """The clock evidence on one fetch: its tick's clock block, and its `ended_at` against the server's Date."""
    clock = manifest.get("clock") or {}
    found = []
    if clock.get("synchronised") != 1:
        found.append("clock-unsynchronised")
    offset = clock.get("offset_seconds")
    if offset is None or abs(offset) > CLOCK_OFFSET_BAR_SECONDS:
        found.append("clock-offset")
    age = clock.get("prom_age_seconds")
    if age is None or age > CLOCK_FILE_STALE_SECONDS:
        found.append("clock-file-stale")
    ended_at, server_date = _ended_at(fetch), _server_date(fetch.get("headers") or [])
    if ended_at is not None and server_date is not None and abs((ended_at - server_date).total_seconds()) > DATE_SKEW_SECONDS:
        found.append("date-skew")
    return tuple(sorted(found))


@dataclass
class SeriesState:
    high_water: date | None = None
    carried: bool = False
    # The observations whose absences are evidence for the series, as (ended_at, first day held), oldest first, each
    # kept only while no later one's range starts at or before its own: the newest whose range starts at or before a
    # day is the last that was evidence the day was not yet held, there or after its newest day.
    evidence: list[tuple[datetime, date]] = field(default_factory=list)


@dataclass
class Held:
    token: str
    retracted: bool = False
    # The `ended_at` of the last observation that held the day, whatever its check: the values a body holds are
    # evidence even where its absences are not.
    seen_at: datetime | None = None


def _with_evidence(evidence: list[tuple[datetime, date]], ended_at: datetime, first_day: date) -> list[tuple[datetime, date]]:
    return [entry for entry in evidence if entry[1] < first_day] + [(ended_at, first_day)]


def _lower_end(series_state: SeriesState, last: Held | None, day: date) -> datetime | None:
    """Q3's lower end for a version of (series, day) first seen now: the last earlier observation that held the day,
    or that was evidence the day was not yet held, whichever is later."""
    held = None if last is None else last.seen_at
    absent = next((ended for ended, first in reversed(series_state.evidence) if first <= day), None)
    return max((moment for moment in (held, absent) if moment is not None), default=None)


@dataclass
class DeriveState:
    series: dict[str, SeriesState] = field(default_factory=dict)
    # Per (series, day), the last non-null token and whether it stands retracted.
    days: dict[str, dict[date, Held]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> DeriveState:
        return cls()


@dataclass(frozen=True)
class _Observed:
    """One fetch's place in the record: the fields its version and coverage rows share."""

    ts: datetime
    source: Source
    tick: str
    position: int
    tick_json_sha256: str | None
    outcome: int
    reason: str | None
    ended_at: datetime | None
    knowable_at: datetime | None
    flags: str


def _metric(series: str) -> str:
    """The metric a check names for a series: a `<metric>-status` or `<metric>-status-time` companion takes its own."""
    return series.rsplit("/", 1)[-1].removesuffix("-status-time").removesuffix("-status")


def _evidence(check: dict, metric: str) -> bool:
    """Whether a body's absences are evidence for a series: not where its check names the metric, or `*`."""
    named = set(check["metrics_absent"])
    named |= {failure[0] for failure in check["metrics_failed"]}
    return "*" not in named and metric not in named


def _kind(last: Held | None, token: str, day: date, high: date | None) -> str | None:
    if last is None:
        return "first_publication" if high is None or day > high else "backfill"
    if token != last.token:
        return "restatement"
    if last.retracted:
        return "restoration"
    return None


def _version(observed: _Observed, series: str, day: date, kind: str, token: str | None, appeared_after: datetime | None) -> dict:
    return {
        "ts": datetime.combine(day, time(), UTC),
        "provider": observed.source.provider,
        "source": observed.source.id,
        "series": series,
        "kind": kind,
        "token": token,
        "tick": observed.tick,
        "position": observed.position,
        "ended_at": observed.ended_at,
        "knowable_at": observed.knowable_at,
        "appeared_after": appeared_after,
        "outcome": observed.outcome,
        "flags": observed.flags,
    }


def _coverage(
    observed: _Observed, series: str, first_day: date | None, last_day: date | None, days: int | None, is_evidence: bool
) -> dict:
    return {
        "ts": observed.ts,
        "provider": observed.source.provider,
        "tick": observed.tick,
        "position": observed.position,
        "tick_json_sha256": observed.tick_json_sha256,
        "source": observed.source.id,
        "series": series,
        "outcome": observed.outcome,
        "reason": observed.reason,
        "ended_at": observed.ended_at,
        "knowable_at": observed.knowable_at,
        "first_day": first_day,
        "last_day": last_day,
        "days": days,
        "evidence": is_evidence,
        "flags": observed.flags,
    }


def _no_observation(observed: _Observed) -> dict:
    return _coverage(observed, "*", None, None, None, False)


def _observe(
    state: DeriveState, observed: _Observed, parsed: dict[str, dict[date, str]], check: dict
) -> tuple[list[dict], list[dict]]:
    """The versions and coverage rows one observation adds, each token judged against the last non-null token seen for
    its (series, day) and the series' high-water day; `state` moves past the observation."""
    versions: list[dict] = []
    coverage: list[dict] = []
    for series, tokens in sorted(parsed.items()):
        series_state = state.series.setdefault(series, SeriesState())
        held = state.days.setdefault(series, {})
        is_evidence = _evidence(check, _metric(series))
        first_day, last_day = min(tokens), max(tokens)
        if not series_state.carried:
            for day, token in sorted(tokens.items()):
                versions.append(_version(observed, series, day, "inherited", token, None))
                held[day] = Held(token, seen_at=observed.ended_at)
        else:
            high = series_state.high_water
            for day, token in sorted(tokens.items()):
                last = held.get(day)
                kind = _kind(last, token, day, high)
                if kind is not None:
                    appeared_after = _lower_end(series_state, last, day)
                    versions.append(_version(observed, series, day, kind, token, appeared_after))
                    held[day] = Held(token)
                held[day].seen_at = observed.ended_at
            if is_evidence:
                for day, last in sorted(held.items()):
                    if not last.retracted and day not in tokens and first_day <= day <= last_day:
                        appeared_after = _lower_end(series_state, last, day)
                        versions.append(_version(observed, series, day, "retraction", None, appeared_after))
                        held[day] = Held(last.token, retracted=True, seen_at=last.seen_at)
        series_state.carried = True
        series_state.high_water = max(last_day, series_state.high_water or last_day)
        series_state.evidence = (
            _with_evidence(series_state.evidence, observed.ended_at, first_day) if is_evidence else series_state.evidence
        )
        coverage.append(_coverage(observed, series, first_day, last_day, len(tokens), is_evidence))
    return versions, coverage


def _is_observation(fetch: dict) -> bool:
    return fetch.get("status") == 200 and fetch.get("body") is not None and fetch["check"]["outcome"] in (0, 2)


def _body(tick_dir: Path, fetch: dict) -> bytes:
    entry = fetch["body"]
    try:
        data = gzip.decompress((tick_dir / entry["file"]).read_bytes())
    except (OSError, EOFError, zlib.error) as exc:
        raise DeriveError(f"body unreadable file={tick_dir / entry['file']}: {type(exc).__name__}") from exc
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise DeriveError(f"body does not re-hash to its entry file={tick_dir / entry['file']}")
    return data


def _parse(source: Source, fetch: dict, data: bytes) -> dict[str, dict[date, str]]:
    if _CHECK_REFUSALS & {tuple(failure) for failure in fetch["check"]["metrics_failed"]}:
        raise ValueError(f"{source.id} body refused by its check")
    encoding = header(fetch.get("headers") or [], "Content-Encoding")
    if encoding is not None and encoding.strip().lower() not in _IDENTITY_ENCODINGS:
        raise ValueError(f"{source.id} body not in identity encoding")
    return parse_series(source, data)


def _facts(stamp: str, position: int, prev: object, regression: bool, entries: tuple[LinkAcknowledgment, ...]) -> list[dict]:
    if not isinstance(prev, dict):
        return []
    taught = []
    if regression:
        taught.append("regression-predecessor")
    if prev.get("error") is not None:
        taught.append("link-error")
    if any(entry.successor == stamp for entry in entries):
        taught.append("link-acknowledged")
    return [{"tick": prev["tick"], "fact": fact, "taught_by": stamp, "taught_position": position} for fact in taught]


def derive_tick(
    state: DeriveState,
    tick: TickFile,
    position: int,
    *,
    tick_dir: Path,
    regression: bool,
    entries: tuple[LinkAcknowledgment, ...] = (),
) -> tuple[list[dict], list[dict], list[dict]]:
    """The tick's version rows, coverage rows and later facts, `state` moved past it. A body that cannot be parsed adds
    no version and one coverage row with series `*`, never stopping the derive."""
    manifest = tick.manifest
    if manifest is None:
        raise DeriveError(f"tick.json unreadable tick={tick.stamp}: {tick.error}")
    prev = manifest.get("prev")
    started = datetime.fromisoformat(manifest["started_at"])
    versions: list[dict] = []
    coverage: list[dict] = []
    for fetch in manifest["fetches"]:
        source = SOURCE_BY_ID.get(fetch.get("source"))
        if source is None:
            raise DeriveError(f"a fetch names no known source tick={tick.stamp} source={fetch.get('source')}")
        if source.kind not in SERIES_KINDS:
            continue
        ended_at = _ended_at(fetch)
        found = {*flags(manifest, fetch), *(("stamp-regression",) if regression else ())}
        observed = _Observed(
            ts=started,
            source=source,
            tick=tick.stamp,
            position=position,
            tick_json_sha256=tick.sha256,
            outcome=fetch["check"]["outcome"],
            reason=fetch["check"]["reason"],
            ended_at=ended_at,
            knowable_at=None if ended_at is None else knowable_at(ended_at, fetch.get("headers") or []),
            flags=",".join(sorted(found)),
        )
        if not _is_observation(fetch):
            coverage.append(_no_observation(observed))
            continue
        try:
            parsed = _parse(source, fetch, _body(tick_dir, fetch))
        except ValueError:
            coverage.append(_no_observation(observed))
            continue
        found_versions, found_coverage = _observe(state, observed, parsed, fetch["check"])
        versions += found_versions
        coverage += found_coverage
    return versions, coverage, _facts(tick.stamp, position, prev, regression, entries)


def frames(versions: list[dict], coverage: list[dict], facts: list[dict]) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    return (
        pl.DataFrame(versions, schema=VERSIONS_SCHEMA).sort(["ts", "source", "series"], maintain_order=True),
        pl.DataFrame(coverage, schema=COVERAGE_SCHEMA).sort(["source", "series"], maintain_order=True),
        pl.DataFrame(facts, schema=LATER_FACTS_SCHEMA),
    )


def derive_record(
    record_root: Path, *, entries: tuple[LinkAcknowledgment, ...] = ()
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Every tick on the record's chain, from genesis, derived in chain order."""
    scanned = scan(record_root)
    if scanned.unreadable:
        named = " ".join(f"{path} ({reason})" for path, reason in scanned.unreadable)
        raise DeriveError(f"record paths unreadable, the record read as damaged: {named}")
    order = chain(scanned.ticks).order
    state = DeriveState.empty()
    versions: list[dict] = []
    coverage: list[dict] = []
    facts: list[dict] = []
    for position, tick in enumerate(order):
        regression = position > 0 and tick.stamp <= order[position - 1].stamp
        found = derive_tick(state, tick, position, tick_dir=tick.dir, regression=regression, entries=entries)
        versions += found[0]
        coverage += found[1]
        facts += found[2]
    return frames(versions, coverage, facts)


def changed_values(prev: dict[str, dict[date, str]], new: dict[str, dict[date, str]]) -> int:
    """The two-body reading between consecutive ok bodies, per series both carry: each day both hold with different
    tokens, each day `prev` holds that lies inside `new`'s range and `new` does not hold, and each day `new` holds at
    or before `prev`'s newest day that `prev` does not hold."""
    count = 0
    for series, now in new.items():
        before = prev.get(series)
        if not before:
            continue
        newest_before = max(before)
        first, last = min(now), max(now)
        for day, token in now.items():
            if day in before:
                count += token != before[day]
            elif day <= newest_before:
                count += 1
        count += sum(1 for day in before if day not in now and first <= day <= last)
    return count
