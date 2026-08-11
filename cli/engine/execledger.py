from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.engine.execgate import GateVerdict

EXEC_SCHEMA_VERSION = 1

# Deliberately NOT `cycle-<HH>.json` and NOT a `failed-cycle-*` sidecar. The Stage-6a streak is
# scored off those two names, and a refusal to trade is not a broken research day -- the cycle
# computed its targets correctly and simply was not permitted to act. Keeping execution outcomes
# in a separate file with a separate prefix makes that structural rather than a matter of care.
_PREFIX = "exec"


def exec_record_path(journal_dir: Path, cycle_ts: datetime) -> Path:
    return Path(journal_dir) / f"{cycle_ts:%Y-%m-%d}" / f"{_PREFIX}-{cycle_ts:%H}.json"


def write_exec_record(journal_dir: Path, cycle_ts: datetime, verdict: GateVerdict, *, evaluated_at: datetime) -> Path:
    path = exec_record_path(journal_dir, cycle_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": EXEC_SCHEMA_VERSION,
        "cycle_ts": cycle_ts.isoformat(),
        "evaluated_at": evaluated_at.isoformat(),
        "level": verdict.level,
        "reasons": list(verdict.reasons),
        "inputs": dict(verdict.inputs),
        # Empty by construction while nothing can submit. The key exists from schema 1 so the
        # first spec that DOES submit adds rows, never a field.
        "submitted": [],
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=True))
    return path


def read_exec_record(path: Path) -> dict:
    return json.loads(Path(path).read_text())
