from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

_BASE_URL = "https://api.kraken.com/0/public/SystemStatus"
_TIMEOUT_SECONDS = 10

# The only value that permits submission, kept as an allowlist of ONE: a denylist would silently
# permit whatever venue state it failed to enumerate.
_OK_STATUS = "online"


@dataclass(frozen=True)
class VenueStatus:
    """One reading of Kraken's venue status; `ok` is the only field control flow may branch on, `status` says why."""

    status: str  # Kraken's own string, or "unreachable" (transport) / "unreadable" (bad body)
    ok: bool
    observed_at: datetime


def read_system_status(*, now: datetime, opener=urllib.request.urlopen) -> VenueStatus:
    """Read Kraken's public SystemStatus; never raises -- every failure becomes `ok=False`, since a caller may hold the
    live trade key and an unknown venue state must reach its gate as a refusal, never as an exception at a submission site.
    """
    try:
        with opener(_BASE_URL, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.URLError, OSError, TimeoutError:
        return VenueStatus(status="unreachable", ok=False, observed_at=now)
    except Exception:  # noqa: BLE001 -- a malformed body must refuse, never propagate
        return VenueStatus(status="unreadable", ok=False, observed_at=now)

    if not isinstance(payload, dict):
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    if payload.get("error"):
        # Kraken answers HTTP 200 with errors carried in the body.
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    result = payload.get("result")
    if not isinstance(result, dict):
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    status = result.get("status")
    if not isinstance(status, str) or not status:
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    return VenueStatus(status=status, ok=status == _OK_STATUS, observed_at=now)
