"""The vintage fixtures: every body's provenance, the synthesised bodies' regeneration, shapes and bound, and the second
ticks' edits against their base."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from tests.vintage_fixtures import (
    BASE_TICK_START,
    FIXTURES,
    MAX_FILE_BYTES,
    MAX_ROWS,
    SENTINEL_KEY,
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
