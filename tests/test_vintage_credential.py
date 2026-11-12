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


def _warned(source_id: str, reason: str) -> tuple[int, re.Pattern]:
    return logging.WARNING, re.compile(re.escape(f"vintage source not ok source={source_id} outcome=1: {reason}"))


def _echo(form: bytes) -> bytes:
    return b'[{"d":"2026-11-10","note":"' + form + b'"}]'


def _quoting() -> ValueError:
    """Built as `http.client.putheader` builds the error an invalid header value raises."""
    return ValueError("Invalid header value %r" % (f"Bearer {SENTINEL_KEY}\n".encode("latin-1"),))


def _holds(data: bytes) -> bool:
    return any(form in data for form in SENTINEL_FORMS)


def _holds_text(text: str) -> bool:
    return _holds(text.encode("utf-8", "backslashreplace"))


def _header(pairs, name: str) -> str | None:
    values = [value for key, value in pairs if key.lower() == name.lower()]
    return ", ".join(values) if values else None


def _inflated(data: bytes) -> bytes:
    wrapped = len(data) >= 2 and data[0] & 0x0F == 8 and int.from_bytes(data[:2]) % 31 == 0
    inflater = zlib.decompressobj(zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
    out = inflater.decompress(data)
    assert inflater.eof and not inflater.unused_data, "a stored deflate body does not end where its stream ends"
    return out


def _decoded(data: bytes, encoding: str) -> bytes:
    for coding in reversed([coding.strip().lower() for coding in encoding.split(",")]):
        if coding in ("", "identity"):
            continue
        if coding == "gzip":
            data = gzip.decompress(data)
        elif coding == "zstd":
            data = zstd.decompress(data)
        elif coding == "deflate":
            data = _inflated(data)
        else:
            pytest.fail(f"a stored body in {coding!r} does not decode")
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


def _assert_dialled(https) -> None:
    for seen in https.seen:
        assert not _holds_text(seen.url), seen.url
        assert not any(_holds_text(f"{name}: {value}") for name, value in seen.headers.items()), seen.headers
        authorization = seen.unredirected.get("Authorization")
        rest = {name: value for name, value in seen.unredirected.items() if name != "Authorization"}
        assert not any(_holds_text(f"{name}: {value}") for name, value in rest.items()), rest
        if urllib.parse.urlsplit(seen.url).hostname == KEYED_HOST:
            assert authorization == f"Bearer {SENTINEL_KEY}", seen.url
        else:
            assert authorization is None, seen.url


def _assert_stored(run) -> dict[str, dict]:
    files = [path for root in (run.data_dir, run.textfile.parent) for path in sorted(root.rglob("*")) if path.is_file()]
    for path in files:
        data = path.read_bytes()
        assert not _holds(data), path
        if path.suffix == ".gz":
            assert not _holds(gzip.decompress(data)), path
    fetches = {}
    for tick_json in run.data_dir.rglob("tick.json"):
        for fetch in json.loads(tick_json.read_bytes())["fetches"]:
            for attempt in fetch["attempts"]:
                if attempt["head"] is not None:
                    assert not _holds(base64.b64decode(attempt["head"], validate=True)), fetch["source"]
            if fetch["body"] is not None:
                served = gzip.decompress((tick_json.parent / fetch["body"]["file"]).read_bytes())
                encoding = _header(fetch["headers"], "Content-Encoding")
                if encoding is not None:
                    assert not _holds(_decoded(served, encoding)), fetch["source"]
            if SOURCE_BY_ID[fetch["source"]].keyed:
                errors = [attempt["error"] for attempt in fetch["attempts"]]
                assert all(error is None or CLASS_NAME.fullmatch(error) for error in errors), errors
                if fetch["attempts"]:
                    assert ["Authorization", "Bearer <redacted>"] in fetch["request_headers"], fetch["request_headers"]
            fetches[fetch["source"]] = fetch
    return fetches


def _assert_holds_no_key(run, caplog, *controls: tuple[int, re.Pattern]) -> dict[str, dict]:
    """The case's positive controls read among the captured lines first, so the absence is read over lines captured."""
    _assert_dialled(run.https)
    lines = [(record.levelno, record.getMessage()) for record in caplog.records]
    for level, pattern in controls:
        assert any(levelno == level and pattern.fullmatch(line) for levelno, line in lines), lines
    for _, line in lines:
        assert not _holds_text(line), line
    assert not _holds_text(caplog.text)
    return _assert_stored(run)


def test_an_ok_tick_holds_no_key(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path)
    assert run.code == 0
    fetches = _assert_holds_no_key(run, caplog, WITNESS)
    assert [fetches[source.id]["check"]["outcome"] for source in KEYED] == [0, 0, 0, 0]
    assert [seen.url for seen in run.https.seen if KEYED_HOST in seen.url] == [source.url for source in KEYED]


def test_a_retried_answer_echoing_the_key_keeps_no_head(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    echoing = b"x" * 1000 + SENTINEL_FORMS[0] + b"y" * 9000
    run = _run(tmp_path, {"bg-sopr": [Reply(503, echoing, reason="Service Unavailable"), Reply(200, BG_SOPR)]})
    assert run.code == 0
    fetch = _assert_holds_no_key(run, caplog, WITNESS)["bg-sopr"]
    first, _ = fetch["attempts"]
    assert (first["status"], first["head"]) == (503, None)
    assert first["withheld"] == {"reason": "credential echoed", "bytes": len(echoing)}
    assert fetch["check"]["outcome"] == 0


def test_an_echoing_401_body_is_not_stored(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    echo = body("second/bg-sopr-401-echo")
    assert SENTINEL_FORMS[0] in echo
    run = _run(tmp_path, {"bg-sopr": [Reply(401, echo, reason="Unauthorized")]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, _warned("bg-sopr", "credential echoed"))["bg-sopr"]
    assert (fetch["status"], fetch["body"]) == (401, None)
    assert fetch["attempts"][0]["withheld"] == {"reason": "credential echoed", "bytes": len(echo)}


def test_an_echoing_header_is_redacted(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    challenge = f'Bearer error="invalid_token" token="{SENTINEL_FORMS[0].decode()}"'
    run = _run(tmp_path, {"bg-sopr": [Reply(401, b"{}", [("WWW-Authenticate", challenge)], reason="Unauthorized")]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, _warned("bg-sopr", "HTTP 401 (no retry)"))["bg-sopr"]
    assert fetch["headers"] == [["WWW-Authenticate", "<redacted>"]]


@pytest.mark.parametrize(
    ("reply", "code", "control", "field", "redacted"),
    [
        (Reply(401, b"{}", reason=f"bad {SENTINEL_KEY}"), 1, _warned("bg-sopr", "HTTP 401 (no retry)"), "reason", "<redacted>"),
        (Reply(200, BG_SOPR, [(SENTINEL_KEY, "1")]), 0, WITNESS, "headers", [["<redacted>", "1"]]),
    ],
    ids=["reason-phrase", "header-name"],
)
def test_an_echoing_reason_phrase_or_header_name_is_redacted(tmp_path, caplog, reply, code, control, field, redacted):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [reply]})
    assert run.code == code
    fetch = _assert_holds_no_key(run, caplog, control)["bg-sopr"]
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
    ],
    ids=["json-escaped", "percent-upper", "percent-lower", "gzip", "gzip-two-members"],
)
def test_echoes_in_every_form_are_not_stored(tmp_path, caplog, served, headers, reading):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [Reply(200, served, headers)]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, _warned("bg-sopr", reading))["bg-sopr"]
    assert fetch["body"] is None
    assert fetch["attempts"][0]["withheld"] == {"reason": reading, "bytes": len(served)}


def test_an_unscannable_body_is_not_stored(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    served = _echo(SENTINEL_FORMS[0])
    run = _run(tmp_path, {"bg-sopr": [Reply(200, served, [("Content-Encoding", "br")])]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, _warned("bg-sopr", "credential unscannable"))["bg-sopr"]
    assert fetch["body"] is None
    assert fetch["attempts"][0]["withheld"] == {"reason": "credential unscannable", "bytes": len(served)}


def test_a_redirect_is_not_followed_and_holds_no_key(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    moved = Reply(302, b"moved", [("Location", ELSEWHERE)], reason="Found")
    run = _run(tmp_path, {"bg-sopr": [moved]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, _warned("bg-sopr", "HTTP 302 redirect not followed"))["bg-sopr"]
    assert (fetch["status"], fetch["final_url"]) == (302, SOURCE_BY_ID["bg-sopr"].url)
    assert ELSEWHERE not in [seen.url for seen in run.https.seen]


def _reset() -> urllib.error.URLError:
    return urllib.error.URLError(ConnectionResetError(104, f"reset after {SENTINEL_FORMS[0].decode()}"))


def test_a_transport_error_holds_no_key(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [_reset(), _reset()]})
    assert run.code == 1
    fetch = _assert_holds_no_key(run, caplog, _warned("bg-sopr", "transport error after 2 attempts"))["bg-sopr"]
    assert [attempt["error"] for attempt in fetch["attempts"]] == ["URLError", "URLError"]


def test_an_exception_quoting_the_key_is_recorded_by_its_class(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, {"bg-sopr": [_quoting(), Reply(200, BG_SOPR)]})
    assert run.code == 0
    fetch = _assert_holds_no_key(run, caplog, WITNESS)["bg-sopr"]
    assert [attempt["error"] for attempt in fetch["attempts"]] == ["ValueError", None]


def _raises_the_quoting_error(*args, **kwargs):
    raise _quoting()


def test_an_exception_reaching_the_top_holds_no_key(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(record_module, "fetch_all", _raises_the_quoting_error)
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path)
    assert run.code == 2
    frame = rf"ValueError at {re.escape(__file__)}:\d+ in {_raises_the_quoting_error.__name__}"
    control = (logging.ERROR, re.compile(f"vintage record failed, nothing published: {frame}"))
    assert _assert_holds_no_key(run, caplog, control) == {}
    assert len([record for record in caplog.records if record.levelno == logging.ERROR]) == 1
    assert run.https.seen == []


class _Unreadable:
    def read(self) -> bytes:
        raise OSError("unreadable")


@pytest.mark.parametrize(
    ("stream", "reason"),
    [
        (lambda: io.BytesIO(b""), "no credential"),
        (_Unreadable, "no credential"),
        (lambda: io.BytesIO(b"two words\n"), "malformed credential"),
    ],
    ids=["empty", "unreadable", "malformed"],
)
def test_a_missing_or_malformed_key_dials_nothing_on_the_keyed_host(tmp_path, caplog, stream, reason):
    caplog.set_level(logging.DEBUG)
    run = _run(tmp_path, key_stream=stream())
    assert run.code == 1
    fetches = _assert_holds_no_key(run, caplog, *(_warned(source.id, reason) for source in KEYED))
    assert [seen.url for seen in run.https.seen] == [source.url for source in PLAIN]
    for source in KEYED:
        assert (fetches[source.id]["check"]["reason"], fetches[source.id]["attempts"]) == (reason, [])
    assert [fetches[source.id]["check"]["outcome"] for source in PLAIN] == [0] * len(PLAIN)
