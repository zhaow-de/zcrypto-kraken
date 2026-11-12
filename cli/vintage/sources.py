"""The vintage recorder's fetch table, pinned for ever per source id, and the lenient check that grades each body it
fetches: 0 ok, 2 a body stored but failing its check; a body never makes the check raise, and the check never
gates storage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    file: str
    provider: str
    host: str
    kind: str
    keyed: bool
    value_key: str | None
    asset: str | None


@dataclass(frozen=True)
class Acknowledgment:
    source: str
    metric: str
    rule: str
    since: str


@dataclass(frozen=True)
class LinkAcknowledgment:
    """A link whose successor's `prev` records `recorded_prev_sha256` while its restored predecessor hashes to
    `witnessed_sha256`."""

    successor: str
    recorded_prev_sha256: str
    witnessed_sha256: str


@dataclass(frozen=True)
class ForkAcknowledgment:
    """A fork's tick off the chain, by its stamp and the sha256 pinned for its `tick.json`; `lost` marks that no copy
    holds that tick any more."""

    off_chain: str
    tick_json_sha256: str
    lost: bool = False


# A new link entry ships with a new derive generation; a fork entry ships with none, since no derive reads it.
LINK_ACKNOWLEDGMENTS: tuple[LinkAcknowledgment, ...] = ()
FORK_ACKNOWLEDGMENTS: tuple[ForkAcknowledgment, ...] = ()

COMPARISON_RULES = frozenset({"collapse", "top", "bottom"})

# Every daily metric the community catalog listed per asset, in the catalog's ASCII order.
ASSET_METRICS: dict[str, tuple[str, ...]] = {
    "btc": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv FlowInExNtv FlowInExUSD FlowOutExNtv FlowOutExUSD HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExNtv SplyExUSD SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "eth": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv FlowInExNtv FlowInExUSD FlowOutExNtv FlowOutExUSD HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateEUR ReferenceRateUSD SplyCur SplyExNtv SplyExUSD SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "doge": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "ltc": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "ada": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "xrp": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "link": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime CapMVRVCur CapMrktCurUSD CapMrktEstUSD IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "dot": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime CapMVRVCur CapMrktCurUSD CapMrktEstUSD IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur TxCnt TxTfrCnt volume_reported_spot_usd_1d".split()
    ),
    "avaxc": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD FeeTotNtv IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d SplyCur TxCnt TxTfrCnt".split()
    ),
    "avaxp": tuple(
        "AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD FeeTotNtv IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d SplyCur TxCnt TxTfrCnt".split()
    ),
}

GENESIS = "00000000T000000Z"
FRESHNESS_DAYS = 3
LABS_ASSETS = ("avaxc", "avaxp")
LABS_FRESHNESS_DAYS = 30
LABS_NEWEST_DAYS = LABS_FRESHNESS_DAYS
NEWEST_DAYS = {"fng": 1, "cm-asset": 1, "mempool-hashrate": 3, "bg": 9}
COLLAPSE_FLOOR = 0.9
DOT_STOPPED = (
    "AdrActCnt",
    "AdrBalCnt",
    "CapMVRVCur",
    "CapMrktCurUSD",
    "IssTotNtv",
    "IssTotUSD",
    "SplyCur",
    "TxCnt",
    "TxTfrCnt",
    "PriceBTC",
    "ROI1yr",
    "ROI30d",
)
ETH_STOPPED = ("HashRate", "SplyExpFut10yr")
CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets={asset}&metrics={metrics}&frequency=1d&format=json_stream&ignore_forbidden_errors=true&ignore_unsupported_errors=true"
ACKNOWLEDGMENTS = (
    *(Acknowledgment("cm-dot", metric, "freshness", GENESIS) for metric in DOT_STOPPED),
    *(Acknowledgment("cm-eth", metric, "freshness", GENESIS) for metric in ETH_STOPPED),
    *(
        Acknowledgment(f"cm-{asset}", metric, "bottom", GENESIS)
        for asset, metrics in ASSET_METRICS.items()
        for metric in metrics
        if metric.startswith("ReferenceRate")
    ),
)

FULL_HISTORY_KINDS = frozenset({"fng", "cm-asset", "mempool-hashrate", "bg"})
_IDENTITY_ENCODINGS = frozenset({"", "identity"})


def _source(
    source_id: str, url: str, file: str, provider: str, kind: str, *, value_key: str | None = None, asset: str | None = None
) -> Source:
    return Source(source_id, url, file, provider, urlsplit(url).hostname or "", kind, kind == "bg", value_key, asset)


def _bg(metric: str, value_key: str) -> Source:
    return _source(
        f"bg-{metric}",
        f"https://api.bitcoin-data.com/v1/{metric}",
        f"bg-{metric}.json.gz",
        "bgeometrics",
        "bg",
        value_key=value_key,
    )


def _cm(asset: str) -> Source:
    url = CM_URL.format(asset=asset, metrics=",".join(ASSET_METRICS[asset]))
    return _source(f"cm-{asset}", url, f"cm-{asset}.jsonl.gz", "coinmetrics", "cm-asset", asset=asset)


# Tick order: the keyed host first, then the hosts serving one request each, then community-api.coinmetrics.io, whose
# requests can together reach the tick deadline; on that host the assets before the catalog.
SOURCES: tuple[Source, ...] = (
    _bg("sopr", "sopr"),
    _bg("asopr", "asopr"),
    _bg("sth-sopr", "sthSopr"),
    _bg("lth-sopr", "lthSopr"),
    _source("fng", "https://api.alternative.me/fng/?limit=0", "fng.json.gz", "alternative.me", "fng"),
    _source("cm-status", "https://status.coinmetrics.io/history.atom", "cm-status.atom.gz", "coinmetrics", "cm-status"),
    _source(
        "mempool-hashrate",
        "https://mempool.space/api/v1/mining/hashrate/all",
        "mempool-hashrate.json.gz",
        "mempool.space",
        "mempool-hashrate",
    ),
    *(_cm(asset) for asset in ("btc", "eth", "xrp", "ada", "link", "doge", "ltc", "dot", "avaxc", "avaxp")),
    _source(
        "cm-catalog",
        "https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics?assets=btc,eth,sol,xrp,ada,link,doge,ltc,dot,avax,avaxc,avaxp&page_size=2000",
        "cm-catalog.json.gz",
        "coinmetrics",
        "cm-catalog",
    ),
)
SOURCE_BY_ID: dict[str, Source] = {source.id: source for source in SOURCES}


@dataclass(frozen=True)
class BodySummary:
    rows: int
    newest: date | None
    metric_newest: dict[str, date]
    metric_oldest: dict[str, date]


@dataclass(frozen=True)
class Check:
    outcome: int
    reason: str | None
    newest_day: date | None
    rows: int | None
    metrics_absent: tuple[str, ...]
    metrics_failed: tuple[tuple[str, str], ...]
    acknowledged: tuple[Acknowledgment, ...]
    summary: BodySummary | None


class _Unreadable(ValueError):
    """A body the check cannot read; its message is the check's own text and never carries a byte of the body."""


def _json(data: bytes) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _Unreadable("not UTF-8") from None
    try:
        return json.loads(text, parse_int=str, parse_float=str)
    except json.JSONDecodeError:
        raise _Unreadable("not JSON") from None


def as_object(doc: object) -> dict:
    if not isinstance(doc, dict):
        raise _Unreadable("not a JSON object")
    return doc


def rows(value: object, what: str, keys: tuple[str, ...]) -> list[dict]:
    if not isinstance(value, list):
        raise _Unreadable(f"{what} is not a list")
    for row in value:
        if not isinstance(row, dict):
            raise _Unreadable(f"a {what} row is not an object")
        for key in keys:
            if key not in row:
                raise _Unreadable(f"a {what} row lacks {key}")
    return value


def iso_day(token: object) -> date:
    if not isinstance(token, str):
        raise _Unreadable("a time is not a string")
    try:
        moment = datetime.fromisoformat(token)
    except ValueError:
        raise _Unreadable("a time is not an ISO time") from None
    return (moment.astimezone(UTC) if moment.tzinfo else moment).date()


def epoch_day(token: object) -> date:
    if not (isinstance(token, str) and token.isascii() and token.isdigit()):
        raise _Unreadable("a timestamp is not epoch seconds")
    try:
        return datetime.fromtimestamp(int(token), UTC).date()
    except OverflowError, OSError, ValueError:
        raise _Unreadable("a timestamp is out of range") from None


def date_day(token: object) -> date:
    if not isinstance(token, str):
        raise _Unreadable("a d is not a string")
    try:
        return date.fromisoformat(token)
    except ValueError:
        raise _Unreadable("a d is not a date") from None


def summarise(source: Source, body: bytes) -> BodySummary:
    return _read(source, body)[0]


def _read(source: Source, body: bytes) -> tuple[BodySummary, bool]:
    """The body's summary and whether it is a catalog page with a next one."""
    try:
        return _read_kind(source, body)
    except _Unreadable:
        raise
    except (ValueError, LookupError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise _Unreadable("an unexpected structure") from exc


def _read_kind(source: Source, body: bytes) -> tuple[BodySummary, bool]:
    match source.kind:
        case "fng":
            doc = as_object(_json(body))
            metadata = doc.get("metadata")
            metadata = as_object({} if metadata is None else metadata)
            if metadata.get("error") is not None:
                raise _Unreadable("metadata.error is set")
            records = rows(doc.get("data"), "data", ("value", "timestamp"))
            return BodySummary(len(records), max((epoch_day(r["timestamp"]) for r in records), default=None), {}, {}), False
        case "cm-asset":
            return _read_cm_asset(ASSET_METRICS[source.asset], body), False
        case "cm-catalog":
            doc = as_object(_json(body))
            data = doc.get("data")
            if not isinstance(data, list) or not data:
                raise _Unreadable("data is not a non-empty list")
            return BodySummary(len(data), None, {}, {}), "next_page_url" in doc
        case "cm-status":
            if not body.lstrip().startswith((b"<?xml", b"<feed")):
                raise _Unreadable("no XML or feed prolog")
            entries = body.count(b"<entry")
            if not entries:
                raise _Unreadable("no entry")
            return BodySummary(entries, None, {}, {}), False
        case "mempool-hashrate":
            records = rows(as_object(_json(body)).get("hashrates"), "hashrates", ("timestamp",))
            if not records:
                raise _Unreadable("hashrates is empty")
            return BodySummary(len(records), max(epoch_day(r["timestamp"]) for r in records), {}, {}), False
        case "bg":
            records = rows(_json(body), "body", ("d", "unixTs", source.value_key))
            if not records:
                raise _Unreadable("the body is empty")
            days = [date_day(r["d"]) for r in records]
            # One series per body, so its days are the source's own: its failures are source-level.
            return BodySummary(len(records), max(days), {"*": max(days)}, {"*": min(days)}), False
    raise _Unreadable(f"no reader for kind {source.kind}")


def _read_cm_asset(pinned: tuple[str, ...], body: bytes) -> BodySummary:
    rows, newest = 0, None
    metric_newest: dict[str, date] = {}
    metric_oldest: dict[str, date] = {}
    for line in body.split(b"\n"):
        if not line.strip():
            continue
        row = _json(line)
        if not isinstance(row, dict) or "asset" not in row or "time" not in row:
            raise _Unreadable("a line is not an object with asset and time")
        day = iso_day(row["time"])
        rows += 1
        newest = day if newest is None else max(newest, day)
        for metric in pinned:
            if row.get(metric) is not None:
                metric_newest[metric] = max(day, metric_newest.get(metric, day))
                metric_oldest[metric] = min(day, metric_oldest.get(metric, day))
    return BodySummary(rows, newest, metric_newest, metric_oldest)


def _tick_date(tick: str) -> date:
    return datetime.strptime(tick, "%Y%m%dT%H%M%SZ").date()


def _waives(ack: Acknowledgment, tick: str, last_ok_tick: str | None) -> bool:
    if tick < ack.since:
        return False
    if ack.since != GENESIS and ack.rule in COMPARISON_RULES:
        return last_ok_tick is None or last_ok_tick < ack.since
    return True


def _newest_days(source: Source) -> int | None:
    if source.asset in LABS_ASSETS:
        return LABS_NEWEST_DAYS
    return NEWEST_DAYS.get(source.kind)


def _failures(
    source: Source, summary: BodySummary, paginated: bool, today: date, last_ok: BodySummary | None
) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    newest_days = _newest_days(source)
    if newest_days is not None and (summary.newest is None or summary.newest < today - timedelta(days=newest_days)):
        failures.append(("*", "newest"))
    if paginated:
        failures.append(("*", "pagination"))
    if last_ok is not None and source.kind in FULL_HISTORY_KINDS and summary.rows < COLLAPSE_FLOOR * last_ok.rows:
        failures.append(("*", "collapse"))
    if source.kind == "cm-asset":
        for metric in ASSET_METRICS[source.asset]:
            if metric not in summary.metric_newest:
                failures.append((metric, "absent"))
        freshness_days = LABS_FRESHNESS_DAYS if source.asset in LABS_ASSETS else FRESHNESS_DAYS
        for metric, newest in sorted(summary.metric_newest.items()):
            if newest < today - timedelta(days=freshness_days):
                failures.append((metric, "freshness"))
    if last_ok is not None:
        for metric, newest in sorted(summary.metric_newest.items()):
            if metric in last_ok.metric_newest and newest < last_ok.metric_newest[metric]:
                failures.append((metric, "top"))
    # A bg body is a rolling 4-year window: its oldest day moves forward a day each day.
    if last_ok is not None and source.kind != "bg":
        for metric, oldest in sorted(summary.metric_oldest.items()):
            if metric in last_ok.metric_oldest and oldest > last_ok.metric_oldest[metric]:
                failures.append((metric, "bottom"))
    return failures


def _reason(failures: list[tuple[str, str]], shape: str | None) -> str:
    absent = [metric for metric, rule in failures if rule == "absent"]
    parts = [f"absent {', '.join(absent)}"] if absent else []
    for metric, rule in failures:
        if rule == "shape":
            parts.append(f"shape: {shape}")
        elif rule == "encoding":
            parts.append("encoding: not identity")
        elif rule != "absent":
            parts.append(rule if metric == "*" else f"{metric} {rule}")
    return "; ".join(parts)


def check_body(
    source: Source,
    body: bytes,
    *,
    content_encoding: str | None,
    tick: str,
    last_ok: BodySummary | None,
    last_ok_tick: str | None,
    acknowledgments: tuple[Acknowledgment, ...] = ACKNOWLEDGMENTS,
) -> Check:
    applied: list[Acknowledgment] = []

    def stands(failure: tuple[str, str]) -> bool:
        for ack in acknowledgments:
            if (ack.source, ack.metric, ack.rule) == (source.id, *failure) and _waives(ack, tick, last_ok_tick):
                applied.append(ack)
                return False
        return True

    summary = shape = None
    failures: list[tuple[str, str]] = []
    if content_encoding is not None and content_encoding.strip().lower() not in _IDENTITY_ENCODINGS:
        failures = [f for f in [("*", "encoding")] if stands(f)]
    if not failures:
        try:
            summary, paginated = _read(source, body)
        except ValueError as exc:
            shape = str(exc)
            failures = [f for f in [("*", "shape")] if stands(f)]
        else:
            failures = [f for f in _failures(source, summary, paginated, _tick_date(tick), last_ok) if stands(f)]
    return Check(
        outcome=2 if failures else 0,
        reason=_reason(failures, shape) if failures else None,
        newest_day=summary.newest if summary else None,
        rows=summary.rows if summary else None,
        metrics_absent=tuple(metric for metric, rule in failures if rule == "absent"),
        metrics_failed=tuple(failures),
        acknowledged=tuple(applied),
        summary=summary,
    )


def check_block(check: Check) -> dict:
    """The check's keys as `tick.json` carries them."""
    return {
        "outcome": check.outcome,
        "reason": check.reason,
        "newest_day": check.newest_day.isoformat() if check.newest_day else None,
        "rows": check.rows,
        "metrics_absent": list(check.metrics_absent),
        "metrics_failed": [list(failure) for failure in check.metrics_failed],
        "acknowledged": [asdict(ack) for ack in check.acknowledged],
    }
