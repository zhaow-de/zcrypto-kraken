"""merge-gate.py: the read line must name the head, with exactly two exceptions -- the one change-index row commit past the tip it names, and the ops-journal month PR."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "merge-gate.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load(_SCRIPT, "merge_gate")

TIP = "6f02667280cfbd7b76cb39d3139a5f865d995c61"
PREV = "20a3bddb1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f"
OTHER = "38f78872aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _pr(**over) -> dict:
    pr = {
        "number": 1,
        "headRefName": "feat/x",
        "baseRefName": "develop",
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "body": f"## Summary\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n- [x] done\n",
        "headRefOid": TIP,
    }
    pr.update(over)
    return pr


def _head(parents: list[str], files: list[str]) -> dict:
    return {"sha": TIP, "parents": [{"sha": p} for p in parents], "files": [{"filename": f} for f in files]}


def _stale_body(sha: str = PREV) -> str:
    return f"## Summary\n\nRead before push by: Claude Fable 5.1 at {sha[:8]}\n\n- [x] done\n"


def test_a_read_at_the_head_passes():
    assert gate.evaluate(_pr()) == []


def test_the_one_row_commit_past_the_read_passes():
    pr = _pr(body=_stale_body())
    assert gate.evaluate(pr, _head([PREV], [gate.INDEX])) == []


def test_a_row_commit_that_also_touches_another_file_fails():
    pr = _pr(body=_stale_body())
    fails = gate.evaluate(pr, _head([PREV], [gate.INDEX, "cli/engine/executor.py"]))
    assert len(fails) == 1 and fails[0].startswith(f"the read named in the body covers {PREV[:8]}, not the head {TIP[:8]}")


def test_a_second_commit_past_the_read_fails():
    pr = _pr(body=_stale_body())
    assert len(gate.evaluate(pr, _head([OTHER], [gate.INDEX]))) == 1


def test_a_merge_commit_past_the_read_fails():
    pr = _pr(body=_stale_body())
    assert len(gate.evaluate(pr, _head([PREV, OTHER], [gate.INDEX]))) == 1


def test_a_stale_read_with_no_head_commit_to_inspect_fails():
    assert len(gate.evaluate(_pr(body=_stale_body()))) == 1


def test_the_ops_journal_month_pr_needs_no_read_line():
    pr = _pr(headRefName="ops-journal", body="## 2026-09\n\n- [x] CI green\n")
    assert gate.evaluate(pr) == []


def test_a_missing_or_placeholder_line_fails():
    unrecorded = "no 'Read before push by: <model> at <sha>' line in the body: the whole-branch read is unrecorded"
    assert gate.evaluate(_pr(body="## Summary\n\n- [x] done\n")) == [unrecorded]
    assert gate.evaluate(_pr(body=f"Read before push by: <model> at {TIP}\n")) == [unrecorded]
    assert gate.evaluate(_pr(body="Read before push by: Claude Fable 5.1\n")) == [unrecorded]


def test_every_other_arm_still_fires():
    pr = _pr(
        baseRefName="main",
        isDraft=True,
        mergeable="UNKNOWN",
        mergeStateStatus="BLOCKED",
        reviewDecision="CHANGES_REQUESTED",
        statusCheckRollup=[{"conclusion": "FAILURE"}, {"state": "PENDING"}],
        body=f"Read before push by: Claude Fable 5.1 at {TIP}\n\n- [ ] not yet\n",
    )
    fails = gate.evaluate(pr)
    assert [f.split(" ")[0] for f in fails] == [
        "base",
        "PR",
        "mergeable='UNKNOWN'",
        "mergeStateStatus=BLOCKED",
        "reviewDecision=CHANGES_REQUESTED",
        "1",
        "1",
        "PR",
    ]
