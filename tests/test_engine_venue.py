from __future__ import annotations

import io
import json
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone

from cli.engine.venue import read_system_status

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _opener_returning(payload: dict):
    @contextmanager
    def opener(url, timeout=None):
        yield io.BytesIO(json.dumps(payload).encode())

    return opener


def test_online_is_the_only_ok_status():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "online"}}))
    assert st.ok is True
    assert st.status == "online"
    assert st.observed_at == NOW


def test_maintenance_is_not_ok():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "maintenance"}}))
    assert st.ok is False
    assert st.status == "maintenance"


def test_cancel_only_is_not_ok():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "cancel_only"}}))
    assert st.ok is False


def test_an_unknown_status_is_not_ok():
    # Fail closed on a value we have never seen rather than assuming it is benign.
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "wibble"}}))
    assert st.ok is False
    assert st.status == "wibble"


def test_krakens_error_array_is_not_ok_even_on_http_200():
    # Kraken returns HTTP 200 with errors in the body — the trap cli/ohlc/fetch.py documents.
    st = read_system_status(now=NOW, opener=_opener_returning({"error": ["EGeneral:Invalid"], "result": {"status": "online"}}))
    assert st.ok is False


def test_a_transport_failure_is_not_ok_and_does_not_raise():
    @contextmanager
    def failing(url, timeout=None):
        raise urllib.error.URLError("no route to host")
        yield  # pragma: no cover

    st = read_system_status(now=NOW, opener=failing)
    assert st.ok is False
    assert st.status == "unreachable"


def test_a_malformed_body_is_not_ok_and_does_not_raise():
    @contextmanager
    def garbage(url, timeout=None):
        yield io.BytesIO(b"<html>502 Bad Gateway</html>")

    st = read_system_status(now=NOW, opener=garbage)
    assert st.ok is False
    assert st.status == "unreadable"


def test_a_missing_status_key_is_not_ok():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {}}))
    assert st.ok is False
