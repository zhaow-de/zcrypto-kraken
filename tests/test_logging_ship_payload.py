from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

import pytest

from cli.logging.ship import (
    BACKOFF_MAX_S,
    BACKOFF_MIN_S,
    BATCH_MAX,
    EXIT_DEADLINE_S,
    FLUSH_INTERVAL_S,
    RING_CAPACITY,
    TIMEOUT_S,
    ShipConfig,
    _build_opener,
    build_payload,
)
from tests.fake_loki import FakeLoki
from tests.fake_loki import handler_factory as _handler_factory


@pytest.fixture
def cfg() -> ShipConfig:
    return ShipConfig(url="http://unused.invalid/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")


@pytest.fixture
def handler_factory():
    return _handler_factory


@pytest.fixture
def fake_loki(handler_factory):
    """A running FakeLoki replying 200 OK; yields `(base_url, requests)` where `requests` is
    the server's live recorded-request list."""
    handler_cls = handler_factory()
    with FakeLoki(handler_cls) as url:
        yield url, handler_cls.requests


def _post(url: str, cfg: ShipConfig) -> None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{cfg.username}:{cfg.password}".encode()).decode(),
    }
    req = urllib.request.Request(url, data=build_payload([("INFO", "1", "line")], cfg), headers=headers, method="POST")
    with _build_opener().open(req, timeout=5) as resp:
        assert resp.status == 200


def test_payload_groups_entries_into_one_stream_per_level(cfg):
    body = json.loads(build_payload([("INFO", "1", "a"), ("ERROR", "2", "b"), ("INFO", "3", "c")], cfg))
    streams = {s["stream"]["level"]: s for s in body["streams"]}
    assert set(streams) == {"INFO", "ERROR"}
    assert streams["INFO"]["stream"] == {"host": "h1", "container": "svc1", "level": "INFO"}
    assert streams["INFO"]["values"] == [["1", "a"], ["3", "c"]]  # order preserved


def test_post_carries_basic_auth_and_content_type(fake_loki):
    url, requests = fake_loki
    cfg = ShipConfig(url=f"{url}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")
    _post(cfg.url, cfg)

    assert len(requests) == 1
    path, headers, _body = requests[0]
    assert path.endswith("/loki/api/v1/push")
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"alice:secret").decode()
    assert headers["Content-Type"] == "application/json"


def test_proxy_env_is_ignored(fake_loki, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")  # dead port: a real proxy pickup would fail the POST
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")
    monkeypatch.delenv("no_proxy", raising=False)  # ambient no_proxy=localhost,127.0.0.1 would make this vacuous
    monkeypatch.delenv("NO_PROXY", raising=False)
    url, requests = fake_loki
    cfg = ShipConfig(url=f"{url}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")
    _post(cfg.url, cfg)

    assert len(requests) == 1  # reached fake_loki directly -- the proxy env was ignored


@pytest.mark.parametrize("code", [302, 303, 307, 308])
def test_redirects_are_refused(code, handler_factory):
    """Every code raises `HTTPError` with the original code and leaves the redirect target -- a
    second, independently live FakeLoki -- with no request. The stdlib's stock handler follows
    302/303 on a POST, forwarding Authorization with them; 307/308 it already refuses."""
    target_cls = handler_factory()
    with FakeLoki(target_cls) as target_url:
        redirecting_cls = handler_factory(status_code=code, location=f"{target_url}/loki/api/v1/push")
        with FakeLoki(redirecting_cls) as redirect_url:
            cfg = ShipConfig(url=f"{redirect_url}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")
            req = urllib.request.Request(
                cfg.url,
                data=build_payload([("INFO", "1", "line")], cfg),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Basic " + base64.b64encode(b"alice:secret").decode(),
                },
                method="POST",
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                _build_opener().open(req, timeout=5)
            assert exc_info.value.code == code

    assert target_cls.requests == []  # the redirect was never followed -- no leaked Authorization


def test_module_constants_are_the_spec_values():
    assert (RING_CAPACITY, BATCH_MAX, FLUSH_INTERVAL_S, TIMEOUT_S, BACKOFF_MIN_S, BACKOFF_MAX_S, EXIT_DEADLINE_S) == (
        4096,
        500,
        1.0,
        5.0,
        1.0,
        30.0,
        2.0,
    )
