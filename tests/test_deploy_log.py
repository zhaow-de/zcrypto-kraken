"""docs/reference/deploy-log.jsonl: the machine record every real converge appends (converge.sh).

One JSON object per line, append-only, never hand-edited: the digest and timestamp a rollback needs
come from the pass that set them, not from an operator's memory. This guards the shape -- a line that
does not parse, or lacks a field, makes the whole file unreadable to the next tool that reads it.
"""

import json
from pathlib import Path

DEPLOY_LOG = Path(__file__).resolve().parents[1] / "docs/reference/deploy-log.jsonl"
REQUIRED = {"ts", "playbook", "limit", "tags", "extra_vars", "revision", "dirty", "rc"}


def _records():
    text = DEPLOY_LOG.read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_the_deploy_log_exists_and_every_line_is_one_complete_record():
    assert DEPLOY_LOG.exists(), "converge.sh appends here; the file must exist on develop"
    for i, rec in enumerate(_records(), 1):
        missing = REQUIRED - set(rec)
        assert not missing, f"line {i} lacks {sorted(missing)}"
        assert isinstance(rec["extra_vars"], dict) and isinstance(rec["rc"], int) and isinstance(rec["dirty"], bool)
        assert rec["ts"].endswith("Z"), f"line {i}: ts is UTC ISO-8601 with a Z suffix, got {rec['ts']!r}"


def test_the_deploy_log_is_append_only_in_time():
    ts = [r["ts"] for r in _records()]
    assert ts == sorted(ts), "records are appended in order; an out-of-order ts means a hand edit"
