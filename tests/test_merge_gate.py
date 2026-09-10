"""merge-gate.py: the read line must be at the floor and name the head, with exactly two exceptions -- the one change-index row commit past the tip it names, and the ops-journal month PR."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "merge-gate.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load(_SCRIPT, "merge_gate")


def _eval(pr, head_commit=None, files=None, branch_growth=()):
    return gate.evaluate(pr, head_commit, files, list(branch_growth))


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
    assert _eval(_pr()) == []


def test_the_one_row_commit_past_the_read_passes():
    pr = _pr(body=_stale_body())
    assert _eval(pr, _head([PREV], [gate.INDEX])) == []


def test_a_row_commit_that_also_touches_another_file_fails():
    pr = _pr(body=_stale_body())
    fails = _eval(pr, _head([PREV], [gate.INDEX, "cli/engine/executor.py"]))
    assert len(fails) == 1 and fails[0].startswith(f"the read named in the body covers {PREV[:8]}, not the head {TIP[:8]}")


def test_a_second_commit_past_the_read_fails():
    pr = _pr(body=_stale_body())
    assert len(_eval(pr, _head([OTHER], [gate.INDEX]))) == 1


def test_a_merge_commit_past_the_read_fails():
    pr = _pr(body=_stale_body())
    assert len(_eval(pr, _head([PREV, OTHER], [gate.INDEX]))) == 1


def test_a_stale_read_with_no_head_commit_to_inspect_fails():
    assert len(_eval(_pr(body=_stale_body()))) == 1


JOURNAL_PR = {"headRefName": "ops-journal", "body": "## 2026-09\n\n- [x] CI green\n"}


def test_the_ops_journal_month_pr_needs_no_read_line():
    assert _eval(_pr(**JOURNAL_PR), files=["docs/reference/ops-journal/2026-09.md"]) == []


def test_a_journal_pr_carrying_a_foreign_file_takes_every_arm():
    files = ["docs/reference/ops-journal/2026-09.md", "cli/engine/executor.py"]
    fails = _eval(_pr(**JOURNAL_PR), files=files)
    assert len(fails) == 1 and fails[0].startswith("no 'Read before push by:")
    haiku = _pr(headRefName="ops-journal", body=f"Read before push by: Claude Haiku 4.5 at {TIP}\n\n- [x] done\n")
    assert len(_eval(haiku, files=files)) == 1 and "the floor is Claude Opus" in _eval(haiku, files=files)[0]


def test_a_journal_pr_with_no_file_list_fails():
    assert len(_eval(_pr(**JOURNAL_PR))) == 1


def test_a_missing_or_placeholder_line_fails():
    unrecorded = "no 'Read before push by: <model> at <sha>' line in the body: the whole-branch read is unrecorded"
    assert _eval(_pr(body="## Summary\n\n- [x] done\n")) == [unrecorded]
    assert _eval(_pr(body=f"Read before push by: <model> at {TIP}\n")) == [unrecorded]
    assert _eval(_pr(body="Read before push by: Claude Fable 5.1\n")) == [unrecorded]


def _read_by(model: str) -> str:
    return f"## Summary\n\nRead before push by: {model} at {TIP}\n\n- [x] done\n"


def test_a_read_below_the_floor_fails():
    fails = _eval(_pr(body=_read_by("Claude Haiku 4.5")), files=[])
    assert len(fails) == 1 and "the floor is Claude Opus" in fails[0]
    assert len(_eval(_pr(body=_read_by("Claude Sonnet 4.6")), files=[])) == 1


def test_an_opus_read_passes_off_the_guarded_paths():
    pr = _pr(body=_read_by("Claude Opus 4.8"))
    assert _eval(pr, files=["cli/costs/schedule.py", "docs/reference/fleet.md", "infra/ansible/roles/ops/tasks/main.yml"]) == []


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        ".claude/skills/open-pr/SKILL.md",
        "cli/engine/executor.py",
        "cli/capture/daemon.py",
        "infra/ansible/roles/capture/tasks/main.yml",
        "infra/ansible/roles/engine/tasks/main.yml",
    ],
)
def test_an_opus_read_on_a_guarded_path_fails(path):
    fails = _eval(_pr(body=_read_by("Claude Opus 4.8")), files=["cli/costs/schedule.py", path])
    assert len(fails) == 1 and path in fails[0] and fails[0].endswith("the floor there is Claude Fable")


def test_a_look_alike_path_is_not_guarded():
    pr = _pr(body=_read_by("Claude Opus 4.8"))
    assert _eval(pr, files=["cli/engine_tools/x.py", "docs/CLAUDE.md", "infra/ansible/roles/capture-mirror/tasks/main.yml"]) == []


def test_an_opus_read_with_no_file_list_fails():
    assert len(_eval(_pr(body=_read_by("Claude Opus 4.8")))) == 1


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
    fails = _eval(pr)
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


def test_a_commit_growing_the_guidance_unstated_fails_the_gate():
    growth = [
        "1a2b3c4d claude(rules): x: the always-loaded guidance grows by 40 bytes against its parent and the message does not say so"
    ]
    assert _eval(_pr(), branch_growth=growth) == growth


def test_the_range_mode_s_refusals_are_prefixed_with_the_commit_and_a_run_failure_is_not(monkeypatch):
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            return gate.subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "merge-base"]:
            return gate.subprocess.CompletedProcess(args, 0, "a" * 40 + "\n", "")
        return gate.subprocess.CompletedProcess(
            args,
            1,
            "guidance-guard: refused over a..b\n  - 1a2b3c4d claude(rules): x: the always-loaded guidance grows by 40 bytes\n",
            "",
        )

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate.branch_growth("develop", "feat/x", "b" * 40) == [
        "a commit fails the guidance guard against its parent — 1a2b3c4d claude(rules): x: the always-loaded guidance grows by 40 bytes"
    ]


def test_a_timeout_anywhere_and_a_silent_merge_base_failure_are_refusals_too(monkeypatch):
    calls = []

    def guard_times_out(args, **kwargs):
        calls.append(args[:2])
        if args[:2] == ["git", "fetch"]:
            return gate.subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "merge-base"]:
            return gate.subprocess.CompletedProcess(args, 0, "a" * 40 + "\n", "")
        raise gate.subprocess.TimeoutExpired(args, 300)

    monkeypatch.setattr(gate.subprocess, "run", guard_times_out)
    fails = gate.branch_growth("develop", "feat/x", "b" * 40)
    assert len(calls) == 3 and len(fails) == 1 and fails[0].startswith("the branch could not be checked commit by commit: ")

    def orphan(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            return gate.subprocess.CompletedProcess(args, 0, "", "")
        raise gate.subprocess.CalledProcessError(1, args, output="", stderr="")  # merge-base: no output, exit 1

    monkeypatch.setattr(gate.subprocess, "run", orphan)
    assert gate.branch_growth("develop", "feat/x", "b" * 40) == [
        "the branch could not be checked commit by commit: no merge base between origin/develop and bbbbbbbb"
    ]

    def gone(args, **kwargs):
        raise gate.subprocess.CalledProcessError(128, args, output="", stderr="fatal: couldn't find remote ref gone/branch\n")

    monkeypatch.setattr(gate.subprocess, "run", gone)
    assert gate.branch_growth("develop", "gone/branch", "b" * 40) == [
        "the branch could not be checked commit by commit: fatal: couldn't find remote ref gone/branch"
    ]


def test_an_unchecked_branch_growth_fails_the_gate():
    fails = gate.evaluate(_pr(), None, None, None)
    assert len(fails) == 1 and "was not checked commit by commit" in fails[0]


def test_a_branch_that_cannot_be_fetched_is_one_refusal_not_a_crash(monkeypatch):
    def raise_fetch(*args, **kwargs):
        raise gate.subprocess.CalledProcessError(128, args[0], output="", stderr="fatal: couldn't find remote ref gone/branch\n")

    monkeypatch.setattr(gate.subprocess, "run", raise_fetch)
    fails = gate.branch_growth("develop", "gone/branch", "0" * 40)
    assert fails == ["the branch could not be checked commit by commit: fatal: couldn't find remote ref gone/branch"]
