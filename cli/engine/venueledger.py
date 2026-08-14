from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.engine.venuestate import ConcordanceVerdict, VenueState

# Bumped 1 -> 2 (spec 00094): `state.to_payload()`'s shape changed four ways -- instruments/positions
# keys go base -> symbol, `InstrumentConstraints.symbol` (was `.base`), and the new `costmin_quote`
# field -- so a pre- and post-deploy record are distinguishable on inspection. Write-only: nothing
# reads or validates this constant against a record's actual shape.
VENUE_SCHEMA_VERSION = 2

# Same rationale as `execledger.py`'s `_PREFIX`: deliberately not `cycle-<HH>.json` and not a
# `failed-cycle-*` sidecar, so the Stage-6a streak's globs never see this file -- structural, not
# a matter of care (proved in tests/test_engine_execledger.py's two exec pins, parametrized over
# this prefix too).
_PREFIX = "venue"


def venue_record_path(journal_dir: Path, cycle_ts: datetime) -> Path:
    return Path(journal_dir) / f"{cycle_ts:%Y-%m-%d}" / f"{_PREFIX}-{cycle_ts:%H}.json"


def write_venue_record(
    journal_dir: Path,
    cycle_ts: datetime,
    *,
    state: VenueState | None,
    concordance: ConcordanceVerdict | None,
    code_version: str,
    error: str | None = None,
) -> Path:
    """`state=None` + `error=...` writes `status: "error"` with the reason and NO `state` key --
    `venue_state_from_cache` raised (venuestate.py docstring) and there is nothing to record but
    why. `state=None` with no `error` is a caller bug, not a degraded record: raises `ValueError`.
    """
    if state is None and error is None:
        raise ValueError("write_venue_record: state=None requires error to be set")
    path = venue_record_path(journal_dir, cycle_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": VENUE_SCHEMA_VERSION,
        "cycle_ts": cycle_ts.isoformat(),
        "code_version": code_version,
        "status": "error" if state is None else "ok",
    }
    if state is None:
        doc["error"] = error
    else:
        doc["state"] = state.to_payload()
        doc["concordance"] = {"ok": concordance.ok, "failures": list(concordance.failures)}
    path.write_text(json.dumps(doc, indent=2, sort_keys=True))
    return path


def read_venue_record(path: Path) -> dict:
    return json.loads(Path(path).read_text())
