"""The credential guard: no byte the recorder keeps or logs holds the BGeometrics key in any of the scan's four forms,
read through `run_record` over urllib's real opener with a fake HTTPS handler beneath it."""

from __future__ import annotations

import base64
import gzip
import io
import json
import logging
import re
import urllib.error
import urllib.parse
import zlib
from compression import zstd
from types import SimpleNamespace

import pytest

import cli.vintage.record as record_module
from cli.vintage.command import run_record
from cli.vintage.sources import SOURCE_BY_ID, SOURCES
from tests.vintage_fixtures import BASE_TICK_START, SENTINEL_FORMS, SENTINEL_KEY, body
from tests.vintage_stub import FakeClock, FakeHTTPS, Reply, default_bodies

KEYED_HOST = "api.bitcoin-data.com"
KEYED = tuple(source for source in SOURCES if source.keyed)
PLAIN = tuple(source for source in SOURCES if not source.keyed)
ELSEWHERE = "https://elsewhere.example/v1/sopr"
CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
WITNESS = (logging.INFO, re.compile(r"vintage tick published tick=\S+ tick_json_sha256=[0-9a-f]{64}"))
BG_SOPR = default_bodies()["bg-sopr"]
FORM_IDS = ["raw", "json-escaped", "percent-upper", "percent-lower"]


def _warned(source_id: str, reason: str) -> tuple[int, re.Pattern]:
    return logging.WARNING, re.compile(re.escape(f"vintage source not ok source={source_id} outcome=1: {reason}"))


def _echo(form: bytes) -> bytes:
    return b'[{"d":"2026-11-10","note":"' + form + b'"}]'


def _raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def _quoting(form: bytes) -> ValueError:
    """Built as `http.client.putheader` builds the error an invalid header value raises."""
    return ValueError("Invalid header value %r" % (b"Bearer " + form + b"\n",))


# The scan's four forms and `repr()`'s spelling of the JSON-escaped one, its backslash doubled, which an exception's
# `%r` text carries; spelt as a literal, never built from the forms.
SEARCHED_FORMS = (*SENTINEL_FORMS, b"vintage.Sentinel-key_0~9+\\\\/x==")


def _holds(data: bytes, echoes: tuple[bytes, ...] = ()) -> bool:
    return any(form in data for form in (*SEARCHED_FORMS, *echoes))


def _holds_text(text: str, echoes: tuple[bytes, ...] = ()) -> bool:
    return _holds(text.encode("utf-8", "backslashreplace"), echoes)


def _header(pairs, name: str) -> str | None:
    values = [value for key, value in pairs if key.lower() == name.lower()]
    return ", ".join(values) if values else None


def _inflated(data: bytes) -> bytes:
    wrapped = len(data) >= 2 and data[0] & 0x0F == 8 and int.from_bytes(data[:2]) % 31 == 0
    inflater = zlib.decompressobj(zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
    out = inflater.decompress(data)
    assert inflater.eof and not inflater.unused_data, "a stored deflate body does not end where its stream ends"
    return out


_DECODERS = {"gzip": gzip.decompress, "zstd": zstd.decompress, "deflate": _inflated}


def _decoded(data: bytes, encoding: str) -> bytes:
    """A coding outside `_DECODERS` raises `KeyError`, failing the case: a stored body that does not decode."""
    for coding in reversed([coding.strip().lower() for coding in encoding.split(",")]):
        data = _DECODERS[coding](data)
    return data


def _run(tmp_path, replies=None, *, key_stream=None):
    clock = FakeClock(BASE_TICK_START)
    script = {SOURCE_BY_ID[source_id].url: [Reply(200, data)] for source_id, data in default_bodies().items()}
    script[ELSEWHERE] = [Reply(200, b"[]")]
    script.update({SOURCE_BY_ID[source_id].url: list(items) for source_id, items in (replies or {}).items()})
    https = FakeHTTPS(script, clock)
    data_dir = tmp_path / "vintages"
    textfile = tmp_path / "textfile" / "vintage.prom"
    textfile.parent.mkdir()
    code = run_record(
        data_dir,
        textfile,
        tmp_path / "clock-offset.prom",
        key_stream=io.BytesIO(SENTINEL_KEY.encode() + b"\n") if key_stream is None else key_stream,
        https_handler=https,
        clock=clock,
        version="0.0.0",
        revision="",
    )
    return SimpleNamespace(code=code, https=https, data_dir=data_dir, textfile=textfile)


def _assert_dialled(https, echoes: tuple[bytes, ...]) -> None:
    for seen in https.seen:
        assert not _holds_text(seen.url, echoes), seen.url
        assert not any(_holds_text(f"{name}: {value}", echoes) for name, value in seen.headers.items()), seen.headers
        authorization = seen.unredirected.get("Authorization")
        rest = {name: value for name, value in seen.unredirected.items() if name != "Authorization"}
        assert not any(_holds_text(f"{name}: {value}", echoes) for name, value in rest.items()), rest
        if urllib.parse.urlsplit(seen.url).hostname == KEYED_HOST:
            assert authorization == f"Bearer {SENTINEL_KEY}", seen.url
        else:
            assert authorization is None, seen.url


def _assert_stored(run, echoes: tuple[bytes, ...]) -> dict[str, dict]:
    files = [path for root in (run.data_dir, run.textfile.parent) for path in sorted(root.rglob("*")) if path.is_file()]
    for path in files:
        data = path.read_bytes()
        assert not _holds(data, echoes), path
        if path.suffix == ".gz":
            assert not _holds(gzip.decompress(data), echoes), path
    fetches = {}
    for tick_json in run.data_dir.rglob("tick.json"):
        for fetch in json.loads(tick_json.read_bytes())["fetches"]:
            for attempt in fetch["attempts"]:
                if attempt["head"] is not None:
                    assert not _holds(base64.b64decode(attempt["head"], validate=True), echoes), fetch["source"]
            if fetch["body"] is not None:
                served = gzip.decompress((tick_json.parent / fetch["body"]["file"]).read_bytes())
                encoding = _header(fetch["headers"], "Content-Encoding")
                if encoding is not None:
                    assert not _holds(_decoded(served, encoding), echoes), fetch["source"]
            if SOURCE_BY_ID[fetch["source"]].keyed:
                errors = [attempt["error"] for attempt in fetch["attempts"]]
                assert all(error is None or CLASS_NAME.fullmatch(error) for error in errors), errors
                if fetch["attempts"]:
                    assert ["Authorization", "Bearer <redacted>"] in fetch["request_headers"], fetch["request_headers"]
            fetches[fetch["source"]] = fetch
    return fetches


def _assert_holds_no_key(run, caplog, capsys, *controls: tuple[int, re.Pattern], echoes: tuple[bytes, ...] = ()) -> dict[str, dict]:
    """The case's positive controls read among the captured lines first, so the absence is read over lines captured;
    `echoes` are searched for beside the key's four forms."""
    _assert_dialled(run.https, echoes)
    lines = [(record.levelno, record.getMessage()) for record in caplog.records]
    for level, pattern in controls:
        assert any(levelno == level and pattern.fullmatch(line) for levelno, line in lines), lines
    for _, line in lines:
        assert not _holds_text(line, echoes), line
    assert not _holds_text(caplog.text, echoes)
    out, err = capsys.readouterr()
    assert not _holds_text(out + err, echoes), (out, err)
    return _assert_stored(run, echoes)


def test_an_ok_tick_holds_no_key(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path)
    assert run.code == 0
    fetches = _assert_holds_no_key(run, caplog, capsys, WITNESS)
    assert [fetches[source.id]["check"]["outcome"] for source in KEYED] == [0, 0, 0, 0]
    assert [seen.url for seen in run.https.seen if KEYED_HOST in seen.url] == [source.url for source in KEYED]


@pytest.mark.parametrize(
    ("offset", "whole_in_head"), [(1000, True), (4096 - 10, False)], ids=["inside-the-head", "straddling-the-cut"]
)
def test_a_retried_answer_echoing_the_key_keeps_no_head(tmp_path, caplog, capsys, offset, whole_in_head):
    echoing = b"x" * offset + SENTINEL_FORMS[0] + b"y" * 9000
    assert _holds(echoing[:4096]) is whole_in_head
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [Reply(503, echoing, reason="Service Unavailable"), Reply(200, BG_SOPR)]})
    assert run.code == 0
    fetch = _assert_holds_no_key(run, caplog, capsys, WITNESS)["bg-sopr"]
    first, _ = fetch["attempts"]
    assert (first["status"], first["head"]) == (503, None)
    assert first["withheld"] == {"reason": "credential echoed", "bytes": len(echoing)}
    assert fetch["check"]["outcome"] == 0


def test_an_echoing_401_body_is_not_stored(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    echo = body("second/bg-sopr-401-echo")
    assert SENTINEL_FORMS[0] in echo
    run = _run(tmp_path, {"bg-sopr": [Reply(401, echo, reason="Unauthorized")]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, capsys, _warned("bg-sopr", "credential echoed"))["bg-sopr"]
    assert (fetch["status"], fetch["body"]) == (401, None)
    assert fetch["attempts"][0]["withheld"] == {"reason": "credential echoed", "bytes": len(echo)}


@pytest.mark.parametrize("form", SENTINEL_FORMS, ids=FORM_IDS)
def test_an_echoing_header_is_redacted(tmp_path, caplog, capsys, form):
    caplog.set_level(logging.DEBUG)
    challenge = f'Bearer error="invalid_token" token="{form.decode()}"'
    run = _run(tmp_path, {"bg-sopr": [Reply(401, b"{}", [("WWW-Authenticate", challenge)], reason="Unauthorized")]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, capsys, _warned("bg-sopr", "HTTP 401 (no retry)"))["bg-sopr"]
    assert fetch["headers"] == [["WWW-Authenticate", "<redacted>"]]


@pytest.mark.parametrize(
    ("reply", "code", "control", "field", "redacted"),
    [
        *[
            (Reply(401, b"{}", reason=f"bad {form.decode()}"), 1, _warned("bg-sopr", "HTTP 401 (no retry)"), "reason", "<redacted>")
            for form in SENTINEL_FORMS
        ],
        (Reply(200, BG_SOPR, [(SENTINEL_KEY, "1")]), 0, WITNESS, "headers", [["<redacted>", "1"]]),
    ],
    ids=[*(f"reason-phrase-{name}" for name in FORM_IDS), "header-name"],
)
def test_an_echoing_reason_phrase_or_header_name_is_redacted(tmp_path, caplog, capsys, reply, code, control, field, redacted):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [reply]})
    assert run.code == code
    fetch = _assert_holds_no_key(run, caplog, capsys, control)["bg-sopr"]
    assert fetch[field] == redacted


@pytest.mark.parametrize(
    ("served", "headers", "reading"),
    [
        (_echo(SENTINEL_FORMS[1]), [], "credential echoed"),
        (_echo(SENTINEL_FORMS[2]), [], "credential echoed"),
        (_echo(SENTINEL_FORMS[3]), [], "credential echoed"),
        (gzip.compress(_echo(SENTINEL_FORMS[0]), mtime=0), [("Content-Encoding", "gzip")], "credential echoed"),
        (
            gzip.compress(BG_SOPR, mtime=0) + gzip.compress(_echo(SENTINEL_FORMS[0]), mtime=0),
            [("Content-Encoding", "gzip")],
            "credential unscannable",
        ),
        (zstd.compress(BG_SOPR + _echo(SENTINEL_FORMS[0])), [("Content-Encoding", "zstd")], "credential echoed"),
        (zlib.compress(_echo(SENTINEL_FORMS[0])), [("Content-Encoding", "deflate")], "credential echoed"),
        (_raw_deflate(_echo(SENTINEL_FORMS[0])), [("Content-Encoding", "deflate")], "credential echoed"),
    ],
    ids=["json-escaped", "percent-upper", "percent-lower", "gzip", "gzip-two-members", "zstd", "deflate", "deflate-raw"],
)
def test_echoes_in_every_form_are_not_stored(tmp_path, caplog, capsys, served, headers, reading):
    # An encoded echo holds no form as served, so only the decode before the scan finds it; the walk's own decode does.
    assert _holds(served) is not bool(headers)
    if headers:
        assert _holds(_decoded(served, _header(headers, "Content-Encoding")))
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [Reply(200, served, headers)]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, capsys, _warned("bg-sopr", reading))["bg-sopr"]
    assert fetch["body"] is None
    assert fetch["attempts"][0]["withheld"] == {"reason": reading, "bytes": len(served)}


@pytest.mark.parametrize(
    ("served", "encoding", "raised"),
    [
        (zlib.compress(BG_SOPR) + zlib.compress(_echo(SENTINEL_FORMS[0])), "deflate", AssertionError),
        (_raw_deflate(BG_SOPR) + _echo(SENTINEL_FORMS[0]), "deflate", AssertionError),
        (_echo(SENTINEL_FORMS[0]), "br", KeyError),
    ],
    ids=["deflate-two-streams", "deflate-raw-trailing", "br"],
)
def test_the_walk_refuses_a_stored_body_it_cannot_decode_whole(served, encoding, raised):
    with pytest.raises(raised):
        _decoded(served, encoding)


def test_an_unscannable_body_is_not_stored(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    served = _echo(SENTINEL_FORMS[0])
    run = _run(tmp_path, {"bg-sopr": [Reply(200, served, [("Content-Encoding", "br")])]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, capsys, _warned("bg-sopr", "credential unscannable"))["bg-sopr"]
    assert fetch["body"] is None
    assert fetch["attempts"][0]["withheld"] == {"reason": "credential unscannable", "bytes": len(served)}


def test_a_redirect_is_not_followed_and_holds_no_key(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    moved = Reply(302, b"moved", [("Location", ELSEWHERE)], reason="Found")
    run = _run(tmp_path, {"bg-sopr": [moved]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, capsys, _warned("bg-sopr", "HTTP 302 redirect not followed"))["bg-sopr"]
    assert (fetch["status"], fetch["final_url"]) == (302, SOURCE_BY_ID["bg-sopr"].url)
    assert ELSEWHERE not in [seen.url for seen in run.https.seen]


def _reset(form: bytes) -> urllib.error.URLError:
    return urllib.error.URLError(ConnectionResetError(104, f"reset after {form.decode()}"))


@pytest.mark.parametrize("form", SENTINEL_FORMS, ids=FORM_IDS)
def test_a_transport_error_holds_no_key(tmp_path, caplog, capsys, form):
    assert _holds_text(str(_reset(form)))
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [_reset(form), _reset(form)]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, capsys, _warned("bg-sopr", "transport error after 2 attempts"))["bg-sopr"]
    assert [attempt["error"] for attempt in fetch["attempts"]] == ["URLError", "URLError"]


@pytest.mark.parametrize("form", SENTINEL_FORMS, ids=FORM_IDS)
def test_an_exception_quoting_the_key_is_recorded_by_its_class(tmp_path, caplog, capsys, form):
    assert _holds_text(str(_quoting(form)))
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [_quoting(form), Reply(200, BG_SOPR)]})
    assert run.code == 0
    fetch = _assert_holds_no_key(run, caplog, capsys, WITNESS)["bg-sopr"]
    assert [attempt["error"] for attempt in fetch["attempts"]] == ["ValueError", None]


def _raising(form: bytes):
    def _raises_the_quoting_error(*args, **kwargs):
        raise _quoting(form)

    return _raises_the_quoting_error


@pytest.mark.parametrize("form", SENTINEL_FORMS, ids=FORM_IDS)
def test_an_exception_reaching_the_top_holds_no_key(tmp_path, caplog, capsys, monkeypatch, form):
    assert _holds_text(str(_quoting(form)))
    raising = _raising(form)
    monkeypatch.setattr(record_module, "fetch_all", raising)
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path)
    assert run.code == 2
    frame = rf"ValueError at {re.escape(__file__)}:\d+ in {raising.__name__}"
    control = (logging.ERROR, re.compile(f"vintage record failed, nothing published: {frame}"))
    assert _assert_holds_no_key(run, caplog, capsys, control) == {}
    assert len([record for record in caplog.records if record.levelno == logging.ERROR]) == 1
    assert run.https.seen == []


class _Unreadable:
    def read(self) -> bytes:
        raise OSError("unreadable")


# Each malformed value but the first carries the key verbatim, as a vault value wrapped in a quote, a bracket or a BOM.
MALFORMED = (b"two words", b'"' + SENTINEL_FORMS[0] + b'"', b"[" + SENTINEL_FORMS[0] + b"]", b"\xef\xbb\xbf" + SENTINEL_FORMS[0])


@pytest.mark.parametrize(
    ("stream", "reason", "value"),
    [
        (lambda: io.BytesIO(b""), "no credential", None),
        (_Unreadable, "no credential", None),
        *[(lambda value=value: io.BytesIO(value + b"\n"), "malformed credential", value) for value in MALFORMED],
    ],
    ids=["empty", "unreadable", "two-words", "quoted", "bracketed", "bom-prefixed"],
)
def test_a_missing_or_malformed_key_dials_nothing_on_the_keyed_host(tmp_path, caplog, capsys, stream, reason, value):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, key_stream=stream())
    assert run.code == 1
    echoes = () if value is None else (value,)
    fetches = _assert_holds_no_key(run, caplog, capsys, *(_warned(source.id, reason) for source in KEYED), echoes=echoes)
    assert [seen.url for seen in run.https.seen] == [source.url for source in PLAIN]
    for source in KEYED:
        assert (fetches[source.id]["check"]["reason"], fetches[source.id]["attempts"]) == (reason, [])
    assert [fetches[source.id]["check"]["outcome"] for source in PLAIN] == [0] * len(PLAIN)
