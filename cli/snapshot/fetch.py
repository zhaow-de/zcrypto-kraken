from __future__ import annotations

import json
import urllib.error
import urllib.request

from cli.snapshot.errors import SnapshotError

_BASE_URL = "https://api.kraken.com/0/public"
_TIMEOUT_SECONDS = 15


def fetch_public(method: str) -> dict:
    """GET a Kraken public reference-data endpoint and return its `result` dict, raising `SnapshotError`
    on a transport or JSON failure, on a non-empty `error` array, which Kraken carries inside HTTP 200,
    on a body that is not a JSON object at all, on a body carrying no `result`, and on a `result` that
    is not itself an object."""
    url = f"{_BASE_URL}/{method}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError) as exc:
        raise SnapshotError(f"transport error fetching {method}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"invalid JSON from {method}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SnapshotError(f"response for {method} is {type(payload).__name__}, not a JSON object: {payload!r:.200}")
    errors = payload.get("error") or []
    if errors:
        raise SnapshotError(f"Kraken API error for {method}: {errors}")
    result = payload.get("result")
    if result is None:
        raise SnapshotError(f"no result in the response for {method}: {payload!r}")
    if not isinstance(result, dict):
        raise SnapshotError(f"result for {method} is {type(result).__name__}, not an object: {result!r:.200}")
    return result
