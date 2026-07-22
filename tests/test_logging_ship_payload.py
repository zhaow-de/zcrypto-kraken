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


@pytest.fixture
def fake_loki_redirecting(handler_factory):
    handler_cls = handler_factory(status_code=308, location="http://127.0.0.1:1/elsewhere")
    with FakeLoki(handler_cls) as url:
        yield url


def _post(url: str, cfg: ShipConfig, *, auth: bool = True) -> None:
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{cfg.username}:{cfg.password}".encode()).decode()
    req = urllib.request.Request(url, data=build_payload([("INFO", "1", "line")], cfg), headers=headers, method="POST")
    with _build_opener().open(req, timeout=5) as resp:
        assert resp.status == 200


def test_payload_groups_entries_into_one_stream_per_level(cfg):
    body = json.loads(build_payload([("INFO", "1", "a"), ("ERROR", "2", "b"), ("INFO", "3", "c")], cfg))
    streams = {s["stream"]["level"]: s for s in body["streams"]}
    assert set(streams) == {"INFO", "ERROR"}
    assert streams["INFO"]["stream"] == {"host": "h1", "container": "svc1", "level": "INFO"}
    assert streams["INFO"]["values"] == [["1", "a"], ["3", "c"]]  # order preserved


def test_post_carries_basic_auth_and_content_type(fake_loki, handler_factory):
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
    url, requests = fake_loki
    cfg = ShipConfig(url=f"{url}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")
    _post(cfg.url, cfg)

    assert len(requests) == 1  # reached fake_loki directly -- the proxy env was ignored


def test_redirects_are_refused(fake_loki_redirecting):
    cfg = ShipConfig(
        url=f"{fake_loki_redirecting}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1"
    )
    req = urllib.request.Request(
        cfg.url,
        data=build_payload([("INFO", "1", "line")], cfg),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _build_opener().open(req, timeout=5)
    assert exc_info.value.code == 308


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
