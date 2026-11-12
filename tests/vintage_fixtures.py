"""The vintage fixtures: each synthesised body drawn from its committed shape file and seed, the second ticks edited from
those bodies (and `fng-next` from Fear & Greed's real body), and their provenance. `python -m tests.vintage_fixtures`
writes them; the tests compare the committed bytes against `regenerate()`."""

from __future__ import annotations

import json
import random
import re
import string
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "vintage"
MAX_ROWS = 120
MAX_FILE_BYTES = 500 * 1024
SENTINEL_KEY = "vintage.Sentinel-key_0~9+/x=="
# Spelt as literals, never built from SENTINEL_KEY, so a test reading them never reads through the forms under test.
SENTINEL_FORMS = (
    b"vintage.Sentinel-key_0~9+/x==",
    b"vintage.Sentinel-key_0~9+\\/x==",
    b"vintage.Sentinel-key_0~9%2B%2Fx%3D%3D",
    b"vintage.Sentinel-key_0~9%2b%2fx%3d%3d",
)
SYNTHESISED = ("cm-btc", "cm-dot", "cm-avaxc", "cm-catalog", "cm-status", "mempool-hashrate", "bg-sopr")
GENERATOR = "tests/vintage_fixtures.py"
VARIANT_SEED = 159000
FNG_FILE = "fng.json"

# The metrics the coupled cm-btc variants name: metric-back-changed restores the metric metric-gone drops, and the
# frozen one is a network metric whose newest day is the fetch date - 1, never a ReferenceRate* one.
GONE_METRIC = "CapMVRVCur"
GAP_METRIC = "TxCnt"
FROZEN_METRIC = "AdrActCnt"


class RawNumber(str):
    """A JSON number as the body spells it, so an integer past 2^53 or an exponent survives a round trip."""


def loads_tokens(data: bytes) -> object:
    return json.loads(data, parse_int=RawNumber, parse_float=RawNumber)


def dumps_compact(obj) -> bytes:
    return _encode(obj).encode()


def _encode(obj) -> str:
    if isinstance(obj, RawNumber):
        return str(obj)
    if isinstance(obj, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{_encode(v)}" for k, v in obj.items()) + "}"
    if isinstance(obj, list):
        return "[" + ",".join(_encode(v) for v in obj) + "]"
    return json.dumps(obj)


@cache
def _shape(source: str) -> dict:
    return json.loads((FIXTURES / "shapes" / f"{source}.shape.json").read_text())


@cache
def _fng_provenance() -> dict:
    return json.loads((FIXTURES / f"{FNG_FILE}.provenance.json").read_text())


BASE_TICK_START = datetime.combine(datetime.fromisoformat(_shape("cm-btc")["real"]["fetched_at"]).date(), time(0, 37), tzinfo=UTC)


def synthesize(shape: dict) -> bytes:
    rng = random.Random(shape["seed"])
    skeleton = shape["skeleton"]
    json_like = shape["format"] in ("json", "json_stream")
    out = []
    in_string = escaped = False
    for i, ch in enumerate(skeleton):
        if json_like:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
        before = skeleton[i - 1] if i else ""
        if ch == "#":
            # A leading zero is no number: a run's first digit is nonzero unless it continues digits or a fraction.
            opens_run = before != "#" and skeleton[i + 1 : i + 2] == "#" and before not in (*string.digits, ".")
            out.append(rng.choice("123456789" if opens_run else string.digits))
        elif ch == "~":
            # Outside a JSON string a letter can only be a number's exponent marker.
            out.append("e" if json_like and not in_string else rng.choice(string.ascii_lowercase))
        else:
            out.append(ch)
    return ("".join(out) + ("\n" if shape["trailing_newline"] else "")).encode()


def _stream_rows(data: bytes) -> list[dict]:
    return [loads_tokens(line) for line in data.split(b"\n")]


def _stream(rows: list[dict]) -> bytes:
    return b"\n".join(dumps_compact(r) for r in rows)


def _changed(token: str, rng: random.Random) -> str:
    """The token with its last digit replaced by a different one, its type kept."""
    i = max(i for i, ch in enumerate(token) if ch in string.digits)
    digit = rng.choice([d for d in string.digits if d != token[i]])
    return type(token)(token[:i] + digit + token[i + 1 :])


@cache
def _pinned(asset: str) -> tuple[str, ...]:
    catalog = json.loads(_shape("cm-catalog")["skeleton"])
    (entry,) = (e for e in catalog["data"] if e["asset"] == asset)
    return tuple(m["metric"] for m in entry["metrics"] if any(f["frequency"] == "1d" for f in m["frequencies"]))


def _carrying(rows: list[dict], key: str) -> list[int]:
    return [i for i, r in enumerate(rows) if key in r]


def _plain_pinned(rows: list[dict]) -> list[str]:
    """The pinned btc metrics that carry no `-status` companion, so dropping one drops nothing beside it."""
    keys = {k for r in rows for k in r}
    return [m for m in _pinned("btc") if f"{m}-status" not in keys]


def _cm_restatement(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    metric = rng.choice(_pinned("btc"))
    i = rng.choice(_carrying(rows, metric)[1:-1])
    rows[i][metric] = _changed(rows[i][metric], rng)
    return _stream(rows)


def _cm_next(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    newest, before = rows[-1], rows[-2]
    metrics = {k: v for k, v in newest.items() if k not in ("asset", "time")}
    for metric in _pinned("btc"):
        if metric in before and metric not in metrics:
            metrics[metric] = _changed(before[metric], rng)
    rows[-1] = {"asset": newest["asset"], "time": newest["time"], **{k: metrics[k] for k in sorted(metrics)}}
    return _stream(rows)


def _cm_retraction(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    metric = rng.choice(_plain_pinned(rows))
    del rows[rng.choice(_carrying(rows, metric)[1:-1])][metric]
    return _stream(rows)


def _cm_metric_gone(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    for row in rows:
        row.pop(GONE_METRIC, None)
    return _stream(rows)


def _cm_metric_back_changed(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    i = rng.choice(_carrying(rows, GONE_METRIC))
    rows[i][GONE_METRIC] = _changed(rows[i][GONE_METRIC], rng)
    return _stream(rows)


def _cm_gap(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    del rows[_carrying(rows, GAP_METRIC)[-2]][GAP_METRIC]
    return _stream(rows)


def _cm_time_format(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    for row in rows:
        row["time"] = f"{row['time'][:10]}T00:00:00Z"
    return _stream(rows)


def _cm_collapse(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    ends = set()
    for key in {k for r in rows for k in r}:
        carrying = _carrying(rows, key)
        ends |= {carrying[0], carrying[-1]}
    droppable = [i for i in range(len(rows)) if i not in ends]
    drop = len(rows) - len(rows) * 85 // 100
    start = (len(droppable) - drop) // 2
    dropped = set(droppable[start : start + drop])
    return _stream([r for i, r in enumerate(rows) if i not in dropped])


def _cm_lost_newest(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    for metric in _pinned("btc"):
        for i in _carrying(rows, metric)[-2:]:
            for key in (metric, f"{metric}-status", f"{metric}-status-time"):
                rows[i].pop(key, None)
    return _stream([r for r in rows if r.keys() - {"asset", "time"}])


def _cm_frozen(data: bytes, rng: random.Random) -> bytes:
    rows = _stream_rows(data)
    for i in _carrying(rows, FROZEN_METRIC)[-5:]:
        del rows[i][FROZEN_METRIC]
    return _stream(rows)


def _cm_catalog_paginated(data: bytes, rng: random.Random) -> bytes:
    catalog = loads_tokens(data)
    token = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(32))
    catalog["next_page_url"] = f"{_shape('cm-catalog')['real']['url']}&next_page_token={token}"
    return dumps_compact(catalog)


def _cm_403(data: bytes, rng: random.Random) -> bytes:
    asset = _stream_rows(data)[0]["asset"]
    metric = rng.choice(_pinned(asset))
    message = f"Requested metric '{metric}' with frequency '1d' for asset '{asset}' is not available with supplied credentials."
    return dumps_compact({"error": {"type": "forbidden", "message": message}})


def _mempool_restated_big(data: bytes, rng: random.Random) -> bytes:
    doc = loads_tokens(data)
    big = [r for r in doc["hashrates"] if r["avgHashrate"].isdigit() and int(r["avgHashrate"]) > 2**53]
    row = rng.choice(big)
    row["avgHashrate"] = _changed(row["avgHashrate"], rng)
    return dumps_compact(doc)


def _bg_rolled(data: bytes, rng: random.Random) -> bytes:
    rows = loads_tokens(data)
    newest = rows[-1]
    day = date.fromisoformat(newest["d"]) + timedelta(days=1)
    value_key = list(newest)[2]
    epoch = RawNumber(int(datetime.combine(day, time(), UTC).timestamp()))
    rows = [*rows[1:], {"d": day.isoformat(), "unixTs": epoch, value_key: _changed(newest[value_key], rng)}]
    return dumps_compact(rows)


def _bg_newest_back(data: bytes, rng: random.Random) -> bytes:
    return dumps_compact(loads_tokens(data)[:-1])


def _bg_collapse(data: bytes, rng: random.Random) -> bytes:
    return dumps_compact(loads_tokens(data)[-100:])


def _bg_restatement(data: bytes, rng: random.Random) -> bytes:
    rows = loads_tokens(data)
    row = rng.choice(rows)
    value_key = list(row)[2]
    row[value_key] = _changed(row[value_key], rng)
    return dumps_compact(rows)


def _spring(status: int, error: str, message: str | None = None) -> bytes:
    stamp = _shape("bg-sopr")["real"]["fetched_at"].removesuffix("Z") + ".000+00:00"
    body = {"timestamp": stamp, "status": status, "error": error}
    if message is not None:
        body["message"] = message
    body["path"] = "/v1/sopr"
    return dumps_compact(body)


def _bg_404(data: bytes, rng: random.Random) -> bytes:
    return _spring(404, "Not Found")


def _bg_401_echo(data: bytes, rng: random.Random) -> bytes:
    return _spring(401, "Unauthorized", f"Invalid bearer token {SENTINEL_KEY}")


def _bg_429(data: bytes, rng: random.Random) -> bytes:
    return _spring(429, "Too Many Requests")


_FNG_ROW = re.compile(
    rb'\t\t\{\n\t\t\t"value": "(\d+)",\n\t\t\t"value_classification": "([^"]+)",\n'
    rb'\t\t\t"timestamp": "(\d+)"(,\n\t\t\t"time_until_update": "(\d+)")?\n\t\t\}'
)


def _fng_next(data: bytes, rng: random.Random) -> bytes:
    """Edited as text, so the real body's tab indentation stays: a new newest row carries `time_until_update` in the old
    newest's place, and one older row in the Fear band moves its value by one, staying in that band."""
    rows = list(_FNG_ROW.finditer(data))
    newest = rows[0]
    value, classification, stamp, _, until = newest.groups()
    new_row = (
        b'\t\t{\n\t\t\t"value": "%s",\n\t\t\t"value_classification": "%s",\n\t\t\t"timestamp": "%d",\n'
        b'\t\t\t"time_until_update": "%s"\n\t\t},\n' % (value, classification, int(stamp) + 86400, until)
    )
    older = rng.choice([r for r in rows[1:] if r[2] == b"Fear" and 30 <= int(r[1]) <= 40])
    restated = older[0].replace(b'"value": "%s"' % older[1], b'"value": "%d"' % (int(older[1]) + 1), 1)
    return (
        data[: newest.start()]
        + new_row
        + newest[0].replace(newest[4], b"", 1)
        + data[newest.end() : older.start()]
        + restated
        + data[older.end() :]
    )


@dataclass(frozen=True)
class Variant:
    base: str
    what: str
    edit: Callable[[bytes, random.Random], bytes]


VARIANTS: dict[str, Variant] = {
    "cm-btc-restatement": Variant("cm-btc", "one pinned metric's token on a day inside its range changed", _cm_restatement),
    "cm-btc-next": Variant("cm-btc", "the newest row gains every pinned metric the row before it carries", _cm_next),
    "cm-btc-retraction": Variant("cm-btc", "one pinned metric's day inside its range removed", _cm_retraction),
    "cm-btc-metric-gone": Variant("cm-btc", f"{GONE_METRIC} removed from every row", _cm_metric_gone),
    "cm-btc-metric-back-changed": Variant(
        "cm-btc", f"{GONE_METRIC} back after cm-btc-metric-gone, one of its tokens changed", _cm_metric_back_changed
    ),
    "cm-btc-gap": Variant("cm-btc", f"{GAP_METRIC}'s second-newest day removed", _cm_gap),
    "cm-btc-time-format": Variant("cm-btc", "every time token rewritten as YYYY-MM-DDT00:00:00Z", _cm_time_format),
    "cm-btc-collapse": Variant(
        "cm-btc", "85% of the rows kept, a middle run dropped, every key's first and last row kept", _cm_collapse
    ),
    "cm-btc-lost-newest": Variant("cm-btc", "every pinned metric's two newest days removed", _cm_lost_newest),
    "cm-btc-frozen": Variant("cm-btc", f"{FROZEN_METRIC}'s five newest days removed", _cm_frozen),
    "cm-catalog-paginated": Variant("cm-catalog", "a next_page_url added", _cm_catalog_paginated),
    "cm-btc-403": Variant("cm-btc", "the measured forbidden error body for one of its pinned metrics", _cm_403),
    "mempool-hashrate-restated-big": Variant(
        "mempool-hashrate", "one avgHashrate integer past 2^53 changed in its last digit", _mempool_restated_big
    ),
    "bg-sopr-rolled": Variant("bg-sopr", "the oldest row dropped and the next day appended", _bg_rolled),
    "bg-sopr-newest-back": Variant("bg-sopr", "the newest row dropped", _bg_newest_back),
    "bg-sopr-collapse": Variant("bg-sopr", "the newest 100 rows kept", _bg_collapse),
    "bg-sopr-restatement": Variant("bg-sopr", "one row's value changed", _bg_restatement),
    "bg-sopr-404": Variant("bg-sopr", "the Spring error body at 404", _bg_404),
    "bg-sopr-401-echo": Variant("bg-sopr", "the Spring error body at 401, its message echoing the key", _bg_401_echo),
    "bg-sopr-429": Variant("bg-sopr", "the Spring error body at 429", _bg_429),
    "fng-next": Variant("fng", "a new newest row and one older row's value changed", _fng_next),
}


def _base_file(source: str) -> str:
    return FNG_FILE if source == "fng" else _shape(source)["real"]["file"]


def _variant_file(name: str) -> str:
    return f"second/{name}{Path(_base_file(VARIANTS[name].base)).suffix}"


def body(name: str) -> bytes:
    """The committed bytes of a base (`"cm-btc"`) or a second tick (`"second/cm-btc-restatement"`)."""
    second = name.removeprefix("second/")
    return (FIXTURES / (_variant_file(second) if second != name else _base_file(name))).read_bytes()


def _dumps_record(obj: dict) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _provenance(source: str, file: str, how: dict) -> dict:
    holder = _fng_provenance() if source == "fng" else _shape(source)
    return {
        "source": source,
        "file": file,
        "real": holder["real"],
        "committed": "synthesised",
        "how": {"generator": GENERATOR, **how},
        "licence": holder["licence"],
        "attribution": holder["attribution"],
    }


def regenerate() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    bases = {"fng": (FIXTURES / FNG_FILE).read_bytes()}
    for source in SYNTHESISED:
        shape = _shape(source)
        file = _base_file(source)
        bases[source] = synthesize(shape)
        files[FIXTURES / file] = bases[source]
        how = {"shape": f"shapes/{source}.shape.json", "seed": shape["seed"]}
        files[FIXTURES / f"{file}.provenance.json"] = _dumps_record(_provenance(source, file, how))
    for index, (name, variant) in enumerate(VARIANTS.items()):
        seed = VARIANT_SEED + index
        file = _variant_file(name)
        files[FIXTURES / file] = variant.edit(bases[variant.base], random.Random(seed))
        shape_path = FNG_FILE if variant.base == "fng" else f"shapes/{variant.base}.shape.json"
        provenance = _provenance(variant.base, file, {"shape": shape_path, "seed": seed})
        provenance |= {"synthetic_second_tick": True, "from": _base_file(variant.base), "edit": variant.what}
        files[FIXTURES / f"{file}.provenance.json"] = _dumps_record(provenance)
    return files


if __name__ == "__main__":
    for path, data in regenerate().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
