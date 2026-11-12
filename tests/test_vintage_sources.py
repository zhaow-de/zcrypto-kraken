"""The vintage fixtures: every body's provenance, the synthesised bodies' regeneration, shapes and bound, and the second
ticks' edits against their base; the fetch table and the check each body is graded by."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from cli.vintage.sources import (
    ACKNOWLEDGMENTS,
    ASSET_METRICS,
    DOT_STOPPED,
    GENESIS,
    SOURCE_BY_ID,
    Acknowledgment,
    Check,
    check_block,
    check_body,
    summarise,
)
from cli.vintage.sources import SOURCES as FETCH_TABLE
from tests.vintage_fixtures import (
    BASE_TICK_START,
    FIXTURES,
    FROZEN_METRIC,
    GONE_METRIC,
    MAX_FILE_BYTES,
    MAX_ROWS,
    SENTINEL_KEY,
    SYNTHESISED,
    VARIANTS,
    body,
    loads_tokens,
    regenerate,
)

SHAPES = FIXTURES / "shapes"
REAL_BODIES = FIXTURES / "real-bodies.json"
FNG = FIXTURES / "fng.json"
PROVENANCE_KEYS = {"source", "file", "real", "committed", "how", "licence", "attribution"}
SECOND_TICK_KEYS = {"synthetic_second_tick", "from", "edit"}
REAL_KEYS = ("url", "fetched_at", "sha256", "bytes")
SOURCES = (
    "fng",
    "cm-catalog",
    "cm-status",
    "mempool-hashrate",
    *(f"cm-{a}" for a in ("ada", "avaxc", "avaxp", "btc", "doge", "dot", "eth", "link", "ltc", "xrp")),
    *(f"bg-{m}" for m in ("sopr", "asopr", "sth-sopr", "lth-sopr")),
)
INVALID_BEARER = "bg-sopr-invalid-bearer.json"
# The value tokens a skeleton keeps, by the key that holds them; JSON keys, true, false and null are kept everywhere.
KEPT_VALUES = {
    "cm-btc": {"asset", "time"},
    "cm-dot": {"asset", "time"},
    "cm-avaxc": {"asset", "time"},
    "cm-catalog": {"asset", "metric", "frequency", "community"},
    "mempool-hashrate": {"timestamp"},
    "bg-sopr": {"d", "unixTs"},
}
JSON_LITERALS = {"true", "false", "null"}
# The feed's kept structure: its prolog, its entity references and its xmlns value; element and attribute names are
# read apart from values by the tag pattern.
ATOM_PROLOG = '<?xml version="1.0" encoding="UTF-8"?>'
ATOM_ENTITY_REFERENCES = ("&lt;", "&gt;")
ATOM_XMLNS = "http://www.w3.org/2005/Atom"
ATOM_TAG = re.compile(r'</?[A-Za-z_][\w:.-]*((?:\s+[\w:.-]+="[^"]*")*)\s*/?>')
ATOM_ATTRIBUTE = re.compile(r'([\w:.-]+)="([^"]*)"')


def _shapes() -> dict[str, dict]:
    return {p.name.removesuffix(".shape.json"): json.loads(p.read_text()) for p in sorted(SHAPES.glob("*.shape.json"))}


def _bodies() -> list[Path]:
    return sorted(
        p
        for p in FIXTURES.rglob("*")
        if p.is_file() and SHAPES not in p.parents and p != REAL_BODIES and not p.name.endswith(".provenance.json")
    )


def _synthesised_bodies() -> list[Path]:
    return [p for p in _bodies() if p != FNG]


def _provenance(path: Path) -> dict:
    return json.loads(path.with_name(path.name + ".provenance.json").read_text())


def _format(source: str) -> str:
    shapes = _shapes()
    return shapes[source]["format"] if source in shapes else "json"


def _pinned(asset: str) -> set[str]:
    catalog = json.loads(_shapes()["cm-catalog"]["skeleton"])
    (entry,) = (e for e in catalog["data"] if e["asset"] == asset)
    return {m["metric"] for m in entry["metrics"] if any(f["frequency"] == "1d" for f in m["frequencies"])}


PINNED = _pinned("btc")


def test_every_fixture_body_has_its_provenance():
    bodies = _bodies()
    assert FNG in bodies and len(bodies) > len(_shapes())
    for path in bodies:
        provenance_path = path.with_name(path.name + ".provenance.json")
        assert provenance_path.is_file(), path
        provenance = _provenance(path)
        second = path.parent.name == "second"
        assert provenance.keys() >= PROVENANCE_KEYS | (SECOND_TICK_KEYS if second else set()), path
        assert provenance["file"] == path.relative_to(FIXTURES).as_posix()
        assert provenance["real"].keys() >= {*REAL_KEYS, "file"}, path
        if second:
            assert provenance["synthetic_second_tick"] is True
    data = FNG.read_bytes()
    real = _provenance(FNG)["real"]
    assert hashlib.sha256(data).hexdigest() == real["sha256"]
    assert len(data) == real["bytes"]


def test_only_fear_and_greeds_body_is_committed_real():
    provenances = [json.loads(p.read_text()) for p in sorted(FIXTURES.rglob("*.provenance.json"))]
    for provenance in provenances:
        source = provenance["source"]
        if source.startswith(("cm-", "bg-")) or source == "mempool-hashrate":
            assert provenance["committed"] == "synthesised", provenance["file"]
    assert [p["file"] for p in provenances if p["committed"] == "real"] == ["fng.json"]


def test_every_synthesised_fixture_regenerates_byte_for_byte():
    generated = regenerate()
    fng_files = {FNG, FNG.with_name("fng.json.provenance.json")}
    committed = {p for p in FIXTURES.rglob("*") if p.is_file() and SHAPES not in p.parents and p != REAL_BODIES} - fng_files
    assert set(generated) == committed
    assert [p.relative_to(FIXTURES).as_posix() for p in sorted(committed) if p.read_bytes() != generated[p]] == []


def _json_value_tokens(skeleton: str) -> list[tuple[str | None, str]]:
    """Each value token of a JSON skeleton with the key it sits under, a string's without its quotes."""
    tokens: list[tuple[str | None, str]] = []
    # One frame per open container: an object's the key last read in it, an array's None.
    stack: list[str | None] = []
    i = 0
    while i < len(skeleton):
        ch = skeleton[i]
        if ch == '"':
            end = i + 1
            while skeleton[end] != '"':
                end += 2 if skeleton[end] == "\\" else 1
            text = skeleton[i + 1 : end]
            rest = skeleton[end + 1 :].lstrip()
            if rest.startswith(":"):
                stack[-1] = text
            else:
                tokens.append((stack[-1] if stack else None, text))
            i = end + 1
        elif ch in "{[":
            stack.append(None)
            i += 1
        elif ch in "}]":
            stack.pop()
            i += 1
        elif ch in ",: \t\r\n":
            i += 1
        else:
            end = i
            while end < len(skeleton) and skeleton[end] not in '{}[],: \t\r\n"':
                end += 1
            tokens.append((stack[-1] if stack else None, skeleton[i:end]))
            i = end
    return tokens


def test_a_scalar_after_an_object_in_an_array_sits_under_no_key():
    tokens = _json_value_tokens('{"rows":[{"time":"#"},"~~",##],"n":#}')
    assert tokens == [("time", "#"), (None, "~~"), (None, "##"), ("n", "#")]


def _atom_value_tokens(skeleton: str) -> list[str]:
    """Each attribute value and text run of a feed skeleton, its prolog, its xmlns value and its entity references
    excepted."""
    assert skeleton.startswith(ATOM_PROLOG)
    rest = skeleton.removeprefix(ATOM_PROLOG)
    values = []
    for match in ATOM_TAG.finditer(rest):
        for name, value in ATOM_ATTRIBUTE.findall(match.group(1)):
            if not (name == "xmlns" and value == ATOM_XMLNS):
                values.append(value)
    for text in ATOM_TAG.split(rest)[::2]:
        for reference in ATOM_ENTITY_REFERENCES:
            text = text.replace(reference, "")
        values.append(text)
    return values


def test_no_shape_holds_a_value():
    shapes = _shapes()
    assert set(shapes) == {*KEPT_VALUES, "cm-status"}
    for source, shape in shapes.items():
        if shape["format"] == "atom":
            values = _atom_value_tokens(shape["skeleton"])
        else:
            values = [
                text
                for key, text in _json_value_tokens(shape["skeleton"])
                if key not in KEPT_VALUES[source] and text not in JSON_LITERALS
            ]
        assert values, source
        held = [v for v in values if any(ch.isalnum() for ch in v)]
        assert held == [], f"{source}: {held[:3]}"


def test_every_shape_names_a_recorded_body():
    recorded = json.loads(REAL_BODIES.read_text())
    reals = _shapes() | {"fng": _provenance(FNG)}
    for source, holder in reals.items():
        real = holder["real"]
        entry = recorded[real["file"]]
        assert entry["source"] == source
        assert {k: real[k] for k in REAL_KEYS} == {k: entry[k] for k in REAL_KEYS}, source
    assert len(recorded) == 19
    assert recorded[INVALID_BEARER]["source"] == "bg-sopr"
    others = {name: entry for name, entry in recorded.items() if name != INVALID_BEARER}
    assert sorted(entry["source"] for entry in others.values()) == sorted(SOURCES)
    assert all(name.split(".")[0] == entry["source"] for name, entry in others.items())


def test_every_synthesised_body_parses_in_its_format():
    for path in _synthesised_bodies():
        data = path.read_bytes()
        match fmt := _format(_provenance(path)["source"]):
            case "json":
                json.loads(data)
            case "json_stream":
                for line in data.split(b"\n"):
                    json.loads(line)
            case "atom":
                ET.fromstring(data)
            case _:
                pytest.fail(f"{path.name}: unknown format {fmt!r}")


def _counted_rows(source: str, data: bytes) -> list[int]:
    if source == "cm-status":
        return [data.count(b"<entry")]
    if _format(source) == "json_stream":
        return [len(data.splitlines())]
    doc = json.loads(data)
    if source == "cm-catalog":
        return [len(doc.get("data", []))]
    if source == "mempool-hashrate":
        return [len(doc.get("hashrates", [])), len(doc.get("difficulty", []))]
    if source.startswith("bg-"):
        return [len(doc) if isinstance(doc, list) else 0]
    if source == "fng":
        return []
    pytest.fail(f"no row count for source {source!r}")


def test_every_fixture_holds_the_bound():
    for path in _synthesised_bodies():
        counts = _counted_rows(_provenance(path)["source"], path.read_bytes())
        assert all(n <= MAX_ROWS for n in counts), (path.name, counts)
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            assert path.stat().st_size < MAX_FILE_BYTES, path


def _stream(name: str) -> list[dict]:
    return [loads_tokens(line) for line in body(name).split(b"\n")]


def _cells(rows: list[dict]) -> dict[tuple[str, str], str]:
    return {(k, r["time"][:10]): v for r in rows for k, v in r.items() if k not in ("asset", "time")}


def _days(cells: dict[tuple[str, str], str], key: str) -> list[str]:
    return sorted(d for k, d in cells if k == key)


def _row_days(rows: list[dict]) -> list[str]:
    return [r["time"][:10] for r in rows]


def _only_gone(base: list[dict], nxt: list[dict]) -> set[tuple[str, str]]:
    b, n = _cells(base), _cells(nxt)
    assert n.keys() <= b.keys()
    assert all(n[c] == b[c] for c in n)
    return b.keys() - n.keys()


def _one_differing(base: list[dict], nxt: list[dict]) -> tuple[str, str]:
    b, n = _cells(base), _cells(nxt)
    assert _row_days(base) == _row_days(nxt)
    assert b.keys() == n.keys()
    (cell,) = (c for c in b if b[c] != n[c])
    return cell


def _check_cm_btc_restatement(base, nxt):
    key, day = _one_differing(base, nxt)
    days = _days(_cells(base), key)
    assert key in PINNED and days[0] < day < days[-1]


def _check_cm_btc_next(base, nxt):
    assert len(nxt) == len(base) == MAX_ROWS
    assert nxt[:-1] == base[:-1]
    newest_metrics = set(base[-1]) - {"asset", "time"}
    assert newest_metrics and all(m.startswith("ReferenceRate") for m in newest_metrics)
    assert all(nxt[-1][k] == v for k, v in base[-1].items())
    gained = set(nxt[-1]) - set(base[-1])
    assert gained == {m for m in PINNED if m in base[-2]} - newest_metrics
    assert "PriceUSD" in gained


def _check_cm_btc_retraction(base, nxt):
    assert _row_days(base) == _row_days(nxt)
    ((key, day),) = _only_gone(base, nxt)
    days = _days(_cells(nxt), key)
    assert key in PINNED and days[0] < day < days[-1]


def _gone_metric(base, nxt) -> str:
    gone = _only_gone(base, nxt)
    (metric,) = {k for k, _ in gone}
    assert metric in PINNED
    assert gone == {c for c in _cells(base) if c[0] == metric}
    return metric


def _check_cm_btc_metric_gone(base, nxt):
    assert _row_days(base) == _row_days(nxt)
    _gone_metric(base, nxt)


def _check_cm_btc_metric_back_changed(base, nxt):
    metric = _gone_metric(base, _stream("second/cm-btc-metric-gone"))
    key, _ = _one_differing(base, nxt)
    assert key == metric


def _check_cm_btc_gap(base, nxt):
    assert _row_days(base) == _row_days(nxt)
    ((key, day),) = _only_gone(base, nxt)
    assert key in PINNED and day == _days(_cells(base), key)[-2]


def _check_cm_btc_time_format(base, nxt):
    assert len(nxt) == len(base)
    for b, n in zip(base, nxt, strict=True):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", n["time"]) and n["time"][:10] == b["time"][:10]
        assert list(n) == list(b) and {**n, "time": b["time"]} == b


def _check_cm_btc_collapse(base, nxt):
    assert len(nxt) == len(base) * 85 // 100
    kept = set(_row_days(nxt))
    assert nxt == [r for r in base if r["time"][:10] in kept]
    dropped = [i for i, r in enumerate(base) if r["time"][:10] not in kept]
    assert dropped == list(range(dropped[0], dropped[-1] + 1))
    for key in {k for r in base for k in r}:
        carrying = [i for i, r in enumerate(base) if key in r]
        assert carrying[0] not in dropped and carrying[-1] not in dropped, key


def _check_cm_btc_lost_newest(base, nxt):
    b, n = _cells(base), _cells(nxt)
    assert all(n[c] == b[c] for c in n)
    for metric in PINNED:
        assert _days(n, metric) == _days(b, metric)[:-2], metric


def _check_cm_btc_frozen(base, nxt):
    assert _row_days(base) == _row_days(nxt)
    gone = _only_gone(base, nxt)
    (metric,) = {k for k, _ in gone}
    days = _days(_cells(base), metric)
    assert metric in PINNED and not metric.startswith("ReferenceRate")
    assert days[-1] == (BASE_TICK_START.date() - timedelta(days=1)).isoformat()
    assert gone == {(metric, d) for d in days[-5:]}


def _check_cm_catalog_paginated(base, nxt):
    assert "next_page_url" not in base
    assert {k: v for k, v in nxt.items() if k != "next_page_url"} == base
    assert nxt["next_page_url"].startswith("https://")


def _check_cm_btc_403(base, nxt):
    (doc,) = nxt
    assert list(doc) == ["error"] and list(doc["error"]) == ["type", "message"]
    assert doc["error"]["type"] == "forbidden"
    measured = r"Requested metric '(\w+)' with frequency '1d' for asset 'btc' is not available with supplied credentials\."
    match = re.fullmatch(measured, doc["error"]["message"])
    assert match and match[1] in PINNED


def _check_mempool_hashrate_restated_big(base, nxt):
    assert {k: v for k, v in nxt.items() if k != "hashrates"} == {k: v for k, v in base.items() if k != "hashrates"}
    pairs = list(zip(base["hashrates"], nxt["hashrates"], strict=True))
    ((b, n),) = ((b, n) for b, n in pairs if b != n)
    assert {**n, "avgHashrate": b["avgHashrate"]} == b
    old, new = b["avgHashrate"], n["avgHashrate"]
    assert old.isdigit() and new.isdigit() and int(old) > 2**53
    assert old[:-1] == new[:-1] and old[-1] != new[-1]


def _check_bg_sopr_rolled(base, nxt):
    assert nxt[:-1] == base[1:]
    new = nxt[-1]
    assert list(new) == list(base[-1])
    day = date.fromisoformat(base[-1]["d"]) + timedelta(days=1)
    assert new["d"] == day.isoformat()
    assert int(new["unixTs"]) == int(datetime.combine(day, time(), UTC).timestamp())


def _check_bg_sopr_newest_back(base, nxt):
    assert nxt == base[:-1]


def _check_bg_sopr_collapse(base, nxt):
    assert len(base) == MAX_ROWS and nxt == base[-100:]


def _check_bg_sopr_restatement(base, nxt):
    pairs = list(zip(base, nxt, strict=True))
    ((b, n),) = ((b, n) for b, n in pairs if b != n)
    assert list(n) == list(b) and (n["d"], n["unixTs"]) == (b["d"], b["unixTs"])


def _spring(nxt, status: int) -> dict:
    assert isinstance(nxt, dict) and nxt["status"] == str(status) and nxt["path"] == "/v1/sopr"
    return nxt


def _check_bg_sopr_404(base, nxt):
    assert list(_spring(nxt, 404)) == ["timestamp", "status", "error", "path"] and nxt["error"] == "Not Found"


def _check_bg_sopr_401_echo(base, nxt):
    assert SENTINEL_KEY in _spring(nxt, 401)["message"]


def _check_bg_sopr_429(base, nxt):
    assert list(_spring(nxt, 429)) == ["timestamp", "status", "error", "path"]


def _check_fng_next(base, nxt):
    def facts(row):
        return row["value"], row["value_classification"], row["timestamp"]

    assert {k: v for k, v in nxt.items() if k != "data"} == {k: v for k, v in base.items() if k != "data"}
    new, *older = nxt["data"]
    assert int(new["timestamp"]) == int(base["data"][0]["timestamp"]) + 86400
    assert "time_until_update" in new and not any("time_until_update" in row for row in older)
    pairs = list(zip(base["data"], older, strict=True))
    ((b, n),) = ((b, n) for b, n in pairs if facts(b) != facts(n))
    assert b is not base["data"][0]
    assert (n["value_classification"], n["timestamp"]) == (b["value_classification"], b["timestamp"])


CHECKS = {
    "cm-btc-restatement": _check_cm_btc_restatement,
    "cm-btc-next": _check_cm_btc_next,
    "cm-btc-retraction": _check_cm_btc_retraction,
    "cm-btc-metric-gone": _check_cm_btc_metric_gone,
    "cm-btc-metric-back-changed": _check_cm_btc_metric_back_changed,
    "cm-btc-gap": _check_cm_btc_gap,
    "cm-btc-time-format": _check_cm_btc_time_format,
    "cm-btc-collapse": _check_cm_btc_collapse,
    "cm-btc-lost-newest": _check_cm_btc_lost_newest,
    "cm-btc-frozen": _check_cm_btc_frozen,
    "cm-catalog-paginated": _check_cm_catalog_paginated,
    "cm-btc-403": _check_cm_btc_403,
    "mempool-hashrate-restated-big": _check_mempool_hashrate_restated_big,
    "bg-sopr-rolled": _check_bg_sopr_rolled,
    "bg-sopr-newest-back": _check_bg_sopr_newest_back,
    "bg-sopr-collapse": _check_bg_sopr_collapse,
    "bg-sopr-restatement": _check_bg_sopr_restatement,
    "bg-sopr-404": _check_bg_sopr_404,
    "bg-sopr-401-echo": _check_bg_sopr_401_echo,
    "bg-sopr-429": _check_bg_sopr_429,
    "fng-next": _check_fng_next,
}


@pytest.mark.parametrize("name", list(CHECKS))
def test_each_second_tick_differs_from_its_base_as_its_name_says(name):
    assert set(VARIANTS) == set(CHECKS)
    variant = VARIANTS[name]
    if _format(variant.base) == "json_stream":
        base, nxt = _stream(variant.base), _stream(f"second/{name}")
    else:
        base, nxt = loads_tokens(body(variant.base)), loads_tokens(body(f"second/{name}"))
    CHECKS[name](base, nxt)


TICK = BASE_TICK_START.strftime("%Y%m%dT%H%M%SZ")
TODAY = BASE_TICK_START.date()
EARLIER_TICK = "20261110T193700Z"
TICK_ORDER = (
    "bg-sopr",
    "bg-asopr",
    "bg-sth-sopr",
    "bg-lth-sopr",
    "fng",
    "cm-status",
    "mempool-hashrate",
    "cm-btc",
    "cm-eth",
    "cm-xrp",
    "cm-ada",
    "cm-link",
    "cm-doge",
    "cm-ltc",
    "cm-dot",
    "cm-avaxc",
    "cm-avaxp",
    "cm-catalog",
)
CM_ASSETS = ("btc", "eth", "xrp", "ada", "link", "doge", "ltc", "dot", "avaxc", "avaxp")


def _check(source_id: str, data: bytes, **kwargs) -> Check:
    kwargs = {"content_encoding": None, "tick": TICK, "last_ok": None, "last_ok_tick": None, **kwargs}
    return check_body(SOURCE_BY_ID[source_id], data, **kwargs)


def _graded(check: Check) -> tuple:
    return check.outcome, check.metrics_absent, check.metrics_failed


def _ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def _epoch_day(token) -> date:
    return datetime.fromtimestamp(int(token), UTC).date()


def _cm_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in body(name).split(b"\n")]


def _cm_day(row: dict) -> date:
    return date.fromisoformat(row["time"][:10])


def _jsonl(rows: list[dict]) -> bytes:
    return b"\n".join(json.dumps(row).encode() for row in rows)


def _metric_until(rows: list[dict], metric: str, last: date) -> bytes:
    """The rows with `metric` dropped from every row after `last`, so its newest day is `last`."""
    kept = [{k: v for k, v in row.items() if k != metric or _cm_day(row) <= last} for row in rows]
    assert max(_cm_day(row) for row in kept if metric in row) == last
    return _jsonl(kept)


def _rows_until(rows: list[dict], last: date) -> bytes:
    kept = [row for row in rows if _cm_day(row) <= last]
    assert max(map(_cm_day, kept)) == last
    return _jsonl(kept)


def _without_end(rows: list[dict], metric: str, end: int) -> bytes:
    """The rows with `metric` dropped from the row that holds its oldest (end 0) or newest (end -1) day."""
    i = [i for i, row in enumerate(rows) if metric in row][end]
    rows = [dict(row) for row in rows]
    del rows[i][metric]
    return _jsonl(rows)


def _fng_until(last: date) -> bytes:
    doc = json.loads(body("fng"))
    doc["data"] = [row for row in doc["data"] if _epoch_day(row["timestamp"]) <= last]
    assert _epoch_day(doc["data"][0]["timestamp"]) == last
    return json.dumps(doc).encode()


def _mempool_until(last: date) -> bytes:
    doc = json.loads(body("mempool-hashrate"))
    doc["hashrates"] = [row for row in doc["hashrates"] if _epoch_day(row["timestamp"]) <= last]
    assert max(_epoch_day(row["timestamp"]) for row in doc["hashrates"]) == last
    return json.dumps(doc).encode()


def _bg_until(last: date) -> bytes:
    rows = [row for row in json.loads(body("bg-sopr")) if date.fromisoformat(row["d"]) <= last]
    assert rows[-1]["d"] == last.isoformat()
    return json.dumps(rows).encode()


def _catalog_daily() -> dict[str, list[str]]:
    catalog = json.loads(body("cm-catalog"))
    return {
        entry["asset"]: [m["metric"] for m in entry["metrics"] if any(f["frequency"] == "1d" for f in m["frequencies"])]
        for entry in catalog["data"]
    }


def test_the_fetch_table_is_pinned():
    assert tuple(s.id for s in FETCH_TABLE) == TICK_ORDER
    assert SOURCE_BY_ID == {s.id: s for s in FETCH_TABLE}
    fixed = {
        "fng": ("https://api.alternative.me/fng/?limit=0", "fng.json.gz", "alternative.me", "fng"),
        "cm-status": ("https://status.coinmetrics.io/history.atom", "cm-status.atom.gz", "coinmetrics", "cm-status"),
        "mempool-hashrate": (
            "https://mempool.space/api/v1/mining/hashrate/all",
            "mempool-hashrate.json.gz",
            "mempool.space",
            "mempool-hashrate",
        ),
        "cm-catalog": (
            "https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics"
            "?assets=btc,eth,sol,xrp,ada,link,doge,ltc,dot,avax,avaxc,avaxp&page_size=2000",
            "cm-catalog.json.gz",
            "coinmetrics",
            "cm-catalog",
        ),
    }
    for source_id, (url, file, provider, kind) in fixed.items():
        s = SOURCE_BY_ID[source_id]
        assert (s.url, s.file, s.provider, s.kind, s.keyed, s.value_key, s.asset) == (url, file, provider, kind, False, None, None)
    for metric, value_key in (("sopr", "sopr"), ("asopr", "asopr"), ("sth-sopr", "sthSopr"), ("lth-sopr", "lthSopr")):
        s = SOURCE_BY_ID[f"bg-{metric}"]
        expected = (f"https://api.bitcoin-data.com/v1/{metric}", f"bg-{metric}.json.gz", "bgeometrics", "bg", True, value_key, None)
        assert (s.url, s.file, s.provider, s.kind, s.keyed, s.value_key, s.asset) == expected
    for asset in CM_ASSETS:
        s = SOURCE_BY_ID[f"cm-{asset}"]
        assert (s.file, s.provider, s.kind, s.keyed, s.value_key, s.asset) == (
            f"cm-{asset}.jsonl.gz",
            "coinmetrics",
            "cm-asset",
            False,
            None,
            asset,
        )
    assert all(s.host == urlsplit(s.url).hostname for s in FETCH_TABLE)
    counts = {"btc": 31, "eth": 31, "doge": 26, "ltc": 26, "ada": 24, "xrp": 23, "link": 22, "dot": 22, "avaxc": 17, "avaxp": 17}
    assert {asset: len(metrics) for asset, metrics in ASSET_METRICS.items()} == counts
    assert all(list(metrics) == sorted(metrics) for metrics in ASSET_METRICS.values())


def test_every_cm_url_asks_its_assets_catalog_list_with_both_flags():
    daily = _catalog_daily()
    for asset in CM_ASSETS:
        parts = urlsplit(SOURCE_BY_ID[f"cm-{asset}"].url)
        assert (parts.scheme, parts.netloc, parts.path) == ("https", "community-api.coinmetrics.io", "/v4/timeseries/asset-metrics")
        assert parse_qs(parts.query, strict_parsing=True) == {
            "assets": [asset],
            "metrics": [",".join(daily[asset])],
            "frequency": ["1d"],
            "format": ["json_stream"],
            "ignore_forbidden_errors": ["true"],
            "ignore_unsupported_errors": ["true"],
        }, asset
        assert ASSET_METRICS[asset] == tuple(daily[asset])


def test_no_bg_url_carries_a_query_and_no_url_names_a_kraken_host():
    for s in FETCH_TABLE:
        assert "kraken" not in s.url.lower() and "kraken" not in s.host.lower(), s.id
        if s.kind == "bg":
            assert "?" not in s.url and urlsplit(s.url).query == "", s.id


@pytest.mark.parametrize("name", ["fng", "cm-btc", "cm-dot", "cm-avaxc", "cm-catalog", "cm-status", "mempool-hashrate", "bg-sopr"])
def test_each_source_kinds_fixture_grades_ok(name):
    check = _check(name, body(name))
    assert (*_graded(check), check.reason) == (0, (), (), None)


def _fng_edited(edit) -> bytes:
    doc = json.loads(body("fng"))
    edit(doc)
    return json.dumps(doc).encode()


def _cm_edited(edit) -> bytes:
    rows = _cm_rows("cm-btc")
    edit(rows)
    return _jsonl(rows)


def _cm_line_replaced(line: bytes) -> bytes:
    lines = body("cm-btc").split(b"\n")
    lines[5] = line
    return b"\n".join(lines)


def _json_edited(name: str, edit) -> bytes:
    doc = json.loads(body(name))
    edit(doc)
    return json.dumps(doc).encode()


def _feed_without_entries() -> bytes:
    feed = body("cm-status")
    return feed[: feed.index(b"<entry")] + b"</feed>\n"


BROKEN = {
    "fng-metadata-error": ("fng", lambda: _fng_edited(lambda d: d["metadata"].update(error="upstream unavailable"))),
    "fng-row-without-timestamp": ("fng", lambda: _fng_edited(lambda d: d["data"][3].pop("timestamp"))),
    "cm-line-not-an-object": ("cm-btc", lambda: _cm_line_replaced(b'"not an object"')),
    "cm-line-without-time": ("cm-btc", lambda: _cm_edited(lambda rows: rows[5].pop("time"))),
    "catalog-empty-data": ("cm-catalog", lambda: _json_edited("cm-catalog", lambda d: d.update(data=[]))),
    "feed-without-entry": ("cm-status", _feed_without_entries),
    "mempool-empty-hashrates": ("mempool-hashrate", lambda: _json_edited("mempool-hashrate", lambda d: d.update(hashrates=[]))),
    "bg-row-without-value-key": ("bg-sopr", lambda: _json_edited("bg-sopr", lambda rows: rows[7].pop("sopr"))),
}


@pytest.mark.parametrize("case", list(BROKEN))
def test_a_broken_body_grades_2(case):
    source_id, make = BROKEN[case]
    check = _check(source_id, make())
    assert _graded(check) == (2, (), (("*", "shape"),))
    assert check.reason and check.summary is None


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (lambda d: d.pop("metadata"), (0, (), ())),
        (lambda d: d.update(metadata=None), (0, (), ())),
        (lambda d: d.update(metadata=[]), (2, (), (("*", "shape"),))),
        (lambda d: d.update(metadata=""), (2, (), (("*", "shape"),))),
    ],
    ids=["missing", "null", "list", "empty-string"],
)
def test_only_a_missing_or_null_fng_metadata_reads_as_empty(edit, expected):
    check = _check("fng", _fng_edited(edit))
    assert _graded(check) == expected
    assert (check.reason or "").startswith("shape") == (expected[0] == 2)


WRONG_SHAPE = {
    "bg-object": ("bg-sopr", lambda: b'{"d":"2026-11-04","unixTs":1793750400,"sopr":1.5}'),
    "cm-line-array": ("cm-btc", lambda: _cm_line_replaced(b"[]")),
    "fng-data-object": ("fng", lambda: _fng_edited(lambda d: d.update(data={"value": "29", "timestamp": "1794355200"}))),
    "fng-not-utf8": ("fng", lambda: body("fng").replace(b"Fear", b"F\xe9ar", 1)),
    "cm-not-utf8": ("cm-btc", lambda: _cm_line_replaced(b'{"asset":"btc","time":"2009-01-05T00:00:00Z","PriceUSD":"\xff"}')),
    "bg-not-utf8": ("bg-sopr", lambda: b"\xff\xfe[]"),
}


@pytest.mark.parametrize("case", list(WRONG_SHAPE))
def test_a_body_in_the_wrong_shape_grades_2_and_never_raises(case):
    source_id, make = WRONG_SHAPE[case]
    check = _check(source_id, make())
    assert _graded(check) == (2, (), (("*", "shape"),))
    assert check.reason


def test_a_non_identity_encoding_grades_2():
    check = _check("cm-btc", body("cm-btc"), content_encoding="gzip")
    assert _graded(check) == (2, (), (("*", "encoding"),))
    assert check.reason
    for encoding in (None, "", "identity"):
        assert _check("cm-btc", body("cm-btc"), content_encoding=encoding).outcome == 0, encoding


def test_an_absent_pinned_metric_grades_2_and_names_it():
    check = _check("cm-btc", body("second/cm-btc-metric-gone"))
    assert _graded(check) == (2, (GONE_METRIC,), ((GONE_METRIC, "absent"),))
    assert GONE_METRIC in check.reason
    block = check_block(check)
    assert block["metrics_absent"] == [GONE_METRIC] and block["metrics_failed"] == [[GONE_METRIC, "absent"]]
    assert block["outcome"] == 2


def test_every_outcome_2_check_names_a_failed_entry():
    graded = []
    for name in ["fng", *SYNTHESISED, *(f"second/{v}" for v in VARIANTS)]:
        source_id = VARIANTS[name.removeprefix("second/")].base if name.startswith("second/") else name
        base = body(source_id)
        for last_ok in (None, summarise(SOURCE_BY_ID[source_id], base)):
            check = _check(source_id, body(name), last_ok=last_ok, last_ok_tick=EARLIER_TICK)
            graded.append((name, check.outcome))
            assert check.outcome in (0, 2), name
            assert check.outcome == 0 or check.metrics_failed, name
    assert ("second/cm-btc-metric-gone", 2) in graded and ("cm-btc", 0) in graded


def test_a_metric_past_its_freshness_bound_grades_2():
    rows = _cm_rows("cm-btc")
    assert _graded(_check("cm-btc", _metric_until(rows, "HashRate", _ago(4)))) == (2, (), (("HashRate", "freshness"),))
    assert _graded(_check("cm-btc", _metric_until(rows, "HashRate", _ago(3)))) == (0, (), ())
    dot = _check("cm-dot", body("cm-dot"))
    assert _graded(dot) == (0, (), ())
    assert {Acknowledgment("cm-dot", m, "freshness", GENESIS) for m in DOT_STOPPED} <= set(dot.acknowledged)
    stale = _metric_until(_cm_rows("cm-dot"), "CapMrktEstUSD", _ago(4))
    assert _graded(_check("cm-dot", stale)) == (2, (), (("CapMrktEstUSD", "freshness"),))
    assert _graded(_check("cm-btc", body("second/cm-btc-frozen"))) == (2, (), ((FROZEN_METRIC, "freshness"),))


def test_the_labs_assets_take_date_minus_30():
    rows = _cm_rows("cm-avaxc")
    assert _graded(_check("cm-avaxc", _metric_until(rows, "AdrActCnt", _ago(31)))) == (2, (), (("AdrActCnt", "freshness"),))
    assert _graded(_check("cm-avaxc", _metric_until(rows, "AdrActCnt", _ago(10)))) == (0, (), ())


def test_never_shorter_at_the_top_and_bottom():
    btc, rows = SOURCE_BY_ID["cm-btc"], _cm_rows("cm-btc")
    last = {"last_ok": summarise(btc, body("cm-btc")), "last_ok_tick": EARLIER_TICK}
    lost = _check("cm-btc", body("second/cm-btc-lost-newest"), **last)
    assert lost.outcome == 2
    assert [m for m, rule in lost.metrics_failed if rule == "top"] == list(ASSET_METRICS["btc"])
    assert ("*", "newest") in lost.metrics_failed
    assert _graded(_check("cm-btc", _without_end(rows, "AdrActCnt", 0), **last)) == (2, (), (("AdrActCnt", "bottom"),))
    reference = _check("cm-btc", _without_end(rows, "ReferenceRate", 0), **last)
    assert _graded(reference) == (0, (), ())
    assert Acknowledgment("cm-btc", "ReferenceRate", "bottom", GENESIS) in reference.acknowledged
    dot_last = {"last_ok": summarise(SOURCE_BY_ID["cm-dot"], body("cm-dot")), "last_ok_tick": EARLIER_TICK}
    shrunk = _check("cm-dot", _without_end(_cm_rows("cm-dot"), "SplyCur", -1), **dot_last)
    assert _graded(shrunk) == (2, (), (("SplyCur", "top"),))


def test_a_collapse_grades_2():
    fng = json.loads(body("fng"))
    last = replace(summarise(SOURCE_BY_ID["fng"], body("fng")), rows=100)

    def first(n: int) -> bytes:
        return json.dumps({**fng, "data": fng["data"][:n]}).encode()

    assert _graded(_check("fng", first(89), last_ok=last, last_ok_tick=EARLIER_TICK)) == (2, (), (("*", "collapse"),))
    assert _graded(_check("fng", first(90), last_ok=last, last_ok_tick=EARLIER_TICK)) == (0, (), ())
    base = summarise(SOURCE_BY_ID["cm-btc"], body("cm-btc"))
    collapse = _check("cm-btc", body("second/cm-btc-collapse"), last_ok=base, last_ok_tick=EARLIER_TICK)
    assert _graded(collapse) == (2, (), (("*", "collapse"),))


def test_the_source_level_newest_bound():
    newest = (2, (), (("*", "newest"),))
    btc = _cm_rows("cm-btc")
    assert _graded(_check("cm-btc", _rows_until(btc, _ago(2)))) == newest
    assert _graded(_check("cm-btc", _rows_until(btc, _ago(1)))) == (0, (), ())
    assert _graded(_check("mempool-hashrate", _mempool_until(_ago(4)))) == newest
    assert _graded(_check("mempool-hashrate", _mempool_until(_ago(3)))) == (0, (), ())
    assert _graded(_check("fng", _fng_until(_ago(2)))) == newest
    assert _graded(_check("fng", _fng_until(_ago(1)))) == (0, (), ())
    assert _graded(_check("bg-sopr", _bg_until(_ago(10)))) == newest
    assert _graded(_check("bg-sopr", _bg_until(_ago(9)))) == (0, (), ())
    avaxc = _cm_rows("cm-avaxc")
    old = _check("cm-avaxc", _rows_until(avaxc, _ago(31)))
    assert old.outcome == 2 and ("*", "newest") in old.metrics_failed
    assert _graded(_check("cm-avaxc", _rows_until(avaxc, _ago(10)))) == (0, (), ())


def test_a_paginated_catalog_grades_2():
    assert _graded(_check("cm-catalog", body("second/cm-catalog-paginated"))) == (2, (), (("*", "pagination"),))


def _value_tokens(doc) -> set[str]:
    if isinstance(doc, dict):
        return set().union(*map(_value_tokens, doc.values()))
    if isinstance(doc, list):
        return set().union(*map(_value_tokens, doc))
    return {doc} if isinstance(doc, str) else set()


def test_the_bg_check():
    last = {"last_ok": summarise(SOURCE_BY_ID["bg-sopr"], body("bg-sopr")), "last_ok_tick": EARLIER_TICK}
    graded = {
        "second/bg-sopr-rolled": (0, (), ()),
        "second/bg-sopr-newest-back": (2, (), (("*", "top"),)),
        "second/bg-sopr-collapse": (2, (), (("*", "collapse"),)),
        "second/bg-sopr-401-echo": (2, (), (("*", "shape"),)),
    }
    for name, expected in graded.items():
        check = _check("bg-sopr", body(name), **last)
        assert _graded(check) == expected, name
        tokens = _value_tokens(loads_tokens(body(name)))
        assert check.reason is None or not any(token in check.reason for token in tokens), name
        assert SENTINEL_KEY not in (check.reason or ""), name
    assert SENTINEL_KEY.encode() in body("second/bg-sopr-401-echo")


def test_an_acknowledgment_holds_from_its_tick():
    since = "20261111T000000Z"
    assert EARLIER_TICK < since <= TICK
    frozen = body("second/cm-btc-frozen")
    ack = Acknowledgment("cm-btc", FROZEN_METRIC, "freshness", since)
    acks = (*ACKNOWLEDGMENTS, ack)
    before = _check("cm-btc", frozen, tick=EARLIER_TICK, acknowledgments=acks)
    assert _graded(before) == (2, (), ((FROZEN_METRIC, "freshness"),)) and ack not in before.acknowledged
    held = _check("cm-btc", frozen, tick=since, acknowledgments=acks)
    assert _graded(held) == (0, (), ()) and ack in held.acknowledged
    assert {"source": "cm-btc", "metric": FROZEN_METRIC, "rule": "freshness", "since": since} in check_block(held)["acknowledged"]
    collapse_ack = Acknowledgment("cm-btc", "*", "collapse", since)
    acks = (*ACKNOWLEDGMENTS, collapse_ack)
    base = summarise(SOURCE_BY_ID["cm-btc"], body("cm-btc"))
    collapsed = body("second/cm-btc-collapse")
    restarted = _check("cm-btc", collapsed, last_ok=base, last_ok_tick=EARLIER_TICK, acknowledgments=acks)
    assert _graded(restarted) == (0, (), ()) and collapse_ack in restarted.acknowledged
    for last_ok_tick in (since, TICK):
        compared = _check("cm-btc", collapsed, last_ok=base, last_ok_tick=last_ok_tick, acknowledgments=acks)
        assert _graded(compared) == (2, (), (("*", "collapse"),)), last_ok_tick


def test_keys_outside_the_pinned_list_are_ignored_by_the_check():
    companions = ("FlowInExNtv-status", "FlowInExNtv-status-time")
    every_row = _cm_edited(lambda rows: [row.update({k: "reviewed" for k in companions}) for row in rows])
    stale_companions = ("CapMVRVCur-status", "CapMVRVCur-status-time")
    old_rows = [
        {**row, **({k: "reviewed" for k in stale_companions} if _cm_day(row) <= _ago(4) else {})} for row in _cm_rows("cm-btc")
    ]
    assert max(_cm_day(row) for row in old_rows if stale_companions[0] in row) == _ago(4)
    for data, names in ((every_row, companions), (_jsonl(old_rows), stale_companions)):
        check = _check("cm-btc", data)
        assert (*_graded(check), check.reason) == (0, (), (), None)
        assert not any(name in str(check_block(check)) for name in names)


def test_the_named_exemptions_are_the_genesis_entries():
    dot = (
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
    expected = {
        *(Acknowledgment("cm-dot", m, "freshness", GENESIS) for m in dot),
        *(Acknowledgment("cm-eth", m, "freshness", GENESIS) for m in ("HashRate", "SplyExpFut10yr")),
        *(
            Acknowledgment(f"cm-{asset}", m, "bottom", GENESIS)
            for asset, metrics in _catalog_daily().items()
            if asset in CM_ASSETS
            for m in metrics
            if m.startswith("ReferenceRate")
        ),
    }
    genesis = [a for a in ACKNOWLEDGMENTS if a.since == GENESIS]
    assert len(genesis) == len(set(genesis)) == 12 + 2 + 38
    assert set(genesis) == expected
