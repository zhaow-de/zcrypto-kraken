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


def _resultless_response():
    body = json.dumps({"error": []}).encode("utf-8")
    return io.BytesIO(body)


def _non_object_response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


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


def test_fetch_public_raises_on_a_body_carrying_no_result(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _resultless_response())
    with pytest.raises(SnapshotError, match="no result in the response for AssetPairs"):
        fetch_public("AssetPairs")


def test_fetch_public_returns_a_present_but_empty_result(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _ok_response({}))
    assert fetch_public("AssetPairs") == {}


@pytest.mark.parametrize("body", [None, ["EGeneral:Internal error"]], ids=["json-null", "json-list"])
def test_fetch_public_raises_on_a_body_that_is_not_a_json_object(monkeypatch, body):
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _non_object_response(body))
    with pytest.raises(SnapshotError, match="not a JSON object"):
        fetch_public("AssetPairs")
