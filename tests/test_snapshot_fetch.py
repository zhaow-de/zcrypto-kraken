import io
import json
import urllib.error
import urllib.request

import pytest

from cli.snapshot.errors import SnapshotError
from cli.snapshot.fetch import fetch_public


def _ok_response(result):
    body = json.dumps({"error": [], "result": result}).encode("utf-8")
    return io.BytesIO(body)


def _error_response(errors):
    body = json.dumps({"error": errors, "result": {}}).encode("utf-8")
    return io.BytesIO(body)


def test_fetch_public_returns_result_on_success(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _ok_response({"pairs": 1509}))
    assert fetch_public("AssetPairs") == {"pairs": 1509}


def test_fetch_public_raises_on_nonempty_error_array(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _error_response(["EGeneral:Invalid arguments"]))
    with pytest.raises(SnapshotError):
        fetch_public("AssetPairs")


def test_fetch_public_raises_on_transport_error(monkeypatch):
    def _raise(url, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(SnapshotError):
        fetch_public("AssetPairs")
